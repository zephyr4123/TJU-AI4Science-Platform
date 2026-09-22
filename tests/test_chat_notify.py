"""叫醒（外层 #63）：作业跑完以「框架」身份发一轮；对话忙就等；对话不在、后端不对都记成一句话。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from backends import BackendNotFound
from framework import paths
from framework.chat import conversation as conv_mod
from framework.chat import notify
from framework.workspace import jobs
from framework.workspace import root as workspace
from tests.fixtures.scripted_chat import ScriptedChat, failure, reply


def _ws(tmp_path: Path) -> workspace.Workspace:
    return workspace.create(tmp_path / "workspaces", "w1")


def _job(chat_id: str | None, exit_code: int = 0) -> jobs.Job:
    return jobs.Job(job_id="job-7", cap="auto-research", stage="experiment",
                    argv=["cap", "auto-research", "--from", "design/1", "--max-iters", "2"],
                    pid=1, started_at="t",
                    status="done" if exit_code == 0 else "failed", exit_code=exit_code,
                    result="stop batch_exhausted\toutput=experiment/1" if exit_code == 0
                    else "有 in-flight", chat_id=chat_id, output="experiment/1")


@pytest.fixture
def scripted(monkeypatch):
    chat = ScriptedChat([])
    monkeypatch.setattr(notify, "get_chat", lambda name: chat)
    monkeypatch.setattr(notify.guide, "system_prompt", lambda kind, tool_guide="": "指南")
    return chat


def test_wake_sends_a_framework_turn_with_the_job_result(tmp_path: Path, scripted):
    ws = _ws(tmp_path)
    conv = conv_mod.new_conversation(ws.chats, "claude_code", ws.root)
    scripted.turns.append(reply("收到，第 2 轮有改进"))
    assert notify.wake(ws, _job(conv.chat_id)) == "done"
    call = scripted.calls[0]
    assert call["chat_id"] == conv.chat_id and call["system_prompt"] == "指南"
    assert call["allowed_paths"] == [ws.root]  # 叫醒的一轮也只在工作区里写
    assert call["readable_paths"] == [paths.workflows_root(), paths.templates_root()]
    head = "作业 job-7（`ai4sci cap auto-research --from design/1 --max-iters 2`）跑完了"
    assert call["message"].startswith(head)
    assert "stop batch_exhausted\toutput=experiment/1" in call["message"]
    assert "--detach" in call["message"]
    turns = conv_mod.read_turns(conv_mod.load_conversation(ws.chats, conv.chat_id))
    assert turns[0]["origin"] == "框架" and turns[0]["reply"] == "收到，第 2 轮有改进"
    transcript = (conv.dir / "transcript.md").read_text(encoding="utf-8")
    assert "**框架**：作业 job-7" in transcript


def test_wake_reports_a_failed_job_and_an_unfinished_turn(tmp_path: Path, scripted):
    ws = _ws(tmp_path)
    conv = conv_mod.new_conversation(ws.chats, "claude_code", ws.root)
    scripted.turns.append(failure("超时"))
    status = notify.wake(ws, _job(conv.chat_id, exit_code=1))
    assert status == "error: 超时"
    assert "没跑成，退出码 1" in scripted.calls[0]["message"]


def test_wake_waits_while_the_conversation_is_busy_then_gives_up(tmp_path: Path, scripted):
    ws = _ws(tmp_path)
    conv = conv_mod.new_conversation(ws.chats, "claude_code", ws.root)
    inflight = conv.dir / conv_mod.INFLIGHT_NAME
    inflight.write_text("{}", encoding="utf-8")
    scripted.turns.append(reply("醒了"))
    naps: list[float] = []

    def sleep(seconds: float) -> None:
        naps.append(seconds)
        if len(naps) == 2:
            inflight.unlink()  # 第二次等完人说完了

    assert notify.wake(ws, _job(conv.chat_id), retry_s=1.0, max_wait_s=60.0,
                       sleep=sleep) == "done"
    assert naps == [1.0, 1.0]
    inflight.write_text("{}", encoding="utf-8")
    status = notify.wake(ws, _job(conv.chat_id), retry_s=5.0, max_wait_s=10.0,
                         sleep=lambda s: None)
    assert status.startswith("busy: 等了 10 秒")


def test_wake_records_missing_conversation_or_backend_instead_of_raising(tmp_path, monkeypatch):
    ws = _ws(tmp_path)
    status = notify.wake(ws, _job("chat-nope"))
    assert status.startswith("failed: 对话不存在")
    conv = conv_mod.new_conversation(ws.chats, "nope", ws.root)
    monkeypatch.setattr(notify, "get_chat",
                        lambda name: (_ for _ in ()).throw(BackendNotFound(f"未知 {name}")))
    assert notify.wake(ws, _job(conv.chat_id)) == "failed: 未知 nope"
    with pytest.raises(AssertionError):
        notify.wake(ws, _job(None))


def test_mark_wake_lands_in_the_job_record(tmp_path: Path):
    jobs._save(tmp_path / "jobs", _job("chat-x"))
    assert jobs.mark_wake(tmp_path / "jobs", "job-7", "busy: 等了 1800 秒").wake.startswith("busy")
    assert json.loads((tmp_path / "jobs" / "job-7.json").read_text())["wake"].startswith("busy")
