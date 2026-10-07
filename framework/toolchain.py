"""两家 CLI 装在平台的家里：认、下载、校验、解包（外层 #277 onboarding）。

主人 2026-10-07：全程国内源、装过就跳过，Claude Code 与 Codex 由命令装好，不让人去页面上点。两家的
原生程序都按平台单独发在 npm 上，npmmirror 与 npmjs 同版本、不要 Node（2026-10-07 实测），所以
这里不装 Node、不跑 npm：照适配器的 `Install`（主包、程序在哪个包里、包里哪一块要留下）直接取 tgz，
按 npm 元数据里的 sha512 校验，解进 `tools/<名字>/`，旁边留一张收据（`RECEIPT`：版本、程序在哪、
从哪来）。
哪家是什么包只在适配器里（框架里不出现某家 CLI 的名字）；这里是两家共用的一份。

装过的判据（`find`）：家里那份、没有再看 PATH 上那份，`--version` 认得出、不低于适配器的
`min_version`。平台起 CLI 时用家里那份（`agents.link` 经 `Link.cli` 交给适配器），没有才用
PATH 上的。
"""

from __future__ import annotations

import base64
import hashlib
import json
import logging
import os
import platform
import shutil
import subprocess
import sys
import tarfile
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import backends
from framework import mirrors, paths

LOGGER = logging.getLogger("ai4sci.toolchain")
RECEIPT = "installed.json"
FETCH_TIMEOUT_S = 60
VERSION_TIMEOUT_S = 30
_CHUNK = 1 << 20
_SYSTEMS = {"darwin": "darwin", "linux": "linux", "win32": "win32"}
_MACHINES = {"arm64": "arm64", "aarch64": "arm64", "x86_64": "x64", "amd64": "x64"}

# 下载进度：已下字节、总字节（服务器没给长度是 None）
Progress = Callable[[int, int | None], None]


class ToolchainError(RuntimeError):
    """取不到、校验不过、解出来跑不起来：一句给人看的话，带上地址与原因。"""


@dataclass(frozen=True)
class Found:
    """一家 CLI 现在是哪一份：程序、`--version` 的原文、够不够平台要求、是不是家里装的。"""

    exe: str
    version: str
    ok: bool
    private: bool


def platform_key(system: str = sys.platform, machine: str = platform.machine()) -> str:
    """npm 写法的平台名（`darwin-arm64`、`win32-x64`）：两家程序包按它分。"""
    os_name, arch = _SYSTEMS.get(system), _MACHINES.get(machine.lower())
    if os_name is None or arch is None:
        raise ToolchainError(f"这台机器（{system} {machine}）没有现成的程序包")
    return f"{os_name}-{arch}"


def private_cli(name: str) -> Path | None:
    """家里装的那份程序：收据在、程序也在就是它，否则 None。只读收据、不起进程：每起一次会话
    都要问一遍。"""
    root = paths.tools_dir() / name
    try:
        entry = json.loads((root / RECEIPT).read_text(encoding="utf-8"))["entry"]
    except FileNotFoundError:
        return None
    except (ValueError, KeyError, TypeError) as exc:  # 收据坏了：当没装，`ai4sci setup` 会重装
        LOGGER.warning("cli_receipt_unreadable backend=%s why=%s", name, exc)
        return None
    exe = root / str(entry)
    return exe if exe.is_file() else None


def find(name: str) -> Found | None:
    """现在能用的是哪一份：家里的优先，没有再看 PATH；都没有是 None。

    Windows 上 PATH 里 npm 装的是 `claude.cmd` 这类壳（外层 #210）：起它要过 cmd.exe，参数里的引号、
    换行会被改写，平台只起原生的 exe，所以认作不够用、`ai4sci setup` 装一份进家里。"""
    spec = backends.install_of(name)
    candidates = [(private_cli(name), True)]
    if (hit := shutil.which(spec.command)) is not None:
        candidates.append((Path(hit), False))
    for exe, private in candidates:
        if exe is not None and sys.platform == "win32" and exe.suffix.lower() != ".exe":
            return Found(exe=str(exe), version="", ok=False, private=private)
        if exe is not None:
            raw = _version(exe)
            parsed = spec.parse_version(raw)
            return Found(exe=str(exe), version=raw, private=private,
                         ok=parsed is not None and parsed >= spec.min_version)
    return None


def latest(name: str) -> str:
    """npmmirror 上这家主包的最新版本号。"""
    spec = backends.install_of(name)
    return str(_json(f"{mirrors.NPM_REGISTRY}/{spec.npm}/latest")["version"])


def install(name: str, progress: Progress | None = None) -> Found:
    """取最新版装进 `tools/<名字>/`：下到临时目录、校验、解包、跑一次 `--version`，都过了才换上去；
    哪一步不过就抛 ToolchainError，原来那份不动。"""
    spec = backends.install_of(name)
    version = latest(name)
    dist = spec.dist(platform_key(), version)
    meta = _json(f"{mirrors.NPM_REGISTRY}/{dist.package}/{dist.version}")
    tarball, integrity = str(meta["dist"]["tarball"]), str(meta["dist"]["integrity"])
    tools = paths.tools_dir()
    tools.mkdir(parents=True, exist_ok=True)
    staging = tools / f".{name}.{os.getpid()}.tmp"
    archive = tools / f".{name}.{os.getpid()}.tgz"
    try:
        _download(tarball, archive, integrity, progress)
        _unpack(archive, staging, dist.root)
        exe = staging / dist.entry
        if not exe.is_file():
            raise ToolchainError(f"{tarball} 里没有 {dist.root}/{dist.entry}")
        exe.chmod(exe.stat().st_mode | 0o111)
        raw = _version(exe)
        parsed = spec.parse_version(raw)
        if parsed is None or parsed < spec.min_version:
            raise ToolchainError(f"装出来的 {dist.entry} 跑不起来或版本不对：{raw or '无输出'}")
        receipt = {"version": version, "entry": dist.entry, "package": dist.package,
                   "tarball": tarball, "integrity": integrity,
                   "at": datetime.now(UTC).isoformat(timespec="seconds")}
        (staging / RECEIPT).write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n",
                                       encoding="utf-8")
        _swap(staging, tools / name)
    finally:
        archive.unlink(missing_ok=True)
        shutil.rmtree(staging, ignore_errors=True)
    LOGGER.info("cli_installed backend=%s version=%s from=%s", name, version, tarball)
    return Found(exe=str(tools / name / dist.entry), version=raw, ok=True, private=True)


def _json(url: str) -> dict:
    try:
        with urllib.request.urlopen(_request(url), timeout=FETCH_TIMEOUT_S) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except (OSError, ValueError) as exc:  # URLError 是 OSError；坏 JSON 是 ValueError
        raise ToolchainError(f"取不到 {url}：{exc}") from exc


def _download(url: str, dest: Path, integrity: str, progress: Progress | None) -> None:
    """边下边算 sha512，与 npm 元数据里的 `integrity`（`sha512-<base64>`）对不上就抛。"""
    algo, _, want = integrity.partition("-")
    if algo != "sha512" or not want:
        raise ToolchainError(f"{url} 的元数据里没有 sha512 校验值：{integrity!r}")
    digest = hashlib.sha512()
    try:
        with urllib.request.urlopen(_request(url), timeout=FETCH_TIMEOUT_S) as resp, \
                dest.open("wb") as out:
            total = int(resp.headers["Content-Length"]) if resp.headers["Content-Length"] else None
            done = 0
            while chunk := resp.read(_CHUNK):
                out.write(chunk)
                digest.update(chunk)
                done += len(chunk)
                if progress is not None:
                    progress(done, total)
    except OSError as exc:
        raise ToolchainError(f"下载 {url} 断了：{exc}") from exc
    if base64.b64encode(digest.digest()).decode("ascii") != want:
        raise ToolchainError(f"{url} 下下来的内容与 npm 元数据的 sha512 对不上，没装")


def _unpack(archive: Path, dest: Path, root: str) -> None:
    """只解 `root/` 下的，去掉这一截前缀；`data` 过滤挡住绝对路径、`..` 与设备文件。"""
    prefix = root.rstrip("/") + "/"
    with tarfile.open(archive, "r:gz") as tar:
        members = []
        for member in tar.getmembers():
            if member.name.startswith(prefix) and member.name != prefix:
                member.name = member.name[len(prefix):]
                members.append(member)
        if not members:
            raise ToolchainError(f"{archive.name} 里没有 {root}/")
        tar.extractall(dest, members=members, filter="data")


def _swap(staging: Path, target: Path) -> None:
    """新的换上去：旧的先挪开再删，中途失败也不会剩下半份。"""
    old = target.with_name(f".{target.name}.old")
    shutil.rmtree(old, ignore_errors=True)
    if target.exists():
        target.rename(old)
    staging.rename(target)
    shutil.rmtree(old, ignore_errors=True)


def _version(exe: Path) -> str:
    """`--version` 的原文；起不来是空串（由调用方判版本认不出）。"""
    try:
        done = subprocess.run([str(exe), "--version"], capture_output=True, text=True,
                              encoding="utf-8", errors="replace", timeout=VERSION_TIMEOUT_S,
                              stdin=subprocess.DEVNULL, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        LOGGER.warning("cli_version_failed exe=%s why=%s", exe, exc)
        return ""
    return (done.stdout or done.stderr).strip()


def _request(url: str) -> urllib.request.Request:
    return urllib.request.Request(url, headers={"User-Agent": f"{paths.CLI_NAME}-setup"})
