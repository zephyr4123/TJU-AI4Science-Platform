"""一行命令的 `install/install.sh` 与 Windows 的 `install/install.ps1`（外层 #277 / #210）：与
Python 那边是同一份事实、端到端照它装一遍。

端到端不连网：CDN 换成 tmp 下一棵 `file://` 的假目录（uv 的发布包是转调真 uv 的小脚本，平台的
wheel 是手搓的、`ai4sci` 只会报版本与回显参数），`HOME` 指到 tmp，PATH 只有系统目录与一个 Python。
真从 CDN 装的那一遍在发版后真跑。

桌面 App 起的那一种（外层 #282，`docs/specs/desktop.md` §3「装与升级」）：`AI4SCI_NO_SETUP=1` 不交给
setup、`AI4SCI_WHEEL_SHA256` 照签名清单核 wheel、平台还开着退 75、升级先暂存再离线换、太老的 uv
不用；Windows 上照外壳的样子用 `-File` 跑带 BOM 的一份、无窗口起，输出是 UTF-8。
"""

from __future__ import annotations

import base64
import hashlib
import io
import os
import platform
import re
import shutil
import subprocess
import sys
import tarfile
import zipfile
from pathlib import Path

import pytest

from framework import mirrors, paths
from framework.skills import run
from tests.fixtures.fake_cli import fake_cli

SCRIPT = Path(__file__).resolve().parents[1] / "install" / "install.sh"
PS1 = SCRIPT.with_name("install.ps1")
REAL_UV = shutil.which("uv") or str(Path(sys.executable).with_name("uv"))
TRIPLES = {("Darwin", "arm64"): "aarch64-apple-darwin", ("Darwin", "x86_64"): "x86_64-apple-darwin",
           ("Linux", "x86_64"): "x86_64-unknown-linux-gnu",
           ("Linux", "aarch64"): "aarch64-unknown-linux-gnu"}


def _var(name: str) -> str:
    found = re.search(rf'^{name}="([^"]*)"$', SCRIPT.read_text(encoding="utf-8"), re.M)
    assert found, f"install.sh 里没有 {name}"
    return found.group(1)


def _ps1_var(name: str) -> str:
    found = re.search(rf"^\${name} = '([^']*)'$", PS1.read_text(encoding="utf-8"), re.M)
    assert found, f"install.ps1 里没有 ${name}"
    return found.group(1)


def test_the_script_and_the_platform_agree_on_mirrors_and_places():
    assert _var("PYPI_INDEX") == mirrors.PYPI_INDEX
    assert _var("PYTHON_DOWNLOADS") == mirrors.PYTHON_DOWNLOADS
    assert _var("BIN") == f"${{HOME_DIR}}/{paths.BIN_DIRNAME}"
    assert _var("TOOLS") == f"${{HOME_DIR}}/{paths.TOOLS_DIRNAME}"
    text = SCRIPT.read_text(encoding="utf-8")
    assert f'UV_PYTHON_INSTALL_DIR="${{TOOLS}}/{paths.PYTHON_DIRNAME}"' in text
    assert f'UV_CACHE_DIR="${{HOME_DIR}}/{"/".join(paths.UV_CACHE_PARTS)}"' in text
    assert f'"${{HOME_DIR}}/{paths.MARKER_NAME}"' in text
    # Windows 那份同一份事实
    assert _ps1_var("PYPI_INDEX") == mirrors.PYPI_INDEX
    assert _ps1_var("PYTHON_DOWNLOADS") == mirrors.PYTHON_DOWNLOADS
    ps1 = PS1.read_text(encoding="utf-8")
    for name in (paths.BIN_DIRNAME, paths.TOOLS_DIRNAME, paths.PYTHON_DIRNAME, paths.MARKER_NAME,
                 "\\".join(paths.UV_CACHE_PARTS)):
        assert f"'{name}'" in ps1, name
    for name, value in run.PYTHON_STAYS_HOME.items():  # Python 不往家外面放东西
        assert f"{name} = '{value}'" in ps1, name


def test_both_scripts_keep_the_desktop_contract_the_same_way():
    """外壳只认一份约定（外层 #282，desktop.md §3）：两份脚本认同样的两个环境变量、「平台还开着」是
    同一个退出码、暂存在同一个目录。"""
    sh, ps1 = SCRIPT.read_text(encoding="utf-8"), PS1.read_text(encoding="utf-8")
    busy_sh = re.search(r"^EXIT_BUSY=(\d+)$", sh, re.M)
    busy_ps1 = re.search(r"^\$EXIT_BUSY = (\d+)$", ps1, re.M)
    assert busy_sh and busy_ps1 and busy_sh.group(1) == busy_ps1.group(1) == "75"
    assert 'STAGING="${TOOLS}/.ai4sci-staging"' in sh
    assert "$STAGING = Join-Path $TOOLS '.ai4sci-staging'" in ps1
    for name in ("AI4SCI_NO_SETUP", "AI4SCI_WHEEL_SHA256"):
        assert f"${{{name}" in sh and f"$env:{name}" in ps1, name


def _case_clashes(text: str) -> list[list[str]]:
    """PowerShell 的变量名不分大小写：写法不同的两个名字是同一个变量。"""
    names: dict[str, set[str]] = {}
    for name in re.findall(r"\$([A-Za-z_]\w*)", text):
        names.setdefault(name.lower(), set()).add(name)
    return sorted(sorted(spelled) for spelled in names.values() if len(spelled) > 1)


def test_install_ps1_has_no_two_variables_that_are_one():
    """`$tools = uv tool list` 曾悄悄盖掉 `$TOOLS`（家里的 tools 目录），后面一用就是空
    （外层 #210）。"""
    assert _case_clashes(PS1.read_text(encoding="utf-8")) == []
    assert _case_clashes("$TOOLS = 'a'\n$tools = uv tool list\n$BIN\n") == [["TOOLS", "tools"]]


# 5.1 里这几个是模块里的脚本函数，不是编进去的 cmdlet：从 pwsh（7）里再开 5.1 时会继承 7 的
# PSModulePath，这几个就加载不到（GitHub 的 runner 撞上的，人在 pwsh 窗口里敲 powershell 也一样）
SCRIPT_DEFINED_IN_51 = ("Get-FileHash", "Expand-Archive", "Compress-Archive", "New-TemporaryFile",
                        "New-Guid", "Format-Hex", "Import-PowerShellDataFile")


def test_install_ps1_only_uses_commands_built_into_51():
    code = "\n".join(line.split("#", 1)[0] for line in PS1.read_text(encoding="utf-8").splitlines())
    assert [name for name in SCRIPT_DEFINED_IN_51 if name in code] == []


def _sha(path: Path) -> None:
    path.with_name(path.name + ".sha256").write_text(
        f"{hashlib.sha256(path.read_bytes()).hexdigest()}  {path.name}\n", encoding="utf-8")


def _wheel(dist: Path, version: str) -> None:
    """一个最小的 ai4sci wheel：`--version` 报版本，别的参数原样回显。"""
    info = f"ai4sci-{version}.dist-info"
    files = {
        "ai4sci_fake.py": ("import os, shutil, sys\n\ndef main():\n"
                           "    if sys.argv[1:] == ['--version']:\n"
                           f"        print('ai4sci {version}')\n    else:\n"
                           "        found = os.path.splitext(shutil.which('ai4sci') or '')[0]\n"
                           "        on_path = os.path.normcase(found) == os.path.normcase(\n"
                           "            os.path.splitext(sys.argv[0])[0])\n"
                           "        said = ' on-path' if on_path else ''\n"
                           "        print('ran ' + ' '.join(sys.argv[1:]) + said)\n"
                           "        print('a log line', file=sys.stderr)\n"),  # 服务的日志走 stderr
        f"{info}/METADATA": f"Metadata-Version: 2.1\nName: ai4sci\nVersion: {version}\n",
        f"{info}/WHEEL": "Wheel-Version: 1.0\nGenerator: test\nRoot-Is-Purelib: true\n"
                         "Tag: py3-none-any\n",
        f"{info}/entry_points.txt": "[console_scripts]\nai4sci = ai4sci_fake:main\n",
    }
    record = []
    for name, body in files.items():
        digest = base64.urlsafe_b64encode(hashlib.sha256(body.encode()).digest()).rstrip(b"=")
        record.append(f"{name},sha256={digest.decode()},{len(body.encode())}")
    files[f"{info}/RECORD"] = "\n".join([*record, f"{info}/RECORD,,"]) + "\n"
    target = dist / version / f"ai4sci-{version}-py3-none-any.whl"
    target.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(target, "w") as whl:
        for name, body in files.items():
            whl.writestr(name, body)
    _sha(target)


def _uv_release(dist: Path, version: str) -> None:
    """uv 的发布包：`uv-<平台>/uv` 与 `uvx`，这里是转调真 uv 的小脚本。"""
    triple = TRIPLES[(platform.system(), platform.machine())]
    target = dist / "uv" / version / f"uv-{triple}.tar.gz"
    target.parent.mkdir(parents=True, exist_ok=True)
    with tarfile.open(target, "w:gz") as tar:
        for tool in ("uv", "uvx"):
            body = _uv_wrapper().encode()
            entry = tarfile.TarInfo(f"uv-{triple}/{tool}")
            entry.size, entry.mode = len(body), 0o755
            tar.addfile(entry, io.BytesIO(body))
    _sha(target)


def _uv_wrapper(fail_downloads: bool = False) -> str:
    """转调真 uv 的小脚本。`fail_downloads`：不带 --offline 的 `tool install` 先删掉它要装进的那个
    环境再失败——uv 删掉旧环境以后才下依赖，中途断网、被杀就是这个样子（外层 #282 审查）。"""
    broken = ('case " $* " in *" tool install "*) case " $* " in *" --offline "*) ;; *)\n'
              '  rm -rf "${UV_TOOL_DIR}/ai4sci"; echo "error: 下到一半断了" >&2; exit 2 ;; esac ;; '
              'esac\n') if fail_downloads else ""
    return f'#!/bin/sh\n{broken}exec "{REAL_UV}" "$@"\n'


def _sh(script: Path, home: Path, dist: Path, extra_path: str = "",
        **extra: str) -> subprocess.CompletedProcess:
    python_dir = str(Path(sys.executable).resolve().parent)  # 真解释器的目录：里面没有 uv
    # LANG 要是 UTF-8：Mac 的 /bin/sh 在 UTF-8 下会把 `$VAR，` 里全角逗号的头一个字节读进变量名
    # （2026-10-07 真从 CDN 装时撞上的），不带它测不出来
    env = {"HOME": str(home), "SHELL": "/bin/zsh", "AI4SCI_DIST": dist.as_uri(),
           "LANG": "en_US.UTF-8",
           "PATH": os.pathsep.join(p for p in (extra_path, python_dir, "/usr/bin", "/bin") if p),
           **extra}
    return subprocess.run(["sh", str(script)], env=env, capture_output=True, text=True,
                          encoding="utf-8", errors="replace",
                          stdin=subprocess.DEVNULL, timeout=300, check=False)


def _run(script: Path, home: Path, dist: Path, extra_path: str = "", **extra: str) -> str:
    done = _sh(script, home, dist, extra_path, **extra)
    assert done.returncode == 0, done.stdout + done.stderr
    return done.stdout


def _script(tmp_path: Path, version: str, uv: str = "0.0.0-test") -> Path:
    text = SCRIPT.read_text(encoding="utf-8").replace("__VERSION__", version)
    out = tmp_path / f"install-{version}.sh"
    out.write_text(text.replace("__UV_VERSION__", uv), encoding="utf-8")
    return out


@pytest.mark.skipif((platform.system(), platform.machine()) not in TRIPLES,
                    reason="install.sh 只管 Mac 与 Linux")
def test_install_sets_up_the_home_then_hands_over_and_a_rerun_skips(tmp_path):
    home, dist = tmp_path / "home", tmp_path / "dist"
    home.mkdir()
    _uv_release(dist, "0.0.0-test")
    for version in ("1.0.0", "1.0.1"):
        _wheel(dist, version)
    # 以前用 uv 装在缺省位置的一份（外层 #274 那位的样子）
    old = subprocess.run([REAL_UV, "tool", "install", str(dist / "1.0.0" /
                                                          "ai4sci-1.0.0-py3-none-any.whl")],
                         env={**os.environ, "HOME": str(home), "XDG_DATA_HOME": "",
                              "XDG_BIN_HOME": "", "UV_TOOL_DIR": "", "UV_TOOL_BIN_DIR": ""},
                         capture_output=True, text=True,
                         encoding="utf-8", errors="replace", check=False)
    assert old.returncode == 0, old.stderr
    local_bin = str(home / ".local" / "bin")

    out = _run(_script(tmp_path, "1.0.0"), home, dist, local_bin)
    ai4sci_home = home / ".ai4sci"
    assert "uv            0.0.0-test，下载完成" in out
    assert "ai4sci        卸掉了以前 uv 装在缺省位置的那份" in out
    assert "ai4sci        1.0.0，安装完成" in out
    # 交给平台自己，PATH 上已有 bin/：它给人的命令就是短短一个 ai4sci
    assert out.rstrip().endswith("ran setup on-path")
    assert (ai4sci_home / paths.MARKER_NAME).is_file()
    assert (ai4sci_home / paths.BIN_DIRNAME / "ai4sci").is_file()
    assert not (home / ".local" / "bin" / "ai4sci").exists()
    rc = home / ".zshrc"
    assert rc.read_text(encoding="utf-8").count("# ai4sci") == 1

    again = _run(_script(tmp_path, "1.0.0"), home, dist)
    assert "uv            已装，跳过" in again and "ai4sci        1.0.0，已装，跳过" in again
    assert rc.read_text(encoding="utf-8").count("# ai4sci") == 1  # PATH 那行不重复加

    newer = _run(_script(tmp_path, "1.0.1"), home, dist)
    assert "ai4sci        1.0.1，安装完成" in newer  # 重跑就是升级


@pytest.mark.skipif((platform.system(), platform.machine()) not in TRIPLES,
                    reason="install.sh 只管 Mac 与 Linux")
def test_a_fresh_install_writes_nothing_outside_the_home_but_the_path_line(tmp_path):
    """装出来的都在 `~/.ai4sci`，外面只有 shell 配置里那一行（主人 2026-10-07 手验时多出过
    `~/.cache/uv` 与 `~/.local/bin/python3.12`）。"""
    home, dist = tmp_path / "home", tmp_path / "dist"
    home.mkdir()
    _uv_release(dist, "0.0.0-test")
    _wheel(dist, "1.0.0")
    _run(_script(tmp_path, "1.0.0"), home, dist)
    assert sorted(p.name for p in home.iterdir()) == [".ai4sci", ".zshrc"]


@pytest.mark.skipif((platform.system(), platform.machine()) not in TRIPLES,
                    reason="install.sh 只管 Mac 与 Linux")
def test_a_tampered_download_stops_the_install(tmp_path):
    home, dist = tmp_path / "home", tmp_path / "dist"
    home.mkdir()
    _uv_release(dist, "0.0.0-test")
    _wheel(dist, "1.0.0")
    wheel = dist / "1.0.0" / "ai4sci-1.0.0-py3-none-any.whl"
    wheel.write_bytes(wheel.read_bytes() + b"x")  # 改了内容、没改 .sha256
    env = {"HOME": str(home), "SHELL": "/bin/zsh", "AI4SCI_DIST": dist.as_uri(),
           "LANG": "en_US.UTF-8",
           "PATH": os.pathsep.join([str(Path(sys.executable).resolve().parent), "/usr/bin",
                                    "/bin"])}
    done = subprocess.run(["sh", str(_script(tmp_path, "1.0.0"))], env=env, capture_output=True,
                          text=True, encoding="utf-8", errors="replace",
                          stdin=subprocess.DEVNULL, timeout=300, check=False)
    assert done.returncode == 1 and "sha256 对不上，没装" in done.stderr
    assert not (home / ".ai4sci" / paths.BIN_DIRNAME / "ai4sci").exists()


POSIX = pytest.mark.skipif((platform.system(), platform.machine()) not in TRIPLES,
                           reason="install.sh 只管 Mac 与 Linux")


def _installed(home: Path) -> str:
    exe = home / ".ai4sci" / paths.BIN_DIRNAME / "ai4sci"
    return subprocess.run([exe, "--version"], capture_output=True, text=True, encoding="utf-8",
                          check=False).stdout.strip()


@POSIX
def test_for_the_desktop_it_stops_before_setup_and_checks_the_wheel_by_the_signed_sha256(
        tmp_path):
    """桌面 App 自己起 setup（不问 key、不起服务，外层 #282）：`AI4SCI_NO_SETUP=1` 装好平台就退 0。
    wheel 照签名清单里的 sha256（`AI4SCI_WHEEL_SHA256`）核，不信 CDN 上的 .sha256：CDN 被改了，旁边
    那份 sha256 也能一起改。"""
    home, dist = tmp_path / "home", tmp_path / "dist"
    home.mkdir()
    _uv_release(dist, "0.0.0-test")
    _wheel(dist, "1.0.0")
    side = dist / "1.0.0" / "ai4sci-1.0.0-py3-none-any.whl.sha256"
    signed = side.read_text(encoding="utf-8").split()[0]
    side.write_text(f"{'0' * 64}  ai4sci-1.0.0-py3-none-any.whl\n", encoding="utf-8")
    out = _run(_script(tmp_path, "1.0.0"), home, dist, AI4SCI_NO_SETUP="1",
               AI4SCI_WHEEL_SHA256=signed.upper())
    assert "ai4sci        1.0.0，安装完成" in out and "ran setup" not in out
    assert _installed(home) == "ai4sci 1.0.0"

    side.write_text(f"{signed}  ai4sci-1.0.0-py3-none-any.whl\n", encoding="utf-8")
    _wheel(dist, "1.0.1")
    done = _sh(_script(tmp_path, "1.0.1"), home, dist, AI4SCI_NO_SETUP="1",
               AI4SCI_WHEEL_SHA256=signed)  # 1.0.0 的 sha256：对不上 1.0.1
    assert done.returncode == 1 and "sha256 对不上，没装" in done.stderr
    assert _installed(home) == "ai4sci 1.0.0"


@POSIX
def test_an_upgrade_while_the_platform_runs_is_refused_with_75_and_touches_nothing(tmp_path):
    """网页版服务、后台作业开着时换掉它们底下的代码，它们会读到半新半旧的文件（外层 #282）：Mac 也像
    Windows 那样先查、停下，退出码 75 让外壳分得清「被拒」与「失败」。不用装的时候不查。"""
    home, dist = tmp_path / "home", tmp_path / "dist"
    home.mkdir()
    _uv_release(dist, "0.0.0-test")
    for version in ("1.0.0", "1.0.1"):
        _wheel(dist, version)
    _run(_script(tmp_path, "1.0.0"), home, dist, AI4SCI_NO_SETUP="1")
    venv_python = next((home / ".ai4sci" / paths.TOOLS_DIRNAME / "ai4sci").rglob("bin/python"))
    running = subprocess.Popen([venv_python, "-c", "import time; time.sleep(120)"])
    try:
        done = _sh(_script(tmp_path, "1.0.1"), home, dist, AI4SCI_NO_SETUP="1")
        same = _sh(_script(tmp_path, "1.0.0"), home, dist, AI4SCI_NO_SETUP="1")
    finally:
        running.kill()
        running.wait()
    assert done.returncode == 75 and "平台还开着（1 个进程在用它）" in done.stderr
    assert _installed(home) == "ai4sci 1.0.0"
    assert same.returncode == 0 and "1.0.0，已装，跳过" in same.stdout
    assert "1.0.1，安装完成" in _run(_script(tmp_path, "1.0.1"), home, dist, AI4SCI_NO_SETUP="1")


@POSIX
def test_an_upgrade_that_breaks_halfway_leaves_the_old_platform_working(tmp_path):
    """uv 先删掉旧环境再下依赖：中途断网或被杀，原来能用的平台就没了（外层 #282 审查，uv 0.12.18
    `tool/install.rs`）。升级先装进暂存目录（下载都在这一步），成了再离线换进去。"""
    home, dist = tmp_path / "home", tmp_path / "dist"
    home.mkdir()
    _uv_release(dist, "0.0.0-test")
    for version in ("1.0.0", "1.0.1"):
        _wheel(dist, version)
    _run(_script(tmp_path, "1.0.0"), home, dist, AI4SCI_NO_SETUP="1")
    tools = home / ".ai4sci" / paths.TOOLS_DIRNAME
    (tools / "uv" / "uv").write_text(_uv_wrapper(fail_downloads=True), encoding="utf-8")
    done = _sh(_script(tmp_path, "1.0.1"), home, dist, AI4SCI_NO_SETUP="1")
    assert done.returncode == 1 and "原来那份照样能用" in done.stderr
    assert _installed(home) == "ai4sci 1.0.0"
    (tools / "uv" / "uv").write_text(_uv_wrapper(), encoding="utf-8")
    assert "1.0.1，安装完成" in _run(_script(tmp_path, "1.0.1"), home, dist, AI4SCI_NO_SETUP="1")
    assert _installed(home) == "ai4sci 1.0.1"
    assert sorted(p.name for p in tools.iterdir()) == ["ai4sci", "uv"]  # 暂存的不留


@POSIX
def test_a_uv_older_than_the_pinned_one_is_not_used(tmp_path):
    """外壳把它带的 uv 放在 PATH 最前，外壳又很少更新（外层 #282 审查）：PATH 上、家里的 uv 低于脚本
    钉的版本就当没有，取钉了版本的那份。"""
    home, dist = tmp_path / "home", tmp_path / "dist"
    home.mkdir()
    _uv_release(dist, "0.0.2-test")
    _wheel(dist, "1.0.0")
    stale = tmp_path / "stale"
    stale.mkdir()
    old_uv = '#!/bin/sh\n[ "$1" = --version ] && echo "uv 0.0.1" && exit 0\nexit 9\n'
    (stale / "uv").write_text(old_uv, encoding="utf-8")
    (stale / "uv").chmod(0o755)
    script = _script(tmp_path, "1.0.0", uv="0.0.2-test")
    out = _run(script, home, dist, str(stale), AI4SCI_NO_SETUP="1")
    assert "uv            0.0.2-test，下载完成" in out
    mine = home / ".ai4sci" / paths.TOOLS_DIRNAME / "uv" / "uv"
    mine.write_text(old_uv, encoding="utf-8")
    assert "uv            0.0.2-test，下载完成" in _run(script, home, dist, AI4SCI_NO_SETUP="1")
    assert "uv            已装，跳过" in _run(script, home, dist, AI4SCI_NO_SETUP="1")


# ── Windows：install.ps1 ───────────────────────────────────────────────────────


def _uv_release_windows(dist: Path, version: str) -> None:
    """uv 的 Windows 发布包：zip 根上是 uv.exe（这里放平台 venv 里那份真的）。"""
    target = dist / "uv" / version / "uv-x86_64-pc-windows-msvc.zip"
    target.parent.mkdir(parents=True, exist_ok=True)
    real = Path(REAL_UV)
    with zipfile.ZipFile(target, "w") as archive:
        for tool in ("uv.exe", "uvx.exe"):
            if real.with_name(tool).is_file():
                archive.write(real.with_name(tool), tool)
    _sha(target)


def _ps1_script(tmp_path: Path, version: str, uv: str = "0.0.0-test", bom: bool = False) -> Path:
    """代入版本的一份；`bom`：桌面 App 存成带 UTF-8 BOM 的文件再 `-File` 起（外层 #282）。"""
    script = tmp_path / f"install-{version}.ps1"
    text = PS1.read_text(encoding="utf-8").replace("__VERSION__", version)
    script.write_text(("\ufeff" if bom else "") + text.replace("__UV_VERSION__", uv),
                      encoding="utf-8")
    return script


def _ps1_env(home: Path, dist: Path, extra_path: str = "", **extra: str) -> dict[str, str]:
    system = Path(os.environ["SystemRoot"])
    python_dir = Path(sys._base_executable).parent  # 有够版本的 Python：不去下
    return {**{k: v for k, v in os.environ.items() if not k.startswith(("UV_", "AI4SCI_"))},
            "AI4SCI_HOME": str(home), "AI4SCI_DIST": dist.as_uri(),
            "PATH": os.pathsep.join(p for p in (
                extra_path, str(system / "System32"), str(system),
                str(system / "System32" / "WindowsPowerShell" / "v1.0"), str(python_dir)) if p),
            **extra}


def _keeping_user_path(run):
    """用户的 Path 在注册表里：脚本会往里加 bin\\，跑完原样还回去；返回跑的结果与跑完时的 Path。"""
    import winreg

    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment", 0,
                        winreg.KEY_READ | winreg.KEY_WRITE) as key:
        saved = winreg.QueryValueEx(key, "Path")
        try:
            done = run()
            return done, winreg.QueryValueEx(key, "Path")[0]
        finally:
            winreg.SetValueEx(key, "Path", 0, saved[1], saved[0])


def _run_ps1(tmp_path: Path, version: str, home: Path, dist: Path) -> str:
    """照 `irm | iex` 的样子跑：脚本读成字符串交给 iex，执行策略 Restricted（研究者的电脑缺省
    就是）；用户的 Path 在注册表里，跑完原样还回去。stderr 并进来（`2>&1`）：ISE、存日志的
    `| Tee-Object` 都这样，5.1 在这种宿主里把原生程序写 stderr 当错误，最严的情形一起测。"""
    script = _ps1_script(tmp_path, version)
    done, path_now = _keeping_user_path(lambda: subprocess.run(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Restricted", "-Command",
         f"& {{ Get-Content -Raw -Encoding UTF8 '{script}' | Invoke-Expression }} 2>&1 "
         "| ForEach-Object { \"$_\" }"],
        env=_ps1_env(home, dist), capture_output=True, stdin=subprocess.DEVNULL, timeout=600,
        check=False))
    out = done.stdout.decode("utf-8", "replace") + done.stderr.decode("utf-8", "replace")
    assert done.returncode == 0, out
    return out + f"\nPATH={path_now}"


def _run_ps1_as_desktop(script: Path, home: Path, dist: Path, extra_path: str = "",
                        **extra: str) -> subprocess.CompletedProcess:
    """照桌面 App 起的样子（外层 #282，desktop.md §3）：带 BOM 的一份、5.1 的完整路径、`-File`、
    无窗口（CREATE_NO_WINDOW）、标准输入接管道（接 NUL 时 isatty 是真）、`AI4SCI_NO_SETUP=1`。
    stdout 按 UTF-8 严格解：解不开就是又按 GBK 出了。"""
    powershell = (Path(os.environ["SystemRoot"]) / "System32" / "WindowsPowerShell" / "v1.0"
                  / "powershell.exe")
    env = _ps1_env(home, dist, extra_path, AI4SCI_NO_SETUP="1", **extra)
    done, _ = _keeping_user_path(lambda: subprocess.run(
        [str(powershell), "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File",
         str(script)], env=env, capture_output=True, input=b"", timeout=600, check=False,
        creationflags=subprocess.CREATE_NO_WINDOW))
    return subprocess.CompletedProcess(done.args, done.returncode, done.stdout.decode("utf-8"),
                                       done.stderr.decode("utf-8", "replace"))


@pytest.mark.skipif(sys.platform != "win32", reason="install.ps1 只管 Windows")
def test_install_ps1_sets_up_the_home_then_hands_over_and_a_rerun_skips(tmp_path):
    home, dist = tmp_path / "home", tmp_path / "dist"
    _uv_release_windows(dist, "0.0.0-test")
    for version in ("1.0.0", "1.0.1"):
        _wheel(dist, version)
    out = _run_ps1(tmp_path, "1.0.0", home, dist)
    assert "uv            0.0.0-test，下载完成" in out and "已装，跳过" in out  # Python 用现成的
    assert "ai4sci        1.0.0，安装完成" in out
    assert "ran setup on-path" in out  # 交给平台自己，这个窗口里 bin\ 已在 PATH 上
    assert (home / paths.MARKER_NAME).is_file()
    assert (home / paths.BIN_DIRNAME / "ai4sci.exe").is_file()
    assert str(home / paths.BIN_DIRNAME) in out.split("PATH=")[-1].split(";")
    again = _run_ps1(tmp_path, "1.0.0", home, dist)
    assert "uv            已装，跳过" in again and "ai4sci        1.0.0，已装，跳过" in again
    newer = _run_ps1(tmp_path, "1.0.1", home, dist)
    assert "ai4sci        1.0.1，安装完成" in newer  # 重跑就是升级
    assert sorted(p.name for p in home.iterdir()) == sorted(
        [paths.MARKER_NAME, paths.BIN_DIRNAME, paths.TOOLS_DIRNAME, "cache", "install.log"])


@pytest.mark.skipif(sys.platform != "win32", reason="install.ps1 只管 Windows")
def test_install_ps1_stops_on_a_tampered_download_without_closing_the_window(tmp_path):
    """对不上 sha256 就停、不装半份；`irm | iex` 跑在人自己的会话里，停也不 exit（会关掉他的
    窗口）。"""
    home, dist = tmp_path / "home", tmp_path / "dist"
    _uv_release_windows(dist, "0.0.0-test")
    _wheel(dist, "1.0.0")
    wheel = dist / "1.0.0" / "ai4sci-1.0.0-py3-none-any.whl"
    wheel.write_bytes(wheel.read_bytes() + b"x")
    out = _run_ps1(tmp_path, "1.0.0", home, dist)
    assert "sha256 对不上，没装" in out and "没装完" in out
    assert not (home / paths.BIN_DIRNAME / "ai4sci.exe").exists()


@pytest.mark.skipif(sys.platform != "win32", reason="install.ps1 只管 Windows")
def test_install_ps1_refuses_to_upgrade_while_the_platform_runs(tmp_path):
    """Windows 上在跑的程序换不掉：服务开着时重跑，uv 先删了 site-packages 才在 Scripts\\ 上
    拒绝访问，留下一份谁都起不来的安装（外层 #210 真机撞上的）。动文件之前先查、停下说清楚。"""
    home, dist = tmp_path / "home", tmp_path / "dist"
    _uv_release_windows(dist, "0.0.0-test")
    for version in ("1.0.0", "1.0.1"):
        _wheel(dist, version)
    _run_ps1(tmp_path, "1.0.0", home, dist)
    venv_python = next((home / paths.TOOLS_DIRNAME).rglob("Scripts/python.exe"))
    running = subprocess.Popen([venv_python, "-c", "import time; time.sleep(120)"])
    try:
        out = _run_ps1(tmp_path, "1.0.1", home, dist)
    finally:
        running.kill()
        running.wait()
    assert "平台还开着" in out and "没装完" in out
    exe = home / paths.BIN_DIRNAME / "ai4sci.exe"
    still = subprocess.run([exe, "--version"], capture_output=True, text=True, encoding="utf-8",
                           check=False)
    assert still.stdout.strip() == "ai4sci 1.0.0"  # 旧的那份原样能用
    assert "ai4sci        1.0.1，安装完成" in _run_ps1(tmp_path, "1.0.1", home, dist)


@pytest.mark.skipif(sys.platform != "win32", reason="install.ps1 只管 Windows")
def test_install_ps1_repairs_a_broken_install(tmp_path):
    """装坏的那份 `--version` 往 stderr 写 traceback：PowerShell 5.1 在 Stop 下会当异常抛，重跑就修
    不了（外层 #210 真机撞上的）。坏了就当没装，照装。"""
    home, dist = tmp_path / "home", tmp_path / "dist"
    _uv_release_windows(dist, "0.0.0-test")
    _wheel(dist, "1.0.0")
    _run_ps1(tmp_path, "1.0.0", home, dist)
    next((home / paths.TOOLS_DIRNAME).rglob("ai4sci_fake.py")).unlink()
    assert "ai4sci        1.0.0，安装完成" in _run_ps1(tmp_path, "1.0.0", home, dist)


def _version_of(home: Path) -> str:
    return subprocess.run([home / paths.BIN_DIRNAME / "ai4sci.exe", "--version"],
                          capture_output=True, text=True, encoding="utf-8",
                          check=False).stdout.strip()


@pytest.mark.skipif(sys.platform != "win32", reason="install.ps1 只管 Windows")
def test_install_ps1_runs_the_way_the_desktop_app_starts_it(tmp_path):
    """桌面 App 起它（外层 #282）：无 BOM 时 5.1 按 GBK 读源码，整段读坏；无窗口起的 Write-Host 按
    GBK 出、✓ 成了 ?；失败也退 0，外壳分不出装好没有。带 BOM 的一份 + -File + 无窗口：输出是 UTF-8，
    退出码作数——0 装好、75 平台还开着、1 失败；wheel 照签名清单的 sha256 核；升级中途断了原来那份
    照样能用。"""
    home, dist = tmp_path / "home", tmp_path / "dist"
    _uv_release_windows(dist, "0.0.0-test")
    for version in ("1.0.0", "1.0.1"):
        _wheel(dist, version)
    side = dist / "1.0.0" / "ai4sci-1.0.0-py3-none-any.whl.sha256"
    signed = side.read_text(encoding="utf-8").split()[0]
    side.write_text(f"{'0' * 64}  ai4sci-1.0.0-py3-none-any.whl\n", encoding="utf-8")
    first = _ps1_script(tmp_path, "1.0.0", bom=True)
    done = _run_ps1_as_desktop(first, home, dist, AI4SCI_WHEEL_SHA256=signed)
    assert done.returncode == 0, done.stdout + done.stderr
    assert not done.stdout.startswith("\ufeff") and "?" not in done.stdout
    assert "  ✓ ai4sci        1.0.0，安装完成" in done.stdout and "ran setup" not in done.stdout
    assert _version_of(home) == "ai4sci 1.0.0"

    newer = _ps1_script(tmp_path, "1.0.1", bom=True)
    done = _run_ps1_as_desktop(newer, home, dist, AI4SCI_WHEEL_SHA256=signed)
    assert done.returncode == 1 and "sha256 对不上，没装" in done.stdout

    venv_python = next((home / paths.TOOLS_DIRNAME).rglob("Scripts/python.exe"))
    running = subprocess.Popen([venv_python, "-c", "import time; time.sleep(120)"])
    try:
        done = _run_ps1_as_desktop(newer, home, dist)
    finally:
        running.kill()
        running.wait()
    assert done.returncode == 75 and "平台还开着（1 个进程在用它）" in done.stdout

    uv_dir = home / paths.TOOLS_DIRNAME / "uv"
    fake_cli(uv_dir / "uv", f"""import os, shutil, subprocess, sys
args = sys.argv[1:]
if args[:2] == ["tool", "install"] and "--offline" not in args:
    shutil.rmtree(os.path.join(os.environ["UV_TOOL_DIR"], "ai4sci"), ignore_errors=True)
    print("error: 下到一半断了", file=sys.stderr)
    sys.exit(2)
sys.exit(subprocess.run([{REAL_UV!r}, *args]).returncode)
""")
    done = _run_ps1_as_desktop(newer, home, dist)
    assert done.returncode == 1 and "原来那份照样能用" in done.stdout
    assert _version_of(home) == "ai4sci 1.0.0"

    shutil.copyfile(Path(REAL_UV).with_suffix(".exe"), uv_dir / "uv.exe")
    done = _run_ps1_as_desktop(newer, home, dist)
    assert done.returncode == 0 and "1.0.1，安装完成" in done.stdout
    assert _version_of(home) == "ai4sci 1.0.1"
    assert sorted(p.name for p in (home / paths.TOOLS_DIRNAME).iterdir()) == ["ai4sci", "uv"]


@pytest.mark.skipif(sys.platform != "win32", reason="install.ps1 只管 Windows")
def test_install_ps1_does_not_use_a_uv_older_than_the_pinned_one(tmp_path):
    """外壳把它带的 uv 放在 PATH 最前，外壳又很少更新（外层 #282 审查）：低于钉的版本就当没有。"""
    home, dist = tmp_path / "home", tmp_path / "dist"
    _uv_release_windows(dist, "0.0.2-test")
    _wheel(dist, "1.0.0")
    stale = tmp_path / "stale"
    stale.mkdir()
    old_uv = 'import sys\nprint("uv 0.0.1") if sys.argv[1:] == ["--version"] else sys.exit(9)\n'
    fake_cli(stale / "uv", old_uv)
    script = _ps1_script(tmp_path, "1.0.0", uv="0.0.2-test", bom=True)
    done = _run_ps1_as_desktop(script, home, dist, str(stale))
    assert done.returncode == 0 and "uv            0.0.2-test，下载完成" in done.stdout
