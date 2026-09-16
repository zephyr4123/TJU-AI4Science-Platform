"""HTTP 后端：端点形状、SSE 事件流、忙与错误的状态码。真 server 起在随机端口，剧本适配器。"""

from __future__ import annotations

import json
import threading
import urllib.error
import urllib.request

import pytest

from backends import BackendNotFound
from framework.chat.server import ChatServer
from tests.fixtures.scripted_chat import ScriptedChat, reply, with_tool

CATALOG = [{"name": "design", "level": "task"}, {"name": "experiment", "level": "run"}]


@pytest.fixture
def served(tmp_path):
    chat = ScriptedChat([reply("你好"), with_tool("三个", "Bash", {"command": "ls"}, "a\nb")])

    def factory(name: str):
        if name != "claude_code":
            raise BackendNotFound(f"未知的 agent 后端 {name!r}")
        return chat

    server = ChatServer(("127.0.0.1", 0), runs_root=tmp_path / "runs", cwd=tmp_path,
                        catalog=lambda: CATALOG, chat_factory=factory, system_prompt="指南")
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_address[1]}"
    yield base, chat
    server.shutdown()
    server.server_close()


def call(base, path, body=None, method=None):
    data = None if body is None else json.dumps(body).encode("utf-8")
    req = urllib.request.Request(base + path, data=data,
                                 method=method or ("POST" if data else "GET"),
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status, resp.headers.get("Content-Type", ""), resp.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.headers.get("Content-Type", ""), exc.read().decode("utf-8")


def sse_events(text: str) -> list[dict]:
    out = []
    for block in text.strip().split("\n\n"):
        lines = dict(line.split(": ", 1) for line in block.splitlines())
        out.append({"event": lines["event"], **json.loads(lines["data"])})
    return out


def test_health_and_catalog(served):
    base, _ = served
    assert call(base, "/health")[2] == '{"ok": true}'
    status, ctype, body = call(base, "/cap")
    assert status == 200 and "application/json" in ctype and json.loads(body) == CATALOG


def test_chat_lifecycle_over_http(served):
    base, chat = served
    status, _, body = call(base, "/chats", {})
    assert status == 201
    meta = json.loads(body)
    chat_id = meta["chat_id"]
    assert meta["backend"] == "claude_code" and meta["turns"] == 0

    status, ctype, body = call(base, f"/chats/{chat_id}/messages", {"text": "你好"})
    assert status == 200 and ctype.startswith("text/event-stream")
    events = sse_events(body)
    assert [e["event"] for e in events] == ["init", "text", "done"]
    assert events[-1]["cost_usd"] == pytest.approx(0.01) and events[-1]["session_id"]

    status, _, body = call(base, f"/chats/{chat_id}/messages", {"text": "有几个？"})
    events = sse_events(body)
    assert [e["event"] for e in events] == ["init", "tool_use", "tool_result", "text", "done"]
    assert events[1]["tool"] == "Bash" and events[1]["tool_input"] == {"command": "ls"}
    assert chat.calls[1]["session_id"] == chat.calls[0]["session_id"] or chat.calls[1]["session_id"]

    status, _, body = call(base, f"/chats/{chat_id}")
    doc = json.loads(body)
    assert status == 200 and doc["turns"] == 2 and "## 第 2 轮" in doc["transcript"]
    status, _, body = call(base, "/chats")
    assert status == 200 and [c["chat_id"] for c in json.loads(body)] == [chat_id]


def test_error_status_codes(served, tmp_path):
    base, _ = served
    assert call(base, "/chats/nope")[0] == 404
    assert call(base, "/chats/nope/messages", {"text": "x"})[0] == 404
    assert call(base, "/nothing")[0] == 404
    status, _, body = call(base, "/chats", {"backend": "nope"})
    assert status == 400 and "nope" in json.loads(body)["error"]
    chat_id = json.loads(call(base, "/chats", {})[2])["chat_id"]
    assert call(base, f"/chats/{chat_id}/messages", {"text": "  "})[0] == 400
    assert call(base, f"/chats/{chat_id}/messages", {})[0] == 400
    (tmp_path / "runs" / "chats" / chat_id / "inflight.json").write_text("{}", encoding="utf-8")
    status, _, body = call(base, f"/chats/{chat_id}/messages", {"text": "插队"})
    assert status == 409 and "在跑" in json.loads(body)["error"]


def test_bad_json_body_is_400(served):
    base, _ = served
    req = urllib.request.Request(base + "/chats", data=b"{not json", method="POST",
                                 headers={"Content-Type": "application/json"})
    with pytest.raises(urllib.error.HTTPError) as exc:
        urllib.request.urlopen(req, timeout=10)
    assert exc.value.code == 400
