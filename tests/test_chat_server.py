"""HTTP 后端：端点形状、按域分前缀、SSE 事件流、忙与错误的状态码。真 server 起在随机端口。"""

from __future__ import annotations

import json
import threading
import urllib.error
import urllib.request

import pytest

from backends import BackendNotFound
from framework import paths
from framework.chat.server import ChatServer
from framework.run import workspace
from tests.fixtures.scripted_chat import KNOBS, ScriptedChat, reply, with_tool

CATALOG = [{"name": "design", "level": "task"}, {"name": "experiment", "level": "run"}]
WORKFLOWS = [{"name": "w", "title": "一条", "summary": "…", "assumes": [],
              "steps": [{"by": "助理", "does": "接", "cap": "design", "key": None}],
              "problems": []}]
PROMPTS = {"workspace": "研究助理指南", "studio": "造流助理指南"}


def flow_check(steps: list[str]) -> dict:
    """剧本版：与 cli.serve._flow_check 同形状，只认 CATALOG 里的名字。"""
    known = {c["name"] for c in CATALOG}
    unknown = [s for s in steps if s not in known]
    return {"steps": steps, "problems": [f"没有这些能力：{unknown}"] if unknown else []}


def flows(ws: workspace.Workspace) -> list[dict]:
    """剧本版：工作区里有几个 yaml 就回几条；有个叫 boom 的就抛，模拟盘上的东西不合约。"""
    if (ws.flows / "boom.yaml").exists():
        raise ValueError("boom.yaml: 坏了")
    return [{"name": p.stem} for p in sorted(ws.flows.glob("*.yaml"))]


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

    def save_workflow(doc: dict) -> dict:
        if doc.get("name") == "taken":
            raise FileExistsError("已经有一条叫 'taken' 的流")
        if not doc.get("steps"):
            raise ValueError("x.yaml: steps 要是非空列表")
        return {**doc, "covers": ["实验"], "remarks": [], "problems": []}

    server = ChatServer(("127.0.0.1", 0), home=tmp_path, catalog=lambda: CATALOG,
                        workflows=lambda: WORKFLOWS, flows=flows, flow_check=flow_check,
                        save_workflow=save_workflow, chat_factory=factory,
                        system_prompts=PROMPTS, ui_dir=ui_dir(tmp_path))
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


def new_workspace(base, ws_id="w1", title=""):
    status, _, body = call(base, "/workspaces", {"id": ws_id, "title": title})
    assert status == 201, body
    return json.loads(body)


def test_health_and_catalog(served):
    base, _ = served
    assert call(base, "/health")[2] == '{"ok": true}'
    status, _, body = call(base, "/stages")
    assert status == 200
    assert json.loads(body) == ["文献", "假设", "设计", "实验", "分析", "写作", "验证"]
    status, ctype, body = call(base, "/cap")
    assert status == 200 and "application/json" in ctype and json.loads(body) == CATALOG
    status, _, body = call(base, "/workflows")
    assert status == 200 and json.loads(body) == WORKFLOWS


def test_workspaces_are_created_listed_and_read(served, tmp_path):
    """工作区（纲领 P-15）：起、列、读一整份；名字规矩与重名的状态码；URL 片段拼不出路径。"""
    base, _ = served
    assert json.loads(call(base, "/workspaces")[2]) == []
    made = new_workspace(base, "rahman-nll", "Rahman 稳定性")
    assert made["id"] == "rahman-nll" and made["title"] == "Rahman 稳定性"
    assert made["task"] is None and made["runs"] == 0
    assert (tmp_path / "workspaces" / "rahman-nll" / "workspace.yaml").is_file()
    assert call(base, "/workspaces", {"id": "rahman-nll"})[0] == 409
    assert call(base, "/workspaces", {"id": "Bad Name"})[0] == 400
    assert call(base, "/workspaces", {})[0] == 400
    status, _, body = call(base, "/workspaces/rahman-nll")
    doc = json.loads(body)
    assert status == 200 and doc["task"] is None and doc["runs"] == [] and doc["flows"] == []
    assert [w["id"] for w in json.loads(call(base, "/workspaces")[2])] == ["rahman-nll"]
    assert call(base, "/workspaces/nope")[0] == 404
    assert call(base, "/workspaces/../etc")[0] == 404
    assert call(base, "/workspaces/rahman-nll/nothing")[0] == 404


@pytest.mark.parametrize("prefix", ["/workspaces/w1", "/studio"])
def test_chat_lifecycle_in_both_scopes(served, tmp_path, prefix):
    """对话四个端点在两个域下共用一套：工作区的对话落在工作区里，编辑台的落在 studio/ 里；
    两位助理各拿各的指南、各写各的目录（P-16）。"""
    base, chat = served
    new_workspace(base, "w1")
    status, _, body = call(base, f"{prefix}/chats", {})
    assert status == 201
    meta = json.loads(body)
    chat_id = meta["chat_id"]
    assert meta["backend"] == "claude_code" and meta["turns"] == 0
    where = tmp_path / ("studio" if prefix == "/studio" else "workspaces/w1")
    assert (where / "chats" / chat_id / "meta.json").is_file()

    status, ctype, body = call(base, f"{prefix}/chats/{chat_id}/messages", {"text": "你好"})
    assert status == 200 and ctype.startswith("text/event-stream")
    events = sse_events(body)
    assert [e["event"] for e in events] == ["init", "text", "done"]
    assert events[-1]["cost_usd"] == pytest.approx(0.01) and events[-1]["session_id"]
    call_ = chat.calls[-1]
    if prefix == "/studio":
        assert call_["system_prompt"] == "造流助理指南"
        assert call_["cwd"] == paths.workflows_root().parent
        assert call_["allowed_paths"] == [paths.workflows_root()] and call_["readable_paths"] == []
    else:
        ws = workspace.load(tmp_path / "workspaces" / "w1")
        assert call_["system_prompt"] == "研究助理指南" and call_["cwd"] == ws.root
        assert call_["allowed_paths"] == [ws.task, ws.flows, ws.runs]
        assert call_["readable_paths"] == [paths.workflows_root()]  # 库可读不可写

    status, _, body = call(base, f"{prefix}/chats/{chat_id}/messages", {"text": "有几个？"})
    events = sse_events(body)
    assert [e["event"] for e in events] == ["init", "tool_use", "tool_result", "text", "done"]
    assert events[1]["tool"] == "Bash" and events[1]["tool_input"] == {"command": "ls"}

    status, _, body = call(base, f"{prefix}/chats/{chat_id}")
    doc = json.loads(body)
    assert status == 200 and doc["turns"] == 2 and doc["history"] == [
        {"turn": 1, "origin": "人", "message": "你好", "reply": "你好"},
        {"turn": 2, "origin": "人", "message": "有几个？", "reply": "三个"}]
    assert "## 第 2 轮" in doc["transcript"]
    status, _, body = call(base, f"{prefix}/chats")
    assert status == 200 and [(c["chat_id"], c["title"]) for c in json.loads(body)] == [
        (chat_id, "你好")]
    # 另一个域看不到这段对话
    other = "/studio" if prefix != "/studio" else "/workspaces/w1"
    assert json.loads(call(base, f"{other}/chats")[2]) == []
    assert call(base, f"{other}/chats/{chat_id}")[0] == 404


def test_backends_endpoint_reports_each_backends_knobs(served):
    """外层 #86：页面照单渲染模型与思考深度两枚旋钮，清单是后端自报的。"""
    base, _ = served
    status, _, body = call(base, "/backends")
    assert status == 200
    [claude] = json.loads(body)
    assert claude["name"] == "claude_code" and claude["default"] is True
    assert claude["models"] == [{"id": "a", "label": "甲", "note": "快"},
                                {"id": "b", "label": "乙", "note": ""}]
    assert [e["id"] for e in claude["efforts"]] == ["low", "high"]
    assert claude["model"] is None and claude["effort"] is None


def test_chat_tuning_is_checked_against_the_knobs_and_remembered(served, tmp_path):
    """外层 #86：开对话与发消息都能带 model / effort；不在清单上 400；给了记住、null 回缺省。"""
    from backends import Tuning

    base, chat = served
    chat.turns.append(reply("三"))
    status, _, body = call(base, "/studio/chats", {"model": "zz"})
    assert status == 400 and "模型 'zz' 不在清单上" in json.loads(body)["error"]
    status, _, body = call(base, "/studio/chats", {"effort": 3})
    assert status == 400 and json.loads(body)["error"] == "effort 要是字符串或 null"
    status, _, body = call(base, "/studio/chats", {"model": "a"})
    assert status == 201
    meta = json.loads(body)
    assert meta["model"] == "a" and meta["effort"] is None
    chat_id = meta["chat_id"]

    # 发消息时改深度：模型沿用对话上记的，深度记进去
    status, _, body = call(base, f"/studio/chats/{chat_id}/messages",
                           {"text": "你好", "effort": "high"})
    assert status == 200 and sse_events(body)[-1]["event"] == "done"
    assert chat.calls[-1]["tuning"] == Tuning(model="a", effort="high")
    doc = json.loads(call(base, f"/studio/chats/{chat_id}")[2])
    assert doc["model"] == "a" and doc["effort"] == "high"
    # 不在清单上的在头响应之前就拒，不开始流、不算一轮
    status, _, body = call(base, f"/studio/chats/{chat_id}/messages",
                           {"text": "再来", "effort": "ultra"})
    assert status == 400
    assert "思考深度 'ultra' 不在清单上；可选：low, high" in json.loads(body)["error"]
    assert not (tmp_path / "studio" / "chats" / chat_id / "turn-2").exists()
    # null 是回到后端缺省
    status, _, body = call(base, f"/studio/chats/{chat_id}/messages",
                           {"text": "再来", "model": None, "effort": None})
    assert status == 200 and chat.calls[-1]["tuning"] == Tuning()
    doc = json.loads(call(base, f"/studio/chats/{chat_id}")[2])
    assert doc["model"] is None and doc["effort"] is None and doc["turns"] == 2
    assert KNOBS.models[0].id == "a"  # 清单与剧本夹具对账


def test_error_status_codes(served, tmp_path):
    base, _ = served
    new_workspace(base, "w1")
    assert call(base, "/workspaces/w1/chats/nope")[0] == 404
    assert call(base, "/workspaces/w1/chats/nope/messages", {"text": "x"})[0] == 404
    assert call(base, "/workspaces/nope/chats", {})[0] == 404
    status, _, body = call(base, "/workspaces/w1/chats", {"backend": "nope"})
    assert status == 400 and "nope" in json.loads(body)["error"]
    chat_id = json.loads(call(base, "/workspaces/w1/chats", {})[2])["chat_id"]
    assert call(base, f"/workspaces/w1/chats/{chat_id}/messages", {"text": "  "})[0] == 400
    assert call(base, f"/workspaces/w1/chats/{chat_id}/messages", {})[0] == 400
    (tmp_path / "workspaces" / "w1" / "chats" / chat_id / "inflight.json").write_text(
        "{}", encoding="utf-8")
    status, _, body = call(base, f"/workspaces/w1/chats/{chat_id}/messages", {"text": "插队"})
    assert status == 409 and "在跑" in json.loads(body)["error"]
    assert call(base, "/studio/runs")[0] == 404  # 编辑台下只有对话
    assert call(base, "/studio/publish", {"by": "x"})[0] == 404


def test_bad_json_body_is_400(served):
    base, _ = served
    req = urllib.request.Request(base + "/workspaces", data=b"{not json", method="POST",
                                 headers={"Content-Type": "application/json"})
    with pytest.raises(urllib.error.HTTPError) as exc:
        urllib.request.urlopen(req, timeout=10)
    assert exc.value.code == 400


# ── 看板端点、两颗键、静态页 ──────────────────────────────────────────────
def test_workspace_board_and_publish_key(served, tmp_path):
    from tests.fixtures.packs_factory import make_pack

    base, _ = served
    pack = make_pack(tmp_path, published=False)  # 夹具的工作区 toy 落在同一个 home 下
    status, _, body = call(base, "/workspaces")
    rows = json.loads(body)
    assert status == 200 and [r["id"] for r in rows] == ["toy"]
    assert rows[0]["task"]["stage"] == "drafting" and rows[0]["task"]["publish"]["ok"] is False

    status, _, body = call(base, "/workspaces/toy")
    doc = json.loads(body)
    assert status == 200 and doc["task"]["design"]
    assert doc["task"]["headroom"]["metric"] == "val_mse"
    (pack.workspace.flows).mkdir()
    (pack.workspace.flows / "mine.yaml").write_text("name: mine\n", encoding="utf-8")
    assert json.loads(call(base, "/workspaces/toy/flows")[2]) == [{"name": "mine"}]
    assert json.loads(call(base, "/workspaces/toy")[2])["flows"] == [{"name": "mine"}]
    # 盘上的东西不合约：回 422 一句话，不是断连接让页面「Failed to fetch」
    (pack.workspace.flows / "boom.yaml").write_text("", encoding="utf-8")
    status, _, body = call(base, "/workspaces/toy")
    assert status == 422 and "boom.yaml: 坏了" in json.loads(body)["error"]
    (pack.workspace.flows / "boom.yaml").unlink()

    assert call(base, "/workspaces/toy/publish", {})[0] == 400  # 不署名不发
    status, _, body = call(base, "/workspaces/toy/publish", {"by": "张三"})
    doc = json.loads(body)
    assert status == 201
    assert doc["publish"] == {"ok": True, "state": "ok", "by": "张三", "at": doc["publish"]["at"],
                              "reason": None}
    assert doc["stage"] == "baselined" and (pack.task_dir / "publish.json").is_file()

    (pack.task_dir / "design.md").write_text("", encoding="utf-8")  # 空 design 发不了
    status, _, body = call(base, "/workspaces/toy/publish", {"by": "张三"})
    assert status == 422 and "design.md" in json.loads(body)["error"]


def test_run_board_and_accept_key(served, tmp_path):
    from tests.fixtures.runs_factory import make_run

    base, _ = served
    run_dir = make_run(tmp_path)
    assert run_dir.parent.parent == tmp_path / "workspaces" / "toy"
    status, _, body = call(base, "/workspaces/toy/runs")
    rows = json.loads(body)
    assert status == 200 and rows[0]["run_id"] == run_dir.name and rows[0]["accept"] is None
    assert json.loads(call(base, "/workspaces/toy")[2])["runs"][0]["run_id"] == run_dir.name
    status, _, body = call(base, f"/workspaces/toy/runs/{run_dir.name}")
    doc = json.loads(body)
    assert status == 200 and len(doc["ledger"]) == 3
    assert call(base, "/workspaces/toy/runs/nope")[0] == 404
    assert call(base, "/workspaces/toy/runs/../runs")[0] == 404

    assert call(base, f"/workspaces/toy/runs/{run_dir.name}/accept", {"by": ""})[0] == 400
    status, _, body = call(base, f"/workspaces/toy/runs/{run_dir.name}/accept", {"by": "李四"})
    doc = json.loads(body)
    assert status == 201 and doc["accept"]["by"] == "李四" and doc["accept"]["stale"] is False
    (run_dir / "experiment" / "inflight.json").write_text("{}", encoding="utf-8")
    status, _, body = call(base, f"/workspaces/toy/runs/{run_dir.name}/accept", {"by": "李四"})
    assert status == 422 and "正在跑" in json.loads(body)["error"]


def test_jobs_endpoints(served, tmp_path):
    """作业清单与单个作业（外层 #63）：run 看板带正在跑的作业与全部作业。"""
    import os

    from framework.run import jobs
    from tests.fixtures.runs_factory import make_run

    base, _ = served
    run_dir = make_run(tmp_path)
    assert json.loads(call(base, "/workspaces/toy/jobs")[2]) == []
    assert call(base, "/workspaces/toy/jobs/nope")[0] == 404
    job = jobs.Job(job_id="job-1", cap="experiment", level="run", target=run_dir.name,
                   argv=["cap", "experiment", run_dir.name], pid=os.getpid(), started_at="t")
    jobs._save(tmp_path / "workspaces" / "toy" / "jobs", job)
    status, _, body = call(base, "/workspaces/toy/jobs/job-1")
    assert status == 200 and json.loads(body)["effective_status"] == "running"
    doc = json.loads(call(base, f"/workspaces/toy/runs/{run_dir.name}")[2])
    assert doc["job"]["job_id"] == "job-1" and [j["job_id"] for j in doc["jobs"]] == ["job-1"]
    assert json.loads(call(base, "/workspaces/toy/runs")[2])[0]["job"]["job_id"] == "job-1"


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
    assert call(base, "/studio/x/y/z")[0] == 404  # 接口前缀下的怪路径还是 404


def test_no_ui_dir_says_how_to_build(tmp_path):
    server = ChatServer(("127.0.0.1", 0), home=tmp_path, catalog=lambda: CATALOG,
                        workflows=lambda: WORKFLOWS, flows=flows, flow_check=flow_check,
                        system_prompts=PROMPTS)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        status, _, body = call(f"http://127.0.0.1:{server.server_address[1]}", "/")
        assert status == 404 and "npm run build" in json.loads(body)["error"]
    finally:
        server.shutdown()
        server.server_close()


def test_save_workflow_endpoint_maps_errors_to_status_codes(served):
    """编辑台存流（外层 #68）：存成 201 回清单里的样子；形状 / 不通 422；同名 409。"""
    base, _ = served
    doc = {"name": "w", "title": "t", "summary": "s",
           "steps": [{"by": "助理", "does": "x", "cap": "design"}]}
    status, _, body = call(base, "/workflows", doc)
    assert status == 201 and json.loads(body)["covers"] == ["实验"]
    assert call(base, "/workflows", {**doc, "steps": []})[0] == 422
    assert call(base, "/workflows", {**doc, "name": "taken"})[0] == 409
