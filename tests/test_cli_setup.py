"""`ai4sci setup`（外层 #277 onboarding）：走 `main()`，装 CLI、自检、问 key 都换成假的，不连网、
不起服务（`--no-serve`）。真从 npmmirror 装、真问 DeepSeek 一句在 live 真跑里验。
"""

from __future__ import annotations

import pytest

from backends import AgentProbe
from backends import claude_code as cc
from backends import codex as cx
from framework import agents, keys, toolchain
from framework.cli import main
from framework.cli import setup as setup_cli

OK = AgentProbe(items=[("装了没", True, "/x"), ("版本", True, "2.1.292"), ("登录", True, "已填"),
                       ("说话", True, "pong，1.2 秒")], installed=True, logged_in=True,
                spoke_s=1.2)
NO_KEY = AgentProbe(items=[("装了没", True, "/x"), ("版本", True, "2.1.292"),
                           ("登录", False, "平台里还没登录")], installed=True)


@pytest.fixture
def machine(monkeypatch):
    """一台假机器：git 有没有、两家 CLI 装没装、助理那家能不能说话、人粘贴了什么，都由用例定。"""
    state = {"git": True, "found": {}, "installed": [], "probes": {}, "typed": [], "asked": 0,
             "tty": True}

    def find(name):
        return state["found"].get(name)

    def install(name, progress=None):
        state["installed"].append(name)
        got = toolchain.Found(exe=f"/home/tools/{name}", version="9.9.9", ok=True, private=True)
        state["found"][name] = got
        return got

    def probe_of(name):
        def probe(link):
            ready = keys.get("deepseek") == "sk-good" and link.provider == "deepseek"
            return state["probes"].get(name) or (OK if ready else NO_KEY)
        return probe

    def ask(prompt):
        state["asked"] += 1
        return state["typed"].pop(0) if state["typed"] else ""

    monkeypatch.setattr(setup_cli, "git_ready", lambda: (state["git"], "已装" if state["git"]
                                                         else "没装：用系统的包管理器装 git"))
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
