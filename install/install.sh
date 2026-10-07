#!/bin/sh
# AAAI4S 一行命令安装（外层 #277）：
#
#     curl -fsSL https://media.zephyrxiang.com/ai4science/dist/install.sh | sh
#
# 只做 Python 还没有时非做不可的事：装 uv、装平台，然后交给 `ai4sci setup`（查 git、装两家 CLI、
# 问 key、起服务）。全程国内源；每一项先查，装过的跳过；重跑就是升级。装出来的都在平台的家里
# （~/.ai4sci），落在外面的只有 shell 配置里一行 PATH。
#
# 桌面 App 也跑这一份（外层 #282，docs/specs/desktop.md §3「装与升级」，只加不改）：
# AI4SCI_NO_SETUP=1 装好平台就退、不交给 setup；AI4SCI_WHEEL_SHA256 是签名清单里 wheel 的 sha256，
# 给了就照它核、不信 CDN 上的 .sha256。退出码 0 装好；75 平台还开着（有进程在用家里的平台），什么都
# 没动；其余是失败。升级先装进暂存目录（下载都在这一步），成了再离线换进去：中途断了，原来那份照样
# 能用。
#
# 下面的地址与目录名和 framework/mirrors.py、framework/paths.py 是同一份事实，
# tests/test_install_script.py 对账。__VERSION__ 这类占位由发版流水线写进去（.github/scripts/cdn.py）：
# 版本是 PEP 440 的写法，与 `ai4sci --version`、wheel 的文件名、CDN 上的目录一样（rc 写成 1.9.0rc1）。
set -eu
# 变量一律带花括号：Mac 的 /bin/sh 在 UTF-8 下会把 `$VAR，` 里全角逗号的头一个字节读进变量名

VERSION="__VERSION__"
UV_VERSION="__UV_VERSION__"
# uv 发布包的 sha256（`<平台>=<sha256>`，空格分隔）：发版时照 GitHub 上核过的写进来。这份脚本由签名
# 清单盖着（外层 #282），uv 也就跟着在签名链里，不信 CDN 上它旁边那份 .sha256
UV_SHA256="__UV_SHA256__"
DIST="${AI4SCI_DIST:-https://media.zephyrxiang.com/ai4science/dist}"
PYPI_INDEX="https://mirrors.tuna.tsinghua.edu.cn/pypi/web/simple"
PYTHON_DOWNLOADS="https://registry.npmmirror.com/-/binary/python-build-standalone"
PYTHON_WANTED=">=3.12"
PYTHON_INSTALL="3.12"
HOME_DIR="${AI4SCI_HOME:-${HOME}/.ai4sci}"
BIN="${HOME_DIR}/bin"
TOOLS="${HOME_DIR}/tools"
LOG="${HOME_DIR}/install.log"
STAGING="${TOOLS}/.ai4sci-staging"
EXIT_BUSY=75

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

# 版本 $1 不低于 $2：X.Y.Z 逐段比数字（-test 这类尾巴不算）
at_least() {
  awk -v have="$1" -v want="$2" 'BEGIN {
    split(have, h, "."); split(want, w, ".")
    for (i = 1; i <= 3; i++) if (h[i] + 0 != w[i] + 0) exit !(h[i] + 0 > w[i] + 0)
    exit 0 }'
}

# 下载：连不上 15 秒就算，连着 60 秒每秒不到 1 KB 就当卡住（连接还在、数据不来），不干等
get() { curl -fsSL --retry 3 --connect-timeout 15 --speed-limit 1024 --speed-time 60 "$@"; }

# 下载 $1 到 $2，$3 是哪一项；sha256 照 $4（签名清单里的、脚本里写好的）核，没给就照 CDN 上旁边的
# .sha256：对不上就停，不装半份
fetch() {
  get -o "$2" "$1" || die "$3" "取不到 $1"
  want=$(printf '%s' "${4:-}" | tr 'A-F' 'a-f')
  if [ -z "${want}" ]; then
    want=$(get "$1.sha256" | awk '{print $1}') || die "$3" "取不到 $1.sha256"
  fi
  if command -v sha256sum >/dev/null 2>&1; then
    got=$(sha256sum "$2" | awk '{print $1}')
  else
    got=$(shasum -a 256 "$2" | awk '{print $1}')
  fi
  [ "${got}" = "${want}" ] || die "$3" "$1 的 sha256 对不上，没装"
}

# uv 的环境：Python、平台本体、缓存都在家里，下载走国内源；装 Python 不往 ~/.local/bin 放入口。
# 平台装进 $1（工具目录）与 $2（入口目录）：平时是家里的，升级时先是暂存的
uv_into() {
  tool_dir=$1 tool_bin=$2
  shift 2
  env UV_PYTHON_INSTALL_DIR="${TOOLS}/python" UV_PYTHON_INSTALL_MIRROR="${PYTHON_DOWNLOADS}" \
    UV_PYTHON_INSTALL_BIN=0 UV_DEFAULT_INDEX="${PYPI_INDEX}" UV_CACHE_DIR="${HOME_DIR}/cache/uv" \
    UV_TOOL_DIR="${tool_dir}" UV_TOOL_BIN_DIR="${tool_bin}" "${UV}" "$@"
}
uv_home() { uv_into "${TOOLS}/ai4sci" "${BIN}" "$@"; }

# 够版本的 uv：低于钉的版本（外壳带的那份会变老）当没有
uv_ok() {
  [ -x "$1" ] && at_least "$("$1" --version 2>/dev/null | awk '{print $2}')" "${UV_VERSION}"
}

# 平台还开着：跑的就是家里这份平台的进程（网页版服务、后台作业、助理的会话），不算自己。在跑的程序
# 底下换代码，它们会读到半新半旧的文件。只认程序本身：命令行以家里的平台开头（venv 的 python、bin 里
# 的 ai4sci），或者是一个 python 跑家里的平台；参数里提到家里文件的（tail、编辑器）不算。Mac 上平台若
# 跑在 Homebrew 这类 framework 构建的 Python 上，它一启动就把自己 re-exec 成 Python.app 里那个路径，
# `python -m` 起的命令行里就看不到家；它的环境里留着 __PYVENV_LAUNCHER__=<家里的 python>，所以 Mac 上
# 连环境一起看（-E）。环境里常有 export 的 key：直接接给 awk、不落盘
busy() {
  flags="-A"
  [ "$(uname -s)" = Darwin ] && flags="-A -E"
  # shellcheck disable=SC2086
  ps ${flags} -o pid= -o args= 2>/dev/null | SELF=$$ A="${TOOLS}/ai4sci/" B="${BIN}/ai4sci" awk '
    function home(s) { return index(s, ENVIRON["A"]) == 1 || index(s, ENVIRON["B"]) == 1 }
    $1 == ENVIRON["SELF"] { next }
    {
      line = substr($0, index($0, $2))
      first = $2; sub(/.*\//, "", first)
      if (home(line) || (first ~ /^[Pp]ython/ && home(substr(line, length($2) + 2))) ||
          index($0, " __PYVENV_LAUNCHER__=" ENVIRON["A"])) n++
    }
    END { print n + 0 }'
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
trap 'rm -rf "${work}" "${STAGING}"' EXIT

# 1. uv：用户有就用他的；家里装过就用家里的；都没有、或都低于钉的版本，从我们的 CDN 取
if uv_ok "$(command -v uv 2>/dev/null || true)"; then
  UV=$(command -v uv)
  say "✓" "uv" "已装，跳过"
elif uv_ok "${TOOLS}/uv/uv"; then
  UV="${TOOLS}/uv/uv"
  say "✓" "uv" "已装，跳过"
else
  triple=$(target)
  signed=$(echo "${UV_SHA256}" | tr ' ' '\n' | awk -F= -v t="${triple}" '$1 == t { print $2 }')
  [ -n "${signed}" ] || die "uv" "这份安装脚本里没有 ${triple} 的 uv 的 sha256"
  fetch "${DIST}/uv/${UV_VERSION}/uv-${triple}.tar.gz" "${work}/uv.tar.gz" uv "${signed}"
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
  running=$(busy)
  if [ "${running}" -gt 0 ]; then
    say "✗" "ai4sci" "平台还开着（${running} 个进程在用它）：关掉服务的窗口，作业在跑就等它跑完或在页面上停掉" >&2
    exit "${EXIT_BUSY}"
  fi
  wheel="ai4sci-${VERSION}-py3-none-any.whl"
  fetch "${DIST}/${VERSION}/${wheel}" "${work}/${wheel}" ai4sci "${AI4SCI_WHEEL_SHA256:-}"
  if [ -d "${TOOLS}/ai4sci" ]; then
    # 升级：uv 先删掉旧环境再下依赖，中途断了原来那份就没了。先装进暂存目录，下载都在这一步、旧的
    # 不动；成了再从缓存离线换进去（真 wheel 实测不到一秒）
    rm -rf "${STAGING}"
    uv_into "${STAGING}/tools" "${STAGING}/bin" tool install --force --python "${PYTHON_WANTED}" \
      "${work}/${wheel}" >>"${LOG}" 2>&1 \
      || die "ai4sci" "${VERSION} 没装上，原来那份照样能用；详情在 ${LOG}"
    rm -rf "${STAGING}"
    uv_home tool install --force --offline --python "${PYTHON_WANTED}" "${work}/${wheel}" \
      >>"${LOG}" 2>&1 || die "ai4sci" "装不上，详情在 ${LOG}"
  else
    uv_home tool install --force --python "${PYTHON_WANTED}" "${work}/${wheel}" >>"${LOG}" 2>&1 \
      || die "ai4sci" "装不上，详情在 ${LOG}"
  fi
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
#    是脚本本身，问 key 要接回终端。桌面 App 自己起 setup（不问 key、不起服务），到这里就算装好
rm -rf "${work}"  # exec 之后 EXIT 的 trap 不跑
if [ "${AI4SCI_NO_SETUP:-}" = 1 ]; then
  exit 0
fi
PATH="${BIN}:${PATH}"
export PATH
if (: </dev/tty) 2>/dev/null; then
  exec "${BIN}/ai4sci" setup </dev/tty
fi
exec "${BIN}/ai4sci" setup
