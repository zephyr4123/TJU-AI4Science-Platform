#!/bin/sh
# AAAI4S 一行命令安装（外层 #277）：
#
#     curl -fsSL https://media.zephyrxiang.com/ai4science/dist/install.sh | sh
#
# 只做 Python 还没有时非做不可的事：装 uv、装平台，然后交给 `ai4sci setup`（查 git、装两家 CLI、
# 问 key、起服务）。全程国内源；每一项先查，装过的跳过；重跑就是升级。装出来的都在平台的家里
# （~/.ai4sci），落在外面的只有 shell 配置里一行 PATH。
#
# 下面的地址与目录名和 framework/mirrors.py、framework/paths.py 是同一份事实，
# tests/test_install_script.py 对账。__VERSION__ 这类占位由发版流水线写进去（.github/scripts/cdn.sh）。
set -eu
# 变量一律带花括号：Mac 的 /bin/sh 在 UTF-8 下会把 `$VAR，` 里全角逗号的头一个字节读进变量名

VERSION="__VERSION__"
UV_VERSION="__UV_VERSION__"
DIST="${AI4SCI_DIST:-https://media.zephyrxiang.com/ai4science/dist}"
PYPI_INDEX="https://mirrors.tuna.tsinghua.edu.cn/pypi/web/simple"
PYTHON_DOWNLOADS="https://registry.npmmirror.com/-/binary/python-build-standalone"
PYTHON_WANTED=">=3.12"
PYTHON_INSTALL="3.12"
HOME_DIR="${AI4SCI_HOME:-${HOME}/.ai4sci}"
BIN="${HOME_DIR}/bin"
TOOLS="${HOME_DIR}/tools"
LOG="${HOME_DIR}/install.log"

# 标签只用英文名：printf 按字节补空格，中文会错位
say() { printf '  %s %-14s%s\n' "$1" "$2" "$3"; }
die() { say "✗" "$1" "$2" >&2; exit 1; }

# 平台名：uv 的发布包按它分（Windows 走 install.ps1，外层 #210）
target() {
  case "$(uname -s)-$(uname -m)" in
    Darwin-arm64) echo "aarch64-apple-darwin" ;;
    Darwin-x86_64) echo "x86_64-apple-darwin" ;;
    Linux-x86_64) echo "x86_64-unknown-linux-gnu" ;;
    Linux-aarch64 | Linux-arm64) echo "aarch64-unknown-linux-gnu" ;;
    *) die "uv" "$(uname -s) $(uname -m) 没有现成的安装包" ;;
  esac
}

# 下载 $1 到 $2 并和 CDN 上的 .sha256 对账，$3 是哪一项：对不上就停，不装半份
fetch() {
  curl -fsSL --retry 3 -o "$2" "$1" || die "$3" "取不到 $1"
  want=$(curl -fsSL --retry 3 "$1.sha256" | awk '{print $1}') || die "$3" "取不到 $1.sha256"
  if command -v sha256sum >/dev/null 2>&1; then
    got=$(sha256sum "$2" | awk '{print $1}')
  else
    got=$(shasum -a 256 "$2" | awk '{print $1}')
  fi
  [ "${got}" = "${want}" ] || die "$3" "$1 的 sha256 对不上，没装"
}

# uv 的环境：Python、平台本体、缓存都在家里，下载走国内源；装 Python 不往 ~/.local/bin 放入口
uv_home() {
  env UV_PYTHON_INSTALL_DIR="${TOOLS}/python" UV_PYTHON_INSTALL_MIRROR="${PYTHON_DOWNLOADS}" \
    UV_PYTHON_INSTALL_BIN=0 UV_DEFAULT_INDEX="${PYPI_INDEX}" UV_CACHE_DIR="${HOME_DIR}/cache/uv" \
    UV_TOOL_DIR="${TOOLS}/ai4sci" UV_TOOL_BIN_DIR="${BIN}" "${UV}" "$@"
}

# 找以前装在 uv 缺省位置的那份：工具目录用缺省的，缓存仍在家里
uv_default() {
  env UV_CACHE_DIR="${HOME_DIR}/cache/uv" "${UV}" "$@"
}

printf 'AAAI4S 安装（全程国内源）\n'
# 家的标记（同 framework/paths.py 的 mark）：新家、空家才放；指到一个已有东西的目录不放，清除就不认它
if [ ! -d "${HOME_DIR}" ] || [ -z "$(ls -A "${HOME_DIR}")" ]; then
  mkdir -p "${HOME_DIR}"
  printf 'ai4sci 的家（外层 #263）：清除只删有这个文件的目录。\n' > "${HOME_DIR}/.ai4sci-home"
fi
mkdir -p "${BIN}" "${TOOLS}"
work=$(mktemp -d)
trap 'rm -rf "${work}"' EXIT

# 1. uv：用户有就用他的；家里装过就用家里的；都没有从我们的 CDN 取
if command -v uv >/dev/null 2>&1; then
  UV=$(command -v uv)
  say "✓" "uv" "已装，跳过"
elif [ -x "${TOOLS}/uv/uv" ]; then
  UV="${TOOLS}/uv/uv"
  say "✓" "uv" "已装，跳过"
else
  triple=$(target)
  fetch "${DIST}/uv/${UV_VERSION}/uv-${triple}.tar.gz" "${work}/uv.tar.gz" uv
  mkdir -p "${TOOLS}/uv"
  tar -xzf "${work}/uv.tar.gz" -C "${work}"
  cp "${work}/uv-${triple}/uv" "${work}/uv-${triple}/uvx" "${TOOLS}/uv/"
  UV="${TOOLS}/uv/uv"
  say "✓" "uv" "${UV_VERSION}，下载完成"
fi

# 2. Python：有够版本的就用，没有装进家里
if found=$(uv_home python find "${PYTHON_WANTED}" 2>/dev/null); then
  say "✓" "Python" "$("${found}" -c 'import platform; print(platform.python_version())')，已装，跳过"
else
  uv_home python install "${PYTHON_INSTALL}" >>"${LOG}" 2>&1 || die "Python" "装不上，详情在 ${LOG}"
  say "✓" "Python" "${PYTHON_INSTALL}，下载完成"
fi

# 3. 平台：已是这一版就跳过；以前用 uv 装在缺省位置的先卸掉，不然终端里有两份 ai4sci（外层 #274）
if uv_default tool list 2>/dev/null | grep -q '^ai4sci '; then
  uv_default tool uninstall ai4sci >>"${LOG}" 2>&1 || die "ai4sci" "卸不掉以前的那份，详情在 ${LOG}"
  say "✓" "ai4sci" "卸掉了以前 uv 装在缺省位置的那份，换成家里这份"
fi
hash -r 2>/dev/null || true
old=$(command -v ai4sci 2>/dev/null || true)
if [ -n "${old}" ] && [ "${old}" != "${BIN}/ai4sci" ]; then
  say "!" "ai4sci" "${old} 不是 uv 装的，没动；终端里先找到的可能是它"
fi
if [ -x "${BIN}/ai4sci" ] && [ "$("${BIN}/ai4sci" --version 2>/dev/null)" = "ai4sci ${VERSION}" ]; then
  say "✓" "ai4sci" "${VERSION}，已装，跳过"
else
  wheel="ai4sci-${VERSION}-py3-none-any.whl"
  fetch "${DIST}/${VERSION}/${wheel}" "${work}/${wheel}" ai4sci
  uv_home tool install --force --python "${PYTHON_WANTED}" "${work}/${wheel}" >>"${LOG}" 2>&1 \
    || die "ai4sci" "装不上，详情在 ${LOG}"
  say "✓" "ai4sci" "${VERSION}，安装完成"
fi

# 4. PATH：新开的终端里敲得到 ai4sci；有了不重复加
case ":${PATH}:" in
  *":${BIN}:"*) ;;
  *)
    case "${SHELL:-}" in
      */zsh) rc="${HOME}/.zshrc" ;;
      */bash) [ "$(uname -s)" = Darwin ] && rc="${HOME}/.bash_profile" || rc="${HOME}/.bashrc" ;;
      *) rc="${HOME}/.profile" ;;
    esac
    shown="~/${rc#"${HOME}"/}"
    if grep -qs '# ai4sci$' "${rc}"; then
      say "✓" "PATH" "${shown} 里已经有了，新开的终端里生效"
    else
      printf '\nexport PATH="%s:${PATH}"  # ai4sci\n' "${BIN}" >> "${rc}"
      say "✓" "PATH" "写进了 ${shown}，新开的终端里敲 ai4sci 就能用"
    fi
    ;;
esac

# 5. 剩下的交给平台自己：PATH 带上 bin/（它给人的命令才是短短一个 ai4sci）；curl | sh 时标准输入
#    是脚本本身，问 key 要接回终端
PATH="${BIN}:${PATH}"
export PATH
if (: </dev/tty) 2>/dev/null; then
  exec "${BIN}/ai4sci" setup </dev/tty
fi
exec "${BIN}/ai4sci" setup
