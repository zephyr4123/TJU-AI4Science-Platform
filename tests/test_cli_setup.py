"""`ai4sci setup`（外层 #277 onboarding）：走 `main()`，装 CLI、自检、问 key 都换成假的，不连网、
不起服务（`--no-serve`）。真从 npmmirror 装、真问 DeepSeek 一句在 live 真跑里验。

`--no-input` 是桌面 App 起的那一种（外层 #282）：不问、不探模型、不开浏览器，一项一行给外壳读。
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import time

import pytest

from backends import AgentProbe
from backends import claude_code as cc
from backends import codex as cx
from framework import agents, keys, toolchain
from framework.cli import main
from framework.cli import serve as serve_cli
from framework.cli import setup as setup_cli

REAL_GIT_READY = setup_cli.git_ready

OK = AgentProbe(items=[("装了没", True, "/x"), ("版本", True, "2.1.292"), ("登录", True, "已填"),
                       ("说话", True, "pong，1.2 秒")], installed=True, logged_in=True,
                spoke_s=1.2)
NO_KEY = AgentProbe(items=[("装了没", True, "/x"), ("版本", True, "2.1.292"),
                           ("登录", False, "平台里还没登录")], installed=True)


@pytest.fixture
def machine(monkeypatch):
    """一台假机器：git 有没有、两家 CLI 装没装、助理那家能不能说话、人粘贴了什么，都由用例定。"""
    state = {"git": True, "found": {}, "installed": [], "probes": {}, "typed": [], "asked": 0,
             "tty": True, "probed": 0}

    def find(name):
        return state["found"].get(name)

    def install(name, progress=None):
        state["installed"].append(name)
        got = toolchain.Found(exe=f"/home/tools/{name}", version="9.9.9", ok=True, private=True)
        state["found"][name] = got
        return got

    def probe_of(name):
        def probe(link):
            state["probed"] += 1
            ready = keys.get("deepseek") == "sk-good" and link.provider == "deepseek"
            return state["probes"].get(name) or (OK if ready else NO_KEY)
        return probe

    def ask(prompt):
        state["asked"] += 1
        return state["typed"].pop(0) if state["typed"] else ""

    monkeypatch.setattr(setup_cli, "git_ready", lambda no_input=False: (
        ("✓", "已装，跳过") if state["git"] else ("✗", "没装：用系统的包管理器装 git")))
    monkeypatch.setattr(toolchain, "find", find)
    monkeypatch.setattr(toolchain, "install", install)
    monkeypatch.setattr(cc, "probe", probe_of("claude_code"))
    monkeypatch.setattr(cx, "probe", probe_of("codex"))
    monkeypatch.setattr(setup_cli, "ask_secret", ask)
    monkeypatch.setattr(setup_cli, "interactive", lambda: state["tty"])
    return state


def test_a_fresh_machine_gets_both_clis_and_a_working_deepseek_key(machine, capsys):
    machine["typed"] = ["sk-good"]
    assert main(["setup", "--no-serve"]) == 0
    out = capsys.readouterr().out
    assert machine["installed"] == ["claude_code", "codex"]
    assert "Claude Code   9.9.9，下载完成" in out and "Codex         9.9.9，下载完成" in out
    assert keys.get("deepseek") == "sk-good"
    # 新家：两家都切到 DeepSeek，以后在设置里换执行层也不用再填
    registry = agents.load()
    assert {registry.get(n).provider for n in ("claude_code", "codex")} == {"deepseek"}
    assert "Claude Code 问了一句，通了" in out
    assert "sk-good" not in out  # key 不上屏


def test_rerun_skips_everything_that_already_works(machine, capsys):
    machine["found"] = {n: toolchain.Found(exe="/x", version="2.1.292", ok=True, private=True)
                        for n in ("claude_code", "codex")}
    keys.put("deepseek", "sk-good")
    agents.use("claude_code", provider="deepseek")
    assert main(["setup", "--no-serve"]) == 0
    out = capsys.readouterr().out
    assert machine["installed"] == [] and machine["asked"] == 0
    assert out.count("已装，跳过") == 3 and "Claude Code 能用" in out  # git 与两家


def test_a_cli_below_the_platform_minimum_is_replaced(machine, capsys):
    machine["found"] = {"claude_code": toolchain.Found(exe="/usr/local/bin/claude",
                                                       version="2.0.0", ok=False, private=False),
                        "codex": toolchain.Found(exe="/x", version="0.160.1", ok=True,
                                                 private=True)}
    machine["typed"] = ["sk-good"]
    assert main(["setup", "--no-serve"]) == 0
    assert machine["installed"] == ["claude_code"]


def test_a_wrong_key_is_asked_again_and_an_empty_one_skips(machine, capsys):
    machine["typed"] = ["sk-bad", ""]
    assert main(["setup", "--no-serve"]) == 1
    out = capsys.readouterr().out
    assert machine["asked"] == 2
    assert "没通" in out and "页面「设置 → AI」里填" in out
    assert "sk-bad" not in out


def test_without_a_terminal_it_does_not_ask(machine, capsys):
    machine["tty"] = False
    assert main(["setup", "--no-serve"]) == 1
    assert machine["asked"] == 0
    assert "没有终端，不问 key" in capsys.readouterr().out


def test_missing_git_is_reported_but_the_rest_still_runs(machine, capsys):
    machine["git"] = False
    machine["typed"] = ["sk-good"]
    assert main(["setup", "--no-serve"]) == 1
    out = capsys.readouterr().out
    assert "✗ git" in out and machine["installed"] == ["claude_code", "codex"]


def test_no_input_never_asks_or_probes_and_puts_both_clis_in_the_home(machine, capsys):
    """桌面 App 起的 setup（外层 #282）：外壳拿到的 PATH 时有时没有，PATH 上的 CLI 认了就时好时坏，
    所以一律装进家里；不问 key（Windows 上标准输入接 NUL 时 isatty 是真，getpass 会卡死）、不探模型
    （能不能说话由页面读 /settings 再弹框），git 与 CLI 装好就退 0。"""
    machine["found"] = {n: toolchain.Found(exe=f"/usr/local/bin/{n}", version="2.1.292", ok=True,
                                           private=False) for n in ("claude_code", "codex")}
    assert main(["setup", "--no-serve", "--no-input"]) == 0
    out = capsys.readouterr().out
    assert machine["installed"] == ["claude_code", "codex"]
    assert machine["asked"] == 0 and machine["probed"] == 0
    assert "key" not in out


def test_no_input_skips_what_the_home_already_has_and_fails_on_a_cli_it_cannot_get(machine,
                                                                                   monkeypatch,
                                                                                   capsys):
    machine["found"] = {"claude_code": toolchain.Found(exe="/home/tools/claude", version="2.1.292",
                                                       ok=True, private=True)}

    def broken(name, progress=None):
        raise toolchain.ToolchainError("下载 https://registry.npmmirror.com/x 断了：timed out")

    monkeypatch.setattr(toolchain, "install", broken)
    assert main(["setup", "--no-serve", "--no-input"]) == 1
    out = capsys.readouterr().out
    assert "✓ Claude Code   2.1.292，已装，跳过" in out
    assert "✗ Codex         下载 https://registry.npmmirror.com/x 断了" in out


def test_a_mac_without_command_line_tools_asks_apple_once_and_lets_the_desktop_in(machine,
                                                                                  monkeypatch,
                                                                                  capsys):
    """研究者的 Mac 多半没装命令行工具（外层 #282 审查）：git 只在跑实验时要，桌面 App 不为它停在
    启动页——弹一次苹果的安装框、打一行 `!`、不算失败。终端里照旧算没装好。"""
    calls = []

    def run(argv, **kwargs):
        calls.append(argv)
        return subprocess.CompletedProcess(argv, 2 if argv[1] == "-p" else 0, b"", b"")

    monkeypatch.setattr(setup_cli, "git_ready", REAL_GIT_READY)
    monkeypatch.setattr(sys, "platform", "darwin")
    monkeypatch.setattr(subprocess, "run", run)
    monkeypatch.setattr(shutil, "which", lambda name: setup_cli.MAC_GIT_STUB)
    assert main(["setup", "--no-serve", "--no-input"]) == 0
    out = capsys.readouterr().out
    assert calls.count(["xcode-select", "--install"]) == 1
    notice = next(line for line in out.splitlines() if line.startswith("  ! git"))
    assert "终端" not in notice and "ai4sci setup" not in notice
    mark, note = REAL_GIT_READY()
    assert mark == "✗" and "装完再跑一次 ai4sci setup" in note


def test_without_a_terminal_a_download_says_it_started_and_then_every_five_seconds(machine,
                                                                                  monkeypatch,
                                                                                  capsys):
    """外壳不接终端，一项装完才有一行时，启动页有几十秒什么都不动（外层 #282 实测 22、34、41 秒）：
    开始下就说一句，之后每 5 秒一行已下多少，每行当场 flush。"""
    clock = [100.0]
    monkeypatch.setattr(time, "monotonic", lambda: clock[0])

    def install(name, progress=None):
        for at, done, total in ((101, 1e6, 224e6), (105.5, 30e6, 224e6), (107, 60e6, 224e6),
                                (110.6, 120e6, 224e6), (116, 130e6, None)):
            clock[0] = at
            progress(int(done), None if total is None else int(total))
        return toolchain.Found(exe="/home/tools/x", version="9.9.9", ok=True, private=True)

    monkeypatch.setattr(toolchain, "install", install)
    assert main(["setup", "--no-serve", "--no-input"]) == 0
    lines = [line for line in capsys.readouterr().out.splitlines() if "Claude Code" in line]
    assert lines == ["  … Claude Code   下载中",
                     "  ↓ Claude Code   已下 30 MB / 共 224 MB",
                     "  ↓ Claude Code   已下 120 MB / 共 224 MB",
                     "  ↓ Claude Code   已下 130 MB",
                     "  ✓ Claude Code   9.9.9，下载完成"]


def test_the_hand_over_to_serve_carries_every_option_serve_has(machine, monkeypatch):
    """setup 起服务时的参数由 serve 自己的 parser 生成：serve 加了参数（外壳要的那些），`make up` 与
    一行命令的最后一步不会因为少一个属性而断（外层 #282 审查）。--no-input 不开浏览器。"""
    machine["typed"] = ["sk-good"]
    real_add_parser = serve_cli.add_parser
    handed: list = []
    opened: list = []

    def add_parser(groups):
        real_add_parser(groups)
        groups.choices["serve"].add_argument("--newly-added", default="缺省值")

    monkeypatch.setattr(serve_cli, "add_parser", add_parser)
    monkeypatch.setattr(serve_cli, "cmd_serve", lambda args: handed.append(args) or 0)
    monkeypatch.setattr(setup_cli, "_listening", lambda host, port: False)
    monkeypatch.setattr(setup_cli, "_open_when_up", lambda *args: opened.append(args))
    assert main(["setup", "--port", "9001"]) == 0
    assert handed[-1].port == 9001 and handed[-1].host == "127.0.0.1"
    assert handed[-1].ui is None and handed[-1].newly_added == "缺省值"
    assert len(opened) == 1
    assert main(["setup", "--no-input"]) == 0
    assert len(handed) == 2 and len(opened) == 1
