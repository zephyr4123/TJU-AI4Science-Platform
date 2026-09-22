"""`ai4sci agent list | check | use` 与 `ai4sci check`（纲领 P-25）：走 `main()`，自检用假的 probe。
"""

from __future__ import annotations

import pytest

from backends import AgentProbe
from backends import claude_code as cc
from backends import codex as cx
from framework import agents
from framework.cli import main

OK = AgentProbe(items=[("装了没", True, "/x"), ("版本", True, "1"), ("登录", True, "是"),
                       ("说话", True, "pong")], installed=True, version="1", logged_in=True)
BAD = AgentProbe(items=[("装了没", True, "/x"), ("登录", False, "没登录：在终端跑 `codex login`")],
                 installed=True, version="1")


@pytest.fixture
def fake_probes(monkeypatch):
    calls: list[str] = []
    monkeypatch.setattr(cc, "probe", lambda: calls.append("claude_code") or OK)
    monkeypatch.setattr(cx, "probe", lambda: calls.append("codex") or BAD)
    return calls


def test_agent_list_shows_roles_and_defaults(capsys):
    assert main(["agent", "list"]) == 0
    out = capsys.readouterr().out.splitlines()
    assert out[0].startswith("claude_code\tClaude Code\t-\tsonnet\tmedium\t未检查")
    assert out[0].endswith("(对话用、执行用)")
    assert out[1].startswith("codex\tCodex\t-\tgpt-5.6-terra\tmedium\t未检查") and "(" not in out[1]


def test_agent_use_switches_a_role_and_rejects_values_off_the_list(capsys):
    assert main(["agent", "use", "codex", "--for", "executor", "--model", "gpt-5.6-luna"]) == 0
    assert capsys.readouterr().out.startswith("ok codex\tgpt-5.6-luna\tmedium\t执行用\t写入 ")
    registry = agents.load()
    assert registry.executor == "codex" and registry.chat == "claude_code"
    assert registry.get("codex").model == "gpt-5.6-luna"
    assert main(["agent", "use", "codex", "--model", "nope"]) == 2
    assert "模型 'nope' 不在清单上" in capsys.readouterr().err
    assert main(["agent", "use", "codex"]) == 2  # 什么都没给
    assert main(["agent", "use", "gemini", "--for", "chat"]) == 2
    assert main(["agent", "list"]) == 0
    assert "(执行用)" in capsys.readouterr().out.splitlines()[1]


def test_agent_check_records_and_reports(capsys, fake_probes):
    assert main(["agent", "check", "claude_code"]) == 0
    out = capsys.readouterr().out
    assert "  ✓ 说话\tpong" in out and out.rstrip().endswith("ok claude_code\t可用")
    assert main(["agent", "check", "codex"]) == 1
    out = capsys.readouterr().out
    assert "  ✗ 登录\t没登录：在终端跑 `codex login`" in out and "检查没过" in out
    assert fake_probes == ["claude_code", "codex"]
    assert agents.load().get("codex").last_check["ok"] is False
    assert main(["agent", "check", "gemini"]) == 2


def test_check_covers_agents_computes_storage_and_fails_on_any_item(capsys, fake_probes):
    assert main(["check", "--only", "storage"]) == 0
    out = capsys.readouterr().out
    assert out.startswith("存放\t") and "可写" in out and out.rstrip().endswith("ok\t全部通过")
    assert fake_probes == []  # 只查存放不碰 CLI
    assert main(["check"]) == 1
    out = capsys.readouterr().out
    assert "Claude Code\t可用\t对话用、执行用" in out and "Codex\t检查没过" in out
    assert "算力 local\t本机\t可用" in out
    assert out.rstrip().endswith("ok\t没过：agent:codex")
    assert fake_probes == ["claude_code", "codex"]
