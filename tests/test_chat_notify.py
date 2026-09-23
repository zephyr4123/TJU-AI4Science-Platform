"""叫醒（外层 #63，#136 改收件箱）：作业跑完先进收件箱，对话空闲就当场以「框架」身份发一轮念完；
忙就留着（queued），正跑的那一轮结束后 `follow_up` 接着念；对话不在、后端不对都记成一句话。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from backends import BackendNotFound
from framework import paths
from framework.chat import conversation as conv_mod
from framework.chat import notify, scope
from framework.workspace import jobs
from framework.workspace import project as project_mod
from framework.workspace import root as workspace
from tests.fixtures import spaces
from tests.fixtures.scripted_chat import ScriptedChat, failure, reply


def _ws(tmp_path: Path) -> workspace.Workspace:
    return spaces.make_workspace(tmp_path, "w1")


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
    conv = conv_mod.new_conversation(project_mod.of(ws).chats, "claude_code", ws.root)
    scripted.turns.append(reply("收到，第 2 轮有改进"))
    assert notify.wake(ws, _job(conv.chat_id)) == "done"
    call = scripted.calls[0]
    assert call["chat_id"] == conv.chat_id and call["system_prompt"] == "指南"
    assert call["allowed_paths"] == [project_mod.of(ws).root]  # 叫醒的一轮也只在项目里写
    assert call["readable_paths"] == [paths.workflows_root(), paths.user_workflows_root(),
                                      paths.templates_root()]
    head = ("工作区 w1 的作业 job-7（`ai4sci cap auto-research --from design/1 --max-iters 2`）"
            "跑完了")
    assert call["message"].startswith(head)
    assert "--ws w1" in call["message"]
    assert conv_mod.pending_notes(conv) == []  # 念完了，收件箱空
    assert "stop batch_exhausted\toutput=experiment/1" in call["message"]
    assert "--detach" in call["message"]
    turns = conv_mod.read_turns(conv_mod.load_conversation(project_mod.of(ws).chats, conv.chat_id))
    assert turns[0]["origin"] == "框架" and turns[0]["reply"] == "收到，第 2 轮有改进"
    transcript = (conv.dir / "transcript.md").read_text(encoding="utf-8")
    assert "**框架**：工作区 w1 的作业 job-7" in transcript


def test_wake_reports_a_failed_job_and_an_unfinished_turn(tmp_path: Path, scripted):
    ws = _ws(tmp_path)
    conv = conv_mod.new_conversation(project_mod.of(ws).chats, "claude_code", ws.root)
    scripted.turns.append(failure("超时"))
    status = notify.wake(ws, _job(conv.chat_id, exit_code=1))
    assert status == "error: 超时"
    assert "没跑成，退出码 1" in scripted.calls[0]["message"]


def test_wake_queues_while_the_conversation_is_busy_and_follow_up_reads_the_inbox(
        tmp_path: Path, scripted):
    """对话忙：话留在收件箱、几秒内再试；还忙就 queued 不丢。正跑的那一轮结束后 `follow_up`
    一次把收件箱念完（几条并成一轮），空了就不发。"""
    ws = _ws(tmp_path)
    where = scope.for_project(project_mod.of(ws))
    conv = conv_mod.new_conversation(where.chats, "claude_code", ws.root)
    inflight = conv.dir / conv_mod.INFLIGHT_NAME
    inflight.write_text("{}", encoding="utf-8")
    scripted.turns.append(reply("醒了"))
    naps: list[float] = []

    def sleep(seconds: float) -> None:
        naps.append(seconds)
        if len(naps) == 2:
            inflight.unlink()  # 第二次等完人说完了

    assert notify.wake(ws, _job(conv.chat_id), settle_s=60.0, sleep=sleep) == "done"
    assert naps == [1.0, 1.0] and scripted.calls[-1]["message"].startswith("工作区 w1 的作业 job-7")
    # 一直忙：留在收件箱，queued；两条作业排两条
    inflight.write_text("{}", encoding="utf-8")
    assert notify.wake(ws, _job(conv.chat_id), settle_s=3.0, sleep=lambda s: None) == "queued"
    failed = _job(conv.chat_id, exit_code=1)
    assert notify.wake(ws, failed, settle_s=0, sleep=lambda s: None) == "queued"
    assert len(conv_mod.pending_notes(conv)) == 2
    # 人那一轮结束（锁摘了）：follow_up 一轮念完两条，事件照吐；再调一次收件箱空、一个事件都没有
    inflight.unlink()
    scripted.turns.append(reply("两条都看了"))
    events = list(notify.follow_up(where, conv, scripted, "指南"))
    assert [e.kind for e in events] == ["init", "text", "done"]
    message = scripted.calls[-1]["message"]
    assert message.count("作业 job-7") == 2 and "没跑成，退出码 1" in message
    assert conv_mod.pending_notes(conv) == []
    assert list(notify.follow_up(where, conv, scripted, "指南")) == []
    turns = conv_mod.read_turns(conv_mod.load_conversation(where.chats, conv.chat_id))
    assert [t["origin"] for t in turns] == ["框架", "框架"]


def test_wake_records_missing_conversation_or_backend_instead_of_raising(tmp_path, monkeypatch):
    ws = _ws(tmp_path)
    status = notify.wake(ws, _job("chat-nope"))
    assert status.startswith("failed: 对话不存在")
    conv = conv_mod.new_conversation(project_mod.of(ws).chats, "nope", ws.root)
    monkeypatch.setattr(notify, "get_chat",
                        lambda name: (_ for _ in ()).throw(BackendNotFound(f"未知 {name}")))
    assert notify.wake(ws, _job(conv.chat_id)) == "failed: 未知 nope"
    with pytest.raises(AssertionError):
        notify.wake(ws, _job(None))


def test_mark_wake_lands_in_the_job_record(tmp_path: Path):
    jobs._save(tmp_path / "jobs", _job("chat-x"))
    assert jobs.mark_wake(tmp_path / "jobs", "job-7", "queued").wake == "queued"
    assert json.loads((tmp_path / "jobs" / "job-7.json").read_text())["wake"] == "queued"
