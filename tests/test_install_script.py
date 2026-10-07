"""一行命令的 `install/install.sh` 与 Windows 的 `install/install.ps1`（外层 #277 / #210）：与
Python 那边是同一份事实、端到端照它装一遍。

端到端不连网：CDN 换成 tmp 下一棵 `file://` 的假目录（uv 的发布包是转调真 uv 的小脚本，平台的
wheel 是手搓的、`ai4sci` 只会报版本与回显参数），`HOME` 指到 tmp，PATH 只有系统目录与一个 Python。
真从 CDN 装的那一遍在发版后真跑。
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
                           "        print('ran ' + ' '.join(sys.argv[1:]) + said)\n"),
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
            body = f'#!/bin/sh\nexec "{REAL_UV}" "$@"\n'.encode()
            entry = tarfile.TarInfo(f"uv-{triple}/{tool}")
            entry.size, entry.mode = len(body), 0o755
            tar.addfile(entry, io.BytesIO(body))
    _sha(target)


def _run(script: Path, home: Path, dist: Path, extra_path: str = "") -> str:
    python_dir = str(Path(sys.executable).resolve().parent)  # 真解释器的目录：里面没有 uv
    # LANG 要是 UTF-8：Mac 的 /bin/sh 在 UTF-8 下会把 `$VAR，` 里全角逗号的头一个字节读进变量名
    # （2026-10-07 真从 CDN 装时撞上的），不带它测不出来
    env = {"HOME": str(home), "SHELL": "/bin/zsh", "AI4SCI_DIST": dist.as_uri(),
           "LANG": "en_US.UTF-8",
           "PATH": os.pathsep.join(p for p in (extra_path, python_dir, "/usr/bin", "/bin") if p)}
    done = subprocess.run(["sh", str(script)], env=env, capture_output=True, text=True,
                          encoding="utf-8", errors="replace",
                          stdin=subprocess.DEVNULL, timeout=300, check=False)
    assert done.returncode == 0, done.stdout + done.stderr
    return done.stdout


def _script(tmp_path: Path, version: str) -> Path:
    text = SCRIPT.read_text(encoding="utf-8").replace("__VERSION__", version)
    out = tmp_path / f"install-{version}.sh"
    out.write_text(text.replace("__UV_VERSION__", "0.0.0-test"), encoding="utf-8")
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


def _run_ps1(tmp_path: Path, version: str, home: Path, dist: Path) -> str:
    """照 `irm | iex` 的样子跑：脚本读成字符串交给 iex，执行策略 Restricted（研究者的电脑缺省
    就是）；用户的 Path 在注册表里，跑完原样还回去。"""
    import winreg

    script = tmp_path / f"install-{version}.ps1"
    script.write_text(PS1.read_text(encoding="utf-8").replace("__VERSION__", version)
                      .replace("__UV_VERSION__", "0.0.0-test"), encoding="utf-8")
    system = Path(os.environ["SystemRoot"])
    python_dir = Path(sys._base_executable).parent  # 有够版本的 Python：不去下
    env = {**{k: v for k, v in os.environ.items() if not k.startswith(("UV_", "AI4SCI_"))},
           "AI4SCI_HOME": str(home), "AI4SCI_DIST": dist.as_uri(),
           "PATH": os.pathsep.join([str(system / "System32"), str(system),
                                    str(system / "System32" / "WindowsPowerShell" / "v1.0"),
                                    str(python_dir)])}
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment", 0,
                        winreg.KEY_READ | winreg.KEY_WRITE) as key:
        saved = winreg.QueryValueEx(key, "Path")
        try:
            done = subprocess.run(
                ["powershell", "-NoProfile", "-ExecutionPolicy", "Restricted", "-Command",
                 f"Get-Content -Raw -Encoding UTF8 '{script}' | Invoke-Expression"],
                env=env, capture_output=True, stdin=subprocess.DEVNULL, timeout=600,
                check=False)
            path_now = winreg.QueryValueEx(key, "Path")[0]
        finally:
            winreg.SetValueEx(key, "Path", 0, saved[1], saved[0])
    out = done.stdout.decode("utf-8", "replace") + done.stderr.decode("utf-8", "replace")
    assert done.returncode == 0, out
    return out + f"\nPATH={path_now}"


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
