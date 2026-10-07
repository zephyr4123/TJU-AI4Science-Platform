"""一行命令的 `install/install.sh`（外层 #277）：与 Python 那边是同一份事实、端到端照它装一遍。

端到端不连网：CDN 换成 tmp 下一棵 `file://` 的假目录（uv 的发布包是转调真 uv 的小脚本，平台的
wheel 是手搓的、`ai4sci` 只会报版本与回显参数），`HOME` 指到 tmp，PATH 只有系统目录与一个 Python。
真从 CDN 装的那一遍在发版后真跑。
"""

from __future__ import annotations

import base64
import hashlib
import io
import os
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
REAL_UV = shutil.which("uv") or str(Path(sys.executable).with_name("uv"))
TRIPLES = {("Darwin", "arm64"): "aarch64-apple-darwin", ("Darwin", "x86_64"): "x86_64-apple-darwin",
           ("Linux", "x86_64"): "x86_64-unknown-linux-gnu",
           ("Linux", "aarch64"): "aarch64-unknown-linux-gnu"}


def _var(name: str) -> str:
    found = re.search(rf'^{name}="([^"]*)"$', SCRIPT.read_text(encoding="utf-8"), re.M)
    assert found, f"install.sh 里没有 {name}"
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
                           "        on_path = shutil.which('ai4sci') == sys.argv[0]\n"
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
    triple = TRIPLES[(os.uname().sysname, os.uname().machine)]
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
                          stdin=subprocess.DEVNULL, timeout=300, check=False)
    assert done.returncode == 0, done.stdout + done.stderr
    return done.stdout


def _script(tmp_path: Path, version: str) -> Path:
    text = SCRIPT.read_text(encoding="utf-8").replace("__VERSION__", version)
    out = tmp_path / f"install-{version}.sh"
    out.write_text(text.replace("__UV_VERSION__", "0.0.0-test"), encoding="utf-8")
    return out


@pytest.mark.skipif((os.uname().sysname, os.uname().machine) not in TRIPLES,
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
                         capture_output=True, text=True, check=False)
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
                          text=True, stdin=subprocess.DEVNULL, timeout=300, check=False)
    assert done.returncode == 1 and "sha256 对不上，没装" in done.stderr
    assert not (home / ".ai4sci" / paths.BIN_DIRNAME / "ai4sci").exists()
