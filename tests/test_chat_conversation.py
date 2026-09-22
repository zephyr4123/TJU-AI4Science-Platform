"""对话落盘与"发一轮"：session id 续接、事件流留档、transcript、忙锁、没走完的一轮。"""

from __future__ import annotations

import json

import pytest

from framework.chat import conversation as conv_mod
from tests.fixtures.scripted_chat import (
    SESSION,
    ScriptedChat,
    failure,
    reply,
    streamed,
    with_tool,
)

GUIDE = "# 指南\n你是协调 agent。"


def start(tmp_path, *turns):
    conv = conv_mod.new_conversation(tmp_path / "chats", "scripted", tmp_path)
    return conv, ScriptedChat(list(turns))


def drain(conv, chat, text, **kw):
    return list(conv_mod.send(conv, chat, text, system_prompt=GUIDE, allowed_paths=[],
                              bash_rules=(), **kw))


def test_new_load_list_round_trip(tmp_path):
    conv, _ = start(tmp_path)
    assert conv.dir == tmp_path / "chats" / conv.chat_id
    assert conv.chat_id.startswith("chat-") and conv.session_id is None and conv.turns == 0
    loaded = conv_mod.load_conversation(tmp_path / "chats", conv.chat_id)
    assert loaded.to_dict() == conv.to_dict() and loaded.dir == conv.dir
    assert [c.chat_id for c in conv_mod.list_conversations(tmp_path / "chats")] == [conv.chat_id]
    with pytest.raises(conv_mod.ConversationNotFound):
        conv_mod.load_conversation(tmp_path / "chats", "nope")
    with pytest.raises(FileExistsError):
        conv_mod.new_conversation(tmp_path / "chats", "scripted", tmp_path, chat_id=conv.chat_id)


def test_deltas_stream_through_but_only_the_full_text_lands_on_disk(tmp_path):
    """外层 #65：逐字片段往外吐（CLI / SSE 靠它），events.jsonl 只留完整事件，transcript 不变。"""
    conv, chat = start(tmp_path, streamed("你好，研究者", pieces=3))
    events = drain(conv, chat, "你好")
    assert [e.kind for e in events] == ["init", "delta", "delta", "delta", "text", "done"]
    assert "".join(e.text for e in events if e.kind == "delta") == "你好，研究者"
    lines = (conv.dir / "turn-1" / "events.jsonl").read_text(encoding="utf-8").splitlines()
    assert [json.loads(line)["type"] for line in lines] == ["system", "assistant", "result"]
    turn = conv_mod.read_turns(conv)[0]
    assert turn["reply"] == "你好，研究者"
    # trace.jsonl 是同一轮的框架事件（不分后端），delta 不落盘；老轮次没有这个文件就是空列表
    assert [e["kind"] for e in turn["events"]] == ["init", "text", "done"]
    (conv.dir / "turn-1" / "trace.jsonl").unlink()
    assert conv_mod.read_turns(conv)[0]["events"] == []


def test_framework_origin_turn_is_labelled_and_chat_id_reaches_the_adapter(tmp_path):
    """外层 #63：框架叫醒的一轮标「框架」；适配器拿到 chat_id 好传给 agent 调用的命令。"""
    conv, chat = start(tmp_path, reply("醒了"), reply("好"))
    drain(conv, chat, "作业跑完了", origin="框架")
    assert chat.calls[0]["chat_id"] == conv.chat_id
    assert "**框架**：作业跑完了" in (conv.dir / "transcript.md").read_text(encoding="utf-8")
    drain(conv, chat, "谢谢")
    assert [t["origin"] for t in conv_mod.read_turns(conv)] == ["框架", "人"]
    with pytest.raises(ValueError, match="origin"):
        drain(conv, chat, "x", origin="机器人")


def test_tuning_is_remembered_on_meta_and_reaches_the_adapter_every_turn(tmp_path):
    """外层 #86：选了模型 / 思考深度就记进 meta，之后每轮沿用；给 None 是回到后端缺省。"""
    from backends import Tuning

    conv, chat = start(tmp_path, reply("一"), reply("二"), reply("三"))
    assert conv.tuning == Tuning() and conv.to_dict()["model"] is None
    drain(conv, chat, "第一句", tuning=Tuning(model="a", effort="high"))
    assert chat.calls[0]["tuning"] == Tuning(model="a", effort="high")
    meta = json.loads((conv.dir / "meta.json").read_text(encoding="utf-8"))
    assert meta["model"] == "a" and meta["effort"] == "high"
    drain(conv, chat, "第二句")  # 没给：沿用上次的
    assert chat.calls[1]["tuning"] == Tuning(model="a", effort="high")
    loaded = conv_mod.load_conversation(tmp_path / "chats", conv.chat_id)
    assert loaded.tuning == Tuning(model="a", effort="high")
    drain(loaded, chat, "第三句", tuning=Tuning())  # 回到缺省
    assert chat.calls[2]["tuning"] == Tuning()
    assert conv_mod.load_conversation(tmp_path / "chats", conv.chat_id).tuning == Tuning()
    # 开对话时就能带上
    fresh = conv_mod.new_conversation(tmp_path / "chats", "scripted", tmp_path,
                                      tuning=Tuning(effort="low"))
    assert fresh.tuning == Tuning(effort="low")


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

    reloaded = conv_mod.load_conversation(tmp_path / "chats", conv.chat_id)
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


def test_stale_lock_from_a_dead_process_is_reclaimed_but_a_live_one_is_honoured(tmp_path):
    """外层 #122：人打断把一轮杀在半路，inflight.json 留着，之后谁也没法跟这段对话说话。锁记 pid，
    发下一轮时进程不在了就自己收（半途的目录留着当证据）；pid 还活着照旧拒；老格式没 pid 当活着。"""
    import os

    conv, chat = start(tmp_path, reply("一"), reply("二"))
    lock = conv.dir / "inflight.json"
    lock.write_text(json.dumps({"turn": 1, "pid": 999_999_999, "started_at": "t"}),
                    encoding="utf-8")
    assert drain(conv, chat, "第一句")[-1].kind == "done" and conv.turns == 1
    lock.write_text(json.dumps({"turn": 2, "pid": os.getpid(), "started_at": "t"}),
                    encoding="utf-8")
    with pytest.raises(conv_mod.ConversationBusy):
        drain(conv, chat, "插队")
    lock.write_text(json.dumps({"turn": 2, "started_at": "t"}), encoding="utf-8")  # 老格式
    with pytest.raises(conv_mod.ConversationBusy):
        drain(conv, chat, "插队")
    lock.unlink()


def test_guide_change_between_turns_is_announced_to_the_agent(tmp_path):
    """外层 #122：平台中途加了命令（指南变了），助理照上一轮的记忆答「做不了」。指南的指纹记在
    meta，下一轮指纹变了就在话前面加一句提示；没变不加；第一轮不加。"""
    conv, chat = start(tmp_path, reply("一"), reply("二"), reply("三"))
    drain(conv, chat, "第一句")
    assert conv.guide_sha and not chat.calls[0]["message"].startswith("（平台提示")
    drain(conv, chat, "第二句")
    assert not chat.calls[1]["message"].startswith("（平台提示")
    list(conv_mod.send(conv, chat, "第三句", system_prompt=GUIDE + "\n新加了一条命令",
                       allowed_paths=[], bash_rules=()))
    sent = chat.calls[2]["message"]
    assert sent.startswith(conv_mod.GUIDE_CHANGED_NOTICE) and sent.endswith("第三句")
    assert (conv.dir / "turn-3" / "message.md").read_text(encoding="utf-8").startswith("（平台提示")
    reloaded = conv_mod.load_conversation(tmp_path / "chats", conv.chat_id)
    assert reloaded.guide_sha == conv.guide_sha


def test_guide_change_is_reinjected_in_full_for_thread_channel_clis(tmp_path):
    """P-25 / 外层 #131：Codex 只在开线程时收指南（developer_instructions，resume 再给不生效），
    指南变了
    框架把新指南全文塞进那一轮的话里；turn 渠道的（Claude Code 每轮整份送）只加一句提示。"""
    conv, chat = start(tmp_path, reply("一"), reply("二"))
    chat.guide_channel = "thread"
    drain(conv, chat, "第一句")
    list(conv_mod.send(conv, chat, "第二句", system_prompt=GUIDE + "\n新加了一条命令",
                       allowed_paths=[], bash_rules=()))
    sent = chat.calls[1]["message"]
    expected = conv_mod.GUIDE_REINJECT.format(guide=(GUIDE + "\n新加了一条命令").strip())
    assert sent.startswith(expected)
    assert conv_mod.GUIDE_CHANGED_NOTICE in sent and sent.endswith("第二句")
    assert "新加了一条命令" in sent  # 全文在话里
    # 第一轮（还没线程）不塞：那一轮的指南本来就会随开线程送到
    conv2, chat2 = start(tmp_path / "b", reply("一"))
    chat2.guide_channel = "thread"
    conv2.guide_sha = "stale"
    drain(conv2, chat2, "第一句")
    assert "<guide>" not in chat2.calls[0]["message"]


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


def test_session_cumulative_cost_is_turned_into_per_turn_cost(tmp_path):
    """Claude Code `--resume` 的 result.total_cost_usd 是整段会话的累计（实测七轮 0.165 → 0.284）：
    报 cost_reporting="session" 的后端，这一轮 = 这次报的 − 上次报的；换了会话从零算；NaN 照传。
    以前按轮累加的是累计值，meta 里的总花费被算成 $1.58，实际 $0.33。"""
    conv = conv_mod.new_conversation(tmp_path / "chats", "scripted", tmp_path)
    chat = ScriptedChat([reply("一", cost=0.10), reply("二", cost=0.15),
                         reply("三", cost=0.02, session="sess-0002"), reply("四", cost=float("nan"),
                                                                            session="sess-0002")],
                        cost_reporting="session")
    costs = [drain(conv, chat, f"第 {i} 轮")[-1].cost_usd for i in range(1, 5)]
    assert costs[:3] == pytest.approx([0.10, 0.05, 0.02])
    assert costs[3] != costs[3], "NaN 照传，不填 0"
    assert conv.cost_usd == pytest.approx(0.17) and conv.session_cost_usd == pytest.approx(0.02)
    # 落盘的 trace 与 SSE 同一份：done 里记的是这一轮的花费
    turn2 = conv_mod.read_turns(conv)[1]["events"][-1]
    assert turn2["kind"] == "done" and turn2["cost_usd"] == pytest.approx(0.05)
    # 按轮报的后端不减
    plain = ScriptedChat([reply("一", cost=0.10), reply("二", cost=0.15)])
    conv2 = conv_mod.new_conversation(tmp_path / "chats2", "scripted", tmp_path)
    assert [drain(conv2, plain, "x")[-1].cost_usd for _ in range(2)] == pytest.approx([0.10, 0.15])
