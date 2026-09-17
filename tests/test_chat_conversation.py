"""对话落盘与"发一轮"：session id 续接、事件流留档、transcript、忙锁、没走完的一轮。"""

from __future__ import annotations

import json

import pytest

from framework.chat import conversation as conv_mod
from tests.fixtures.scripted_chat import SESSION, ScriptedChat, failure, reply, with_tool

GUIDE = "# 指南\n你是协调 agent。"


def start(tmp_path, *turns):
    conv = conv_mod.new_conversation(tmp_path / "runs", "scripted", tmp_path)
    return conv, ScriptedChat(list(turns))


def drain(conv, chat, text, **kw):
    return list(conv_mod.send(conv, chat, text, system_prompt=GUIDE, allowed_paths=[],
                              bash_rules=(), **kw))


def test_new_load_list_round_trip(tmp_path):
    conv, _ = start(tmp_path)
    assert conv.dir == tmp_path / "runs" / "chats" / conv.chat_id
    assert conv.chat_id.startswith("chat-") and conv.session_id is None and conv.turns == 0
    loaded = conv_mod.load_conversation(tmp_path / "runs", conv.chat_id)
    assert loaded.to_dict() == conv.to_dict() and loaded.dir == conv.dir
    assert [c.chat_id for c in conv_mod.list_conversations(tmp_path / "runs")] == [conv.chat_id]
    with pytest.raises(conv_mod.ConversationNotFound):
        conv_mod.load_conversation(tmp_path / "runs", "nope")
    with pytest.raises(FileExistsError):
        conv_mod.new_conversation(tmp_path / "runs", "scripted", tmp_path, chat_id=conv.chat_id)


def test_framework_origin_turn_is_labelled_and_chat_id_reaches_the_adapter(tmp_path):
    """外层 #63：框架叫醒的一轮标「框架」；适配器拿到 chat_id 好传给 agent 按的按钮。"""
    conv, chat = start(tmp_path, reply("醒了"), reply("好"))
    drain(conv, chat, "作业跑完了", origin="框架")
    assert chat.calls[0]["chat_id"] == conv.chat_id
    assert "**框架**：作业跑完了" in (conv.dir / "transcript.md").read_text(encoding="utf-8")
    drain(conv, chat, "谢谢")
    assert [t["origin"] for t in conv_mod.read_turns(conv)] == ["框架", "人"]
    with pytest.raises(ValueError, match="origin"):
        drain(conv, chat, "x", origin="机器人")


def test_two_turns_resume_by_session_id_and_land_on_disk(tmp_path):
    listing = with_tool("有三个任务包", "Bash", {"command": "ai4sci task list"}, "a\nb\nc")
    conv, chat = start(tmp_path, reply("你好，研究者"), listing)
    first = drain(conv, chat, "你好")
    assert [e.kind for e in first] == ["init", "text", "done"]
    assert chat.calls[0]["session_id"] is None and chat.calls[0]["system_prompt"] == GUIDE
    assert conv.session_id == SESSION and conv.turns == 1 and conv.cost_usd == pytest.approx(0.01)

    second = drain(conv, chat, "有哪些任务包？")
    assert [e.kind for e in second] == ["init", "tool_use", "tool_result", "text", "done"]
    assert chat.calls[1]["session_id"] == SESSION, "第二轮要带上第一轮的 session id"
    assert conv.turns == 2 and conv.cost_usd == pytest.approx(0.02)

    reloaded = conv_mod.load_conversation(tmp_path / "runs", conv.chat_id)
    assert reloaded.session_id == SESSION and reloaded.turns == 2
    lines = (conv.dir / "turn-2" / "events.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(lines) == 5 and json.loads(lines[1])["type"] == "assistant"
    assert (conv.dir / "turn-2" / "message.md").read_text(encoding="utf-8") == "有哪些任务包？\n"
    transcript = (conv.dir / "transcript.md").read_text(encoding="utf-8")
    assert "## 第 1 轮" in transcript and "**agent**：有三个任务包" in transcript
    assert not (conv.dir / "inflight.json").exists()


def test_failed_turn_is_recorded_and_session_kept(tmp_path):
    conv, chat = start(tmp_path, reply("好"), failure("这一轮超过 5 秒，进程树已杀"))
    drain(conv, chat, "记住 17")
    events = drain(conv, chat, "再来")
    assert events[-1].kind == "error" and conv.turns == 2
    assert conv.session_id == SESSION, "没走完的一轮不丢 session id"
    assert conv.cost_usd == pytest.approx(0.01), "成本 NaN 不累加、不填 0"
    transcript = (conv.dir / "transcript.md").read_text(encoding="utf-8")
    assert "这一轮没走完" in transcript
    lines = (conv.dir / "turn-2" / "events.jsonl").read_text(encoding="utf-8").splitlines()
    assert json.loads(lines[-1])["type"] == "ai4sci_error"


def test_busy_lock_refuses_a_second_turn_and_is_released(tmp_path):
    conv, chat = start(tmp_path, reply("一"), reply("二"))
    stream = conv_mod.send(conv, chat, "第一句", system_prompt=GUIDE, allowed_paths=[],
                           bash_rules=())
    next(stream)  # 第一轮跑到一半
    assert (conv.dir / "inflight.json").exists()
    with pytest.raises(conv_mod.ConversationBusy):
        drain(conv, chat, "插队")
    stream.close()  # 调用方半途放弃：锁要摘掉，meta 不记这一轮，目录留着当证据
    assert not (conv.dir / "inflight.json").exists() and conv.turns == 0
    assert (conv.dir / "turn-1" / "message.md").is_file()
    assert drain(conv, chat, "再发")[-1].kind == "done" and conv.turns == 1
    assert (conv.dir / "turn-2" / "message.md").read_text(encoding="utf-8") == "再发\n"


def test_empty_message_and_timeout_env(tmp_path, monkeypatch):
    conv, chat = start(tmp_path, reply("x"))
    with pytest.raises(ValueError, match="空"):
        drain(conv, chat, "   ")
    monkeypatch.setenv("AI4SCI_COORDINATOR_TIMEOUT_S", "42")
    drain(conv, chat, "hi")
    assert chat.calls[0]["timeout_s"] == 42.0
    monkeypatch.setenv("AI4SCI_COORDINATOR_TIMEOUT_S", "-1")
    with pytest.raises(AssertionError):
        conv_mod.coordinator_timeout_s()
