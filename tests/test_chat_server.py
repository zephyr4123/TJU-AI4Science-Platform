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
WORKFLOWS = [{"name": "w", "title": "一条", "summary": "…", "assumes": [],
              "steps": [{"by": "助理", "does": "接", "cap": "design", "key": None}],
              "problems": []}]


def flow_check(steps: list[str]) -> dict:
    """剧本版：与 cli.serve._flow_check 同形状，只认 CATALOG 里的名字。"""
    known = {c["name"] for c in CATALOG}
    unknown = [s for s in steps if s not in known]
    return {"steps": steps, "problems": [f"没有这些能力：{unknown}"] if unknown else []}


def ui_dir(tmp_path):
    """一个最小的页面构建目录：index.html 与一个带哈希名的 assets 文件。"""
    root = tmp_path / "dist"
    (root / "assets").mkdir(parents=True)
    (root / "index.html").write_text("<!doctype html><title>ai4sci</title>", encoding="utf-8")
    (root / "assets" / "app-abc123.js").write_text("console.log(1)", encoding="utf-8")
    return root


@pytest.fixture
def served(tmp_path):
    chat = ScriptedChat([reply("你好"), with_tool("三个", "Bash", {"command": "ls"}, "a\nb")])

    def factory(name: str):
        if name != "claude_code":
            raise BackendNotFound(f"未知的 agent 后端 {name!r}")
        return chat

    server = ChatServer(("127.0.0.1", 0), runs_root=tmp_path / "runs", cwd=tmp_path,
                        catalog=lambda: CATALOG, workflows=lambda: WORKFLOWS,
                        flow_check=flow_check, chat_factory=factory,
                        system_prompt="指南", ui_dir=ui_dir(tmp_path))
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
    status, _, body = call(base, "/workflows")
    assert status == 200 and json.loads(body) == WORKFLOWS


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
    assert status == 200 and doc["turns"] == 2 and doc["history"] == [
        {"turn": 1, "message": "你好", "reply": "你好"},
        {"turn": 2, "message": "有几个？", "reply": "三个"}]
    assert "## 第 2 轮" in doc["transcript"]
    status, _, body = call(base, "/chats")
    assert status == 200 and [(c["chat_id"], c["title"]) for c in json.loads(body)] == [
        (chat_id, "你好")]


def test_error_status_codes(served, tmp_path):
    base, _ = served
    assert call(base, "/chats/nope")[0] == 404
    assert call(base, "/chats/nope/messages", {"text": "x"})[0] == 404
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


# ── 看板端点、两颗键、静态页 ──────────────────────────────────────────────
def test_task_board_and_publish_key(served, tmp_path):
    from tests.fixtures.packs_factory import make_pack

    base, _ = served
    pack = make_pack(tmp_path, published=False)
    status, _, body = call(base, "/tasks")
    rows = json.loads(body)
    assert status == 200 and [r["id"] for r in rows] == ["toy"]
    assert rows[0]["stage"] == "drafting" and rows[0]["publish"]["ok"] is False

    status, _, body = call(base, "/tasks/toy")
    doc = json.loads(body)
    assert status == 200 and doc["design"] and doc["headroom"]["metric"] == "val_mse"
    assert call(base, "/tasks/nope")[0] == 404
    assert call(base, "/tasks/../etc")[0] == 404

    assert call(base, "/tasks/toy/publish", {})[0] == 400  # 不署名不发
    status, _, body = call(base, "/tasks/toy/publish", {"by": "张三"})
    doc = json.loads(body)
    assert status == 201
    assert doc["publish"] == {"ok": True, "state": "ok", "by": "张三", "at": doc["publish"]["at"],
                              "reason": None}
    assert doc["stage"] == "baselined" and (pack.task_dir / "publish.json").is_file()

    (pack.task_dir / "design.md").write_text("", encoding="utf-8")  # 空 design 发不了
    status, _, body = call(base, "/tasks/toy/publish", {"by": "张三"})
    assert status == 422 and "design.md" in json.loads(body)["error"]


def test_run_board_and_accept_key(served, tmp_path):
    from tests.fixtures.runs_factory import make_run

    base, _ = served
    assert json.loads(call(base, "/runs")[2]) == []
    run_dir = make_run(tmp_path)
    assert run_dir.parent == tmp_path / "runs"
    status, _, body = call(base, "/runs")
    rows = json.loads(body)
    assert status == 200 and rows[0]["run_id"] == run_dir.name and rows[0]["accept"] is None
    status, _, body = call(base, f"/runs/{run_dir.name}")
    doc = json.loads(body)
    assert status == 200 and len(doc["ledger"]) == 3
    assert call(base, "/runs/nope")[0] == 404
    assert call(base, "/runs/../runs")[0] == 404

    assert call(base, f"/runs/{run_dir.name}/accept", {"by": ""})[0] == 400
    status, _, body = call(base, f"/runs/{run_dir.name}/accept", {"by": "李四"})
    doc = json.loads(body)
    assert status == 201 and doc["accept"]["by"] == "李四" and doc["accept"]["stale"] is False
    (run_dir / "experiment" / "inflight.json").write_text("{}", encoding="utf-8")
    status, _, body = call(base, f"/runs/{run_dir.name}/accept", {"by": "李四"})
    assert status == 422 and "正在跑" in json.loads(body)["error"]


def test_flow_check_endpoint(served):
    base, _ = served
    assert call(base, "/flow/check")[0] == 400
    status, _, body = call(base, "/flow/check?steps=design,experiment")
    assert status == 200 and json.loads(body) == {"steps": ["design", "experiment"], "problems": []}
    status, _, body = call(base, "/flow/check?steps=design,nope")
    assert status == 200 and "nope" in json.loads(body)["problems"][0]


def test_static_page_and_spa_fallback(served):
    base, _ = served
    status, ctype, body = call(base, "/")
    assert status == 200 and ctype.startswith("text/html") and "ai4sci" in body
    status, ctype, body = call(base, "/assets/app-abc123.js")
    assert status == 200 and "javascript" in ctype
    status, ctype, body = call(base, "/some/client/route")  # 单页应用的路由回 index.html
    assert status == 200 and ctype.startswith("text/html")
    assert call(base, "/nothing")[0] == 200  # 同上：不是接口前缀的路径都归页面
    assert call(base, "/chats/x/y/z")[0] == 404  # 接口前缀下的怪路径还是 404


def test_no_ui_dir_says_how_to_build(tmp_path):
    server = ChatServer(("127.0.0.1", 0), runs_root=tmp_path / "runs", cwd=tmp_path,
                        catalog=lambda: CATALOG, workflows=lambda: WORKFLOWS,
                        flow_check=flow_check, system_prompt="指南")
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        status, _, body = call(f"http://127.0.0.1:{server.server_address[1]}", "/")
        assert status == 404 and "npm run build" in json.loads(body)["error"]
    finally:
        server.shutdown()
        server.server_close()
