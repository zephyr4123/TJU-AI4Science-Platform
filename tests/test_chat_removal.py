"""删对话与删工作区时目录外那部分：这家 CLI 存的会话（`Chat.forget`）、每台机器上的镜像
（`Compute.remove_dir`）；适配器不在、机器连不上不吞也不拦——记一句、本机照删。"""

from __future__ import annotations

import json
import os

import pytest

from backends import BackendNotFound, ChatEvent
from compute import ComputeError
from framework import computes
from framework.chat import conversation, removal, scope
from framework.workspace import outputs
from framework.workspace import root as ws_mod
from tests.fixtures.scripted_chat import ScriptedChat


def _ws(tmp_path):
    return ws_mod.create(ws_mod.workspaces_root(tmp_path), "w")


def _chat_with_session(where, backend="claude_code", session="sess-1"):
    conv = conversation.new_conversation(where.chats, backend, where.cwd)
    conv.session_id = session
    conv.save()
    return conv


def test_remove_chat_forgets_the_cli_session_and_refuses_while_a_turn_runs(tmp_path):
    ws = _ws(tmp_path)
    where = scope.for_workspace(ws)
    chat = ScriptedChat([[ChatEvent(kind="done", text="")]])
    conv = _chat_with_session(where)
    removed = removal.remove_chat(where, conv.chat_id, lambda name: chat)
    assert removed.what == conv.chat_id and removed.clean
    assert chat.forgotten == ["sess-1"] and not conv.dir.exists()
    # 正在一轮里（锁的主人活着）：拒
    conv = _chat_with_session(where, session="sess-2")
    (conv.dir / conversation.INFLIGHT_NAME).write_text(json.dumps({"pid": os.getpid()}))
    with pytest.raises(conversation.ConversationBusy):
        removal.remove_chat(where, conv.chat_id, lambda name: chat)
    assert conv.dir.exists()
    # 适配器不在：目录照删，记一句
    (conv.dir / conversation.INFLIGHT_NAME).unlink()

    def missing(name):
        raise BackendNotFound(f"未知的 agent 后端 {name!r}")

    removed = removal.remove_chat(where, conv.chat_id, missing)
    assert not conv.dir.exists()
    assert removed.leftovers == ["claude_code 那边的会话没清：未知的 agent 后端 'claude_code'"]


def test_remove_workspace_forgets_every_chat_and_wipes_mirrors(tmp_path, monkeypatch):
    ws = _ws(tmp_path)
    where = scope.for_workspace(ws)
    chat = ScriptedChat([])
    _chat_with_session(where, session="a")
    _chat_with_session(where, backend="codex", session="b")
    for name in ("autodl", "gone"):
        d, m = outputs.open_output(ws, "design", title="t", by="design", inputs=[], params={},
                                   flow=None, step=None, requirement=1, chat_id=None,
                                   compute={"name": name, "kind": "ssh"})
        outputs.close_output(d, m, ok=True, line="ok")
    wiped: list[str] = []

    class FakeCompute:
        root = "/remote"

        def remote_dir_for(self, local_dir):
            return f"/remote{local_dir}"

        def remove_dir(self, remote_dir):
            wiped.append(remote_dir)

    class BrokenCompute(FakeCompute):
        def remove_dir(self, remote_dir):
            raise ComputeError("连不上")

    def instance(name):
        return {"autodl": FakeCompute(), "gone": BrokenCompute()}[name]

    monkeypatch.setattr(computes, "instance", instance)
    removed = removal.remove_workspace(ws, lambda name: chat)
    assert sorted(chat.forgotten) == ["a", "b"]
    assert wiped == [f"/remote{ws.root}"]
    assert removed.leftovers == ["gone 上的镜像没删：连不上"] and not ws.root.exists()
