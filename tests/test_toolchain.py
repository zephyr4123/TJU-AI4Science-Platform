"""两家 CLI 装在平台的家里（外层 #277 onboarding）：`framework/toolchain.py`。

不连网：npmmirror 换成 tmp 下一棵 `file://` 的假仓库，元数据、tgz、sha512 都照 npm 的形状造；
程序是打一行版本号的假 CLI（`tests/fixtures/fake_cli.py`，Windows 上是 exe）。真从 npmmirror 取的
那一遍在 `ai4sci setup` 的真跑里验。
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import tarfile
from pathlib import Path

import pytest

import backends
from framework import agents, mirrors, paths, toolchain
from tests.fixtures.fake_cli import fake_cli


def _registry(root: Path, name: str, version: str, says: str, *,
              files: dict[str, str] | None = None, integrity: str | None = None,
              monkeypatch) -> None:
    """在 `root` 下造一棵假 npm 仓库：主包的 latest、程序包的元数据与 tgz。程序包里
    `<Dist.root>/<Dist.entry>` 是一个 `--version` 打 `says` 的假 CLI，`files` 是旁边别的文件。"""
    spec = backends.install_of(name)
    dist = spec.dist(toolchain.platform_key(), version)
    src = root / "src" / dist.root
    (src / dist.entry).parent.mkdir(parents=True, exist_ok=True)
    fake_cli(src / dist.entry, f"print({says!r})\n")
    for rel, body in (files or {}).items():
        path = src / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")
    tgz = root / "tarballs" / f"{name}-{version}.tgz"
    tgz.parent.mkdir(parents=True, exist_ok=True)
    with tarfile.open(tgz, "w:gz") as tar:
        tar.add(root / "src" / "package", arcname="package")
    digest = base64.b64encode(hashlib.sha512(tgz.read_bytes()).digest()).decode()
    latest = root / "registry" / spec.npm / "latest"
    latest.parent.mkdir(parents=True, exist_ok=True)
    latest.write_text(json.dumps({"version": version}), encoding="utf-8")
    meta = root / "registry" / dist.package / dist.version
    meta.parent.mkdir(parents=True, exist_ok=True)
    meta.write_text(json.dumps({"dist": {"tarball": tgz.as_uri(),
                                         "integrity": integrity or f"sha512-{digest}"}}),
                    encoding="utf-8")
    monkeypatch.setattr(mirrors, "NPM_REGISTRY", (root / "registry").as_uri())


def test_platform_names_follow_npm():
    assert toolchain.platform_key("darwin", "arm64") == "darwin-arm64"
    assert toolchain.platform_key("linux", "x86_64") == "linux-x64"
    assert toolchain.platform_key("win32", "AMD64") == "win32-x64"
    with pytest.raises(toolchain.ToolchainError, match="没有现成的程序包"):
        toolchain.platform_key("freebsd", "x86_64")


def test_install_puts_the_cli_in_the_home_and_the_platform_runs_that_one(tmp_path, monkeypatch):
    entry = backends.install_of("claude_code").dist(toolchain.platform_key(), "9.9.9").entry
    _registry(tmp_path, "claude_code", "9.9.9", "9.9.9 (Claude Code)", monkeypatch=monkeypatch)
    assert toolchain.private_cli("claude_code") is None
    seen: list[tuple[int, int | None]] = []
    found = toolchain.install("claude_code",
                              progress=lambda done, total: seen.append((done, total)))
    exe = paths.tools_dir() / "claude_code" / entry
    assert found == toolchain.Found(exe=str(exe), version="9.9.9 (Claude Code)", ok=True,
                                    private=True)
    assert seen and seen[-1][0] == seen[-1][1]  # 下完了：已下 = 总长
    receipt = json.loads((exe.parent / toolchain.RECEIPT).read_text(encoding="utf-8"))
    assert receipt["version"] == "9.9.9" and receipt["integrity"].startswith("sha512-")
    assert toolchain.private_cli("claude_code") == exe
    assert agents.link("claude_code").cli == str(exe)  # 起会话用家里这份
    assert agents.link("codex").cli is None  # 没装的那家用 PATH 上的
    assert toolchain.find("claude_code") == found
    leftovers = [p.name for p in paths.tools_dir().iterdir() if p.name.startswith(".")]
    assert leftovers == []  # 临时目录与 tgz 都收拾了


def test_codex_keeps_the_files_its_program_looks_for_next_to_itself(tmp_path, monkeypatch):
    """Codex 的程序包里除了程序还有 `codex-path/rg`：整块留下，布局不动（0.160.1 实测）。"""
    entry = backends.install_of("codex").dist(toolchain.platform_key(), "9.9.9").entry
    _registry(tmp_path, "codex", "9.9.9", "codex-cli 9.9.9", files={"codex-path/rg": "rg\n"},
              monkeypatch=monkeypatch)
    found = toolchain.install("codex")
    root = paths.tools_dir() / "codex"
    assert found.exe == str(root / entry) and (root / "codex-path" / "rg").is_file()


def test_a_bad_download_or_a_broken_build_leaves_the_old_install_alone(tmp_path, monkeypatch):
    _registry(tmp_path / "a", "claude_code", "9.9.9", "9.9.9 (Claude Code)",
              monkeypatch=monkeypatch)
    toolchain.install("claude_code")
    _registry(tmp_path / "b", "claude_code", "9.9.10", "9.9.10 (Claude Code)",
              integrity="sha512-" + base64.b64encode(b"x" * 64).decode(), monkeypatch=monkeypatch)
    with pytest.raises(toolchain.ToolchainError, match="sha512 对不上"):
        toolchain.install("claude_code")
    _registry(tmp_path / "c", "claude_code", "1.0.0", "1.0.0 (Claude Code)",
              monkeypatch=monkeypatch)
    with pytest.raises(toolchain.ToolchainError, match="版本不对：1.0.0"):
        toolchain.install("claude_code")
    assert toolchain.find("claude_code").version == "9.9.9 (Claude Code)"
    assert [p.name for p in paths.tools_dir().iterdir()] == ["claude_code"]


def test_find_falls_back_to_the_one_on_path_and_judges_its_version(tmp_path, monkeypatch):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    old = fake_cli(bin_dir / "claude", "print('2.0.0 (Claude Code)')\n")
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}/usr/bin{os.pathsep}/bin")
    found = toolchain.find("claude_code")
    assert found == toolchain.Found(exe=old, version="2.0.0 (Claude Code)", ok=False,
                                    private=False)
    fake_cli(bin_dir / "claude", "print('2.1.300 (Claude Code)')\n")
    assert toolchain.find("claude_code").ok
    monkeypatch.setenv("PATH", "/nonexistent")
    assert toolchain.find("codex") is None


def test_an_npm_shell_shim_on_windows_is_not_good_enough(tmp_path, monkeypatch):
    """Windows 上 npm 装的是 `claude.cmd`：平台只起原生 exe，认作不够用，setup 装一份进家里。"""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    shim = bin_dir / "claude.cmd"
    shim.write_text("@echo 2.1.300 (Claude Code)\r\n", encoding="utf-8")
    monkeypatch.setattr(toolchain.sys, "platform", "win32")
    monkeypatch.setattr(toolchain.shutil, "which", lambda command: str(shim))
    assert toolchain.find("claude_code") == toolchain.Found(exe=str(shim), version="", ok=False,
                                                            private=False)


def test_an_unreadable_receipt_counts_as_not_installed():
    root = paths.tools_dir() / "codex"
    root.mkdir(parents=True)
    (root / toolchain.RECEIPT).write_text("{坏", encoding="utf-8")
    assert toolchain.private_cli("codex") is None


def test_mirrors_fill_in_only_what_the_user_has_not_set():
    assert mirrors.missing({}) == {"UV_DEFAULT_INDEX": mirrors.PYPI_INDEX,
                                   "UV_PYTHON_INSTALL_MIRROR": mirrors.PYTHON_DOWNLOADS,
                                   "HF_ENDPOINT": mirrors.HF_ENDPOINT}
    theirs = mirrors.missing({"UV_INDEX_URL": "https://pypi.org/simple", "HF_ENDPOINT": "x"})
    assert theirs == {"UV_PYTHON_INSTALL_MIRROR": mirrors.PYTHON_DOWNLOADS}
