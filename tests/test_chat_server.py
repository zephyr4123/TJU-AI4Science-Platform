"""HTTP 后端：端点形状、按域分前缀、SSE 事件流、忙与错误的状态码。真 server 起在随机端口。"""

from __future__ import annotations

import json
import threading
import urllib.error
import urllib.request

import pytest

from backends import AgentProbe, BackendNotFound, available_backends
from framework import paths
from framework.capabilities import stage_table
from framework.chat.server import ChatServer
from framework.cli import serve as serve_cli
from framework.workspace import root as workspace
from tests.fixtures.scripted_chat import KNOBS, ScriptedChat, reply, with_tool

CATALOG = [{"name": "design", "stage": "设计"}, {"name": "auto-research", "stage": "实验"}]
WORKFLOWS = [{"name": "w", "title": "一条", "summary": "…",
              "stages": [{"kind": "stage", "stage": "设计",
                          "caps": [{"cap": "design", "with": {}}]}],
              "covers": ["设计"], "remarks": [], "problems": []}]
PROMPTS = {"workspace": "研究助理指南", "studio": "流程助理指南"}


def check_workflow(doc: dict) -> dict:
    """剧本版：与 cli.serve._check_workflow 同形状，只认 CATALOG 里的名字。"""
    known = {c["name"] for c in CATALOG}
    caps = [c for room in doc.get("stages", []) if isinstance(room, dict)
            for caps in room.values() for c in (caps or [])]
    unknown = [c for c in caps if c not in known]
    return {"covers": ["设计"], "remarks": [],
            "problems": [f"没有这个能力：{unknown}"] if unknown else []}


def descriptors() -> dict:
    """流程实例的进度要按真描述符核对点名的能力：直接用仓里的四个。"""
    from framework.capabilities import discover
    return {name: module.DESCRIPTOR for name, module in discover().items()}


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
        # 顶着真适配器的名字（P-25 按人的设置按名字查每家的清单），两家都是同一份剧本
        if name not in available_backends():
            raise BackendNotFound(f"未知的 agent 后端 {name!r}")
        return chat

    def save_workflow(doc: dict) -> dict:
        if doc.get("name") == "taken":
            raise FileExistsError("已经有一条叫 'taken' 的流程")
        if not doc.get("stages"):
            raise ValueError("x.yaml: stages 要是非空列表")
        return {**doc, "covers": ["实验"], "remarks": [], "problems": []}

    def probe_agent(name: str) -> AgentProbe:
        # 自检不跑真 CLI：claude_code 过、codex 没登录
        if name == "codex":
            return AgentProbe(items=[("装了没", True, "/x"), ("登录", False, "没登录")],
                              installed=True, version="codex-cli 0.147.0")
        return AgentProbe(items=[("装了没", True, "/x"), ("说话", True, "pong")],
                          installed=True, version="2.1.278", logged_in=True, spoke_s=0.8)

    def add_compute(body: dict) -> dict:
        added.append(body)
        return {"agents": {}, "computes": [{"name": body["name"]}], "storage": {}}

    added: list[dict] = []
    server = ChatServer(("127.0.0.1", 0), home=tmp_path, catalog=lambda: CATALOG,
                        workflows=lambda: WORKFLOWS, check_workflow=check_workflow,
                        save_workflow=save_workflow, descriptors=descriptors,
                        stage_table=stage_table, chat_factory=factory, probe_agent=probe_agent,
                        add_compute=add_compute, system_prompts=PROMPTS, ui_dir=ui_dir(tmp_path))
    server.added = added
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
    assert json.loads(call(base, "/health")[2]) == {"ok": True, "checks_ok": True}
    status, _, body = call(base, "/stages")
    assert status == 200
    stages = json.loads(body)
    assert [s["name"] for s in stages] == ["文献", "假设", "设计", "实验", "分析", "写作", "验证"]
    assert stages[3] == {"name": "实验", "slug": "experiment",
                         "main_files": [{"name": "ledger.tsv", "label": "账本"},
                                        {"name": "results.json", "label": "结果"}]}
    assert stages[0]["main_files"] == [{"name": "sources.md", "label": "材料来源"}]  # P-24 定的
    status, _, body = call(base, "/templates")
    assert status == 200 and [t["name"] for t in json.loads(body)] == ["ai", "cs", "generic",
                                                                       "materials", "reproduce"]
    status, ctype, body = call(base, "/cap")
    assert status == 200 and "application/json" in ctype and json.loads(body) == CATALOG
    status, _, body = call(base, "/workflows")
    assert status == 200 and json.loads(body) == WORKFLOWS


def _unnamed(node, path="") -> list[str]:
    """走一遍响应体：带 id / name / slug 的对象要么有 title / label，要么 name 本身就是中文
    （阶段）。`cap` `flow` `by` 这类是对别的对象的引用，不是对象自己的名字，不在此列。"""
    found: list[str] = []
    if isinstance(node, dict):
        if any(k in node for k in ("id", "name", "slug")):
            name = node.get("name")
            readable = ("title" in node or "label" in node
                        or (isinstance(name, str) and not name.isascii()))
            if not readable:
                found.append(f"{path or '/'}: {sorted(node)}")
        for key, value in node.items():
            found += _unnamed(value, f"{path}.{key}")
    elif isinstance(node, list):
        for i, value in enumerate(node):
            found += _unnamed(value, f"{path}[{i}]")
    return found


def test_everything_named_in_the_page_api_carries_a_readable_name(tmp_path, monkeypatch):
    """P-21 内部名不上屏、翻译在源头：页面拿到的 JSON 里凡带 id / name / slug 的对象都带中文名
    （title / label），前端不用拼也不用猜。用仓里真的能力表与流程库起服务，起一个工作区，
    把页面会读的端点走一遍。"""
    monkeypatch.setenv("AI4SCI_HOME", str(tmp_path))
    server = ChatServer(("127.0.0.1", 0), home=tmp_path, catalog=serve_cli._catalog,
                        workflows=serve_cli._workflows, check_workflow=serve_cli._check_workflow,
                        descriptors=serve_cli._descriptor_map, stage_table=stage_table,
                        system_prompts=PROMPTS)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_address[1]}"
    try:
        new_workspace(base, "w1", "一个课题")
        for path in ("/stages", "/cap", "/workflows", "/templates", "/workspaces",
                     "/workspaces/w1"):
            status, _, body = call(base, path)
            assert status == 200, (path, body)
            assert _unnamed(json.loads(body), path) == [], path
        caps = json.loads(call(base, "/cap")[2])
        assert {c["name"]: c["title"] for c in caps}["auto-research"] == "AutoResearch"
        assert all(c["brief"] and all(p["label"] for p in c["params"]) for c in caps)
    finally:
        server.shutdown()
        server.server_close()


def test_workspaces_are_created_listed_and_read(served, tmp_path):
    """工作区（纲领 P-15）：起、列、读一整份；名字规矩与重名的状态码；URL 片段拼不出路径。"""
    base, _ = served
    assert json.loads(call(base, "/workspaces")[2]) == []
    made = new_workspace(base, "rahman-nll", "Rahman 稳定性")
    assert made["id"] == "rahman-nll" and made["title"] == "Rahman 稳定性"
    assert made["requirement"]["confirmed"] is False and made["running"] == 0
    requirement = tmp_path / "workspaces" / "rahman-nll" / "requirement.md"
    assert requirement.read_text(encoding="utf-8").startswith("# Rahman 稳定性\n")
    assert "## 问题" in requirement.read_text(encoding="utf-8")  # 按 generic 模板起草
    assert call(base, "/workspaces", {"id": "rahman-nll"})[0] == 409
    assert call(base, "/workspaces", {"id": "Bad Name"})[0] == 400
    assert call(base, "/workspaces", {"id": "x2", "template": "nope"})[0] == 400
    assert call(base, "/workspaces", {})[0] == 400
    status, _, body = call(base, "/workspaces/rahman-nll")
    doc = json.loads(body)
    assert status == 200 and doc["flows"] == [] and doc["jobs"] == []
    assert all(s["outputs"] == [] for s in doc["stages"])
    assert doc["requirement"]["title"] == "Rahman 稳定性" and doc["requirement"]["pending"]
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
    where = tmp_path / ("studio" if prefix == "/studio" else "workspaces/w1/.ai4sci")
    assert (where / "chats" / chat_id / "meta.json").is_file()

    status, ctype, body = call(base, f"{prefix}/chats/{chat_id}/messages", {"text": "你好"})
    assert status == 200 and ctype.startswith("text/event-stream")
    events = sse_events(body)
    assert [e["event"] for e in events] == ["init", "text", "done"]
    assert events[-1]["cost_usd"] == pytest.approx(0.01) and events[-1]["session_id"]
    call_ = chat.calls[-1]
    if prefix == "/studio":
        assert call_["system_prompt"] == "流程助理指南"
        assert call_["cwd"] == paths.workflows_root().parent
        assert call_["allowed_paths"] == [paths.workflows_root()] and call_["readable_paths"] == []
    else:
        ws = workspace.load(tmp_path / "workspaces" / "w1")
        assert call_["system_prompt"] == "研究助理指南" and call_["cwd"] == ws.root
        assert call_["allowed_paths"] == [ws.root]
        assert call_["readable_paths"] == [paths.workflows_root(), paths.templates_root()]

    status, _, body = call(base, f"{prefix}/chats/{chat_id}/messages", {"text": "有几个？"})
    events = sse_events(body)
    assert [e["event"] for e in events] == ["init", "tool_use", "tool_result", "text", "done"]
    assert events[1]["tool"] == "Bash" and events[1]["tool_input"] == {"command": "ls"}

    status, _, body = call(base, f"{prefix}/chats/{chat_id}")
    doc = json.loads(body)
    assert status == 200 and doc["turns"] == 2
    assert [{k: v for k, v in t.items() if k != "events"} for t in doc["history"]] == [
        {"turn": 1, "origin": "人", "message": "你好", "reply": "你好"},
        {"turn": 2, "origin": "人", "message": "有几个？", "reply": "三个"}]
    # 工具调用是对话的一部分：重开对话时 history 里带着这一轮的框架事件，页面照原样摆回去
    assert [e["kind"] for e in doc["history"][1]["events"]] == [
        "init", "tool_use", "tool_result", "text", "done"]
    assert doc["history"][1]["events"][1]["tool_input"] == {"command": "ls"}
    assert "## 第 2 轮" in doc["transcript"]
    status, _, body = call(base, f"{prefix}/chats")
    assert status == 200 and [(c["chat_id"], c["title"]) for c in json.loads(body)] == [
        (chat_id, "你好")]
    # 另一个域看不到这段对话
    other = "/studio" if prefix != "/studio" else "/workspaces/w1"
    assert json.loads(call(base, f"{other}/chats")[2]) == []
    assert call(base, f"{other}/chats/{chat_id}")[0] == 404


def test_backends_endpoint_reports_each_backends_knobs(served):
    """外层 #86 / P-25：页面照单渲染模型与思考深度两枚旋钮，清单是后端自报的；每家带产品名与新对话
    用的具体值（按人的设置，没填就是起点）；「对话用」那家 default。"""
    base, _ = served
    status, _, body = call(base, "/backends")
    assert status == 200
    rows = {r["name"]: r for r in json.loads(body)}
    assert set(rows) == set(available_backends())
    claude = rows["claude_code"]
    assert claude["default"] is True and claude["title"] == "Claude Code"
    assert rows["codex"]["default"] is False and rows["codex"]["title"] == "Codex"
    assert claude["models"] == [{"id": "a", "label": "甲", "note": "快"},
                                {"id": "b", "label": "乙", "note": ""}]
    assert [e["id"] for e in claude["efforts"]] == ["low", "high"]
    assert claude["model"] == "a" and claude["effort"] == "low"  # 起点：旋钮上没有「默认」
    # 设置里改了缺省，/backends 跟着变；换「对话用」那家，default 跟着换
    status, _, body = call(base, "/settings/agents",
                           {"chat": "codex", "agents": {"claude_code": {"model": "b"}}})
    assert status == 200, body
    rows = {r["name"]: r for r in json.loads(call(base, "/backends")[2])}
    assert rows["claude_code"]["model"] == "b" and rows["codex"]["default"] is True
    status, _, body = call(base, "/settings/agents", {"agents": {"claude_code": {"model": "zz"}}})
    assert status == 400 and "模型 'zz' 不在清单上" in json.loads(body)["error"]


def test_chat_tuning_is_checked_against_the_knobs_and_remembered(served, tmp_path):
    """外层 #86 / P-25：开对话与发消息都能带 model / effort；不在清单上 400；给了记住；没给的沿用，
    开对话时从按人的设置抄具体值——meta 里从来没有 null。"""
    from backends import Tuning

    base, chat = served
    chat.turns.append(reply("三"))
    status, _, body = call(base, "/studio/chats", {"model": "zz"})
    assert status == 400 and "模型 'zz' 不在清单上" in json.loads(body)["error"]
    status, _, body = call(base, "/studio/chats", {"effort": 3})
    assert status == 400 and json.loads(body)["error"] == "effort 要是字符串"
    status, _, body = call(base, "/studio/chats", {"model": "a"})
    assert status == 201
    meta = json.loads(body)
    assert meta["model"] == "a" and meta["effort"] == "low"  # 深度没给：设置里这家的起点
    chat_id = meta["chat_id"]

    # 发消息时改深度：模型沿用对话上记的，深度记进去
    status, _, body = call(base, f"/studio/chats/{chat_id}/messages",
                           {"text": "你好", "effort": "high"})
    assert status == 200 and sse_events(body)[-1]["event"] == "done"
    assert chat.calls[-1]["tuning"] == Tuning(model="a", effort="high")
    doc = json.loads(call(base, f"/studio/chats/{chat_id}")[2])
    assert doc["model"] == "a" and doc["effort"] == "high"
    # 不在清单上的在头响应之前就拒，不开始流程、不算一轮
    status, _, body = call(base, f"/studio/chats/{chat_id}/messages",
                           {"text": "再来", "effort": "ultra"})
    assert status == 400
    assert "思考深度 'ultra' 不在清单上；可选：low, high" in json.loads(body)["error"]
    assert not (tmp_path / "studio" / "chats" / chat_id / "turn-2").exists()
    # null 与没给一样：沿用对话上记的（旋钮上没有「回缺省」这一项）
    status, _, body = call(base, f"/studio/chats/{chat_id}/messages",
                           {"text": "再来", "model": None, "effort": None})
    assert status == 200 and chat.calls[-1]["tuning"] == Tuning(model="a", effort="high")
    doc = json.loads(call(base, f"/studio/chats/{chat_id}")[2])
    assert doc["model"] == "a" and doc["effort"] == "high" and doc["turns"] == 2
    assert KNOBS.models[0].id == "a"  # 清单与剧本夹具对账


def test_settings_endpoints_snapshot_check_and_computes(served, tmp_path):
    """P-25：设置那块板的读盘、真探（注入的 probe）、接机器、删机器；`/health` 的 checks_ok 随在用的
    那家上次自检翻转（没检查过不算没过）。"""
    base, _ = served
    status, _, body = call(base, "/settings")
    assert status == 200
    snap = json.loads(body)
    table = snap["agents"]
    assert table["chat"] == table["executor"] == "claude_code"
    codex = next(e for e in table["entries"] if e["name"] == "codex")
    assert codex["title"] == "Codex" and codex["last_check"] is None
    assert codex["models"][0]["id"] == "a"  # 清单跟着服务接的那家适配器（剧本）走
    assert [c["name"] for c in snap["computes"]] == ["local"]
    assert snap["storage"]["home"] == str(tmp_path) and snap["storage"]["writable"] is True
    assert json.loads(call(base, "/health")[2])["checks_ok"] is True

    status, _, body = call(base, "/settings/check", {"what": "agents"})
    assert status == 200
    report = json.loads(body)
    assert report["ok"] is False and report["failed"] == ["agent:codex"]
    codex = next(e for e in report["agents"]["entries"] if e["name"] == "codex")
    assert codex["last_check"]["items"][1] == {"name": "登录", "ok": False, "note": "没登录"}
    # codex 没在用（两层都是 claude_code）：页面那个点不亮；换成执行用 codex 就亮
    assert json.loads(call(base, "/health")[2])["checks_ok"] is True
    assert call(base, "/settings/agents", {"executor": "codex"})[0] == 200
    assert json.loads(call(base, "/health")[2])["checks_ok"] is False
    status, _, body = call(base, "/settings/check", {"what": "nope"})
    assert status == 400 and "what 只认" in json.loads(body)["error"]
    status, _, body = call(base, "/settings/check", {"what": "storage"})
    assert status == 200 and json.loads(body)["ok"] is True

    status, _, body = call(base, "/settings/computes",
                           {"name": "box", "ssh": "u@h:22", "key": "~/.ssh/id_ed25519"})
    assert status == 201 and json.loads(body)["computes"] == [{"name": "box"}]
    assert call(base, "/settings/computes/nope/remove", {})[0] == 400
    assert call(base, "/settings/computes/local/remove", {})[0] == 400  # 出厂的删不掉
    assert call(base, "/settings/nope", {})[0] == 404


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
    (tmp_path / "workspaces" / "w1" / ".ai4sci" / "chats" / chat_id / "inflight.json").write_text(
        "{}", encoding="utf-8")
    status, _, body = call(base, f"/workspaces/w1/chats/{chat_id}/messages", {"text": "插队"})
    assert status == 409 and "在跑" in json.loads(body)["error"]
    assert call(base, "/studio/requirement")[0] == 404  # 编辑台下只有对话
    assert call(base, "/studio/requirement/confirm", {"by": "x"})[0] == 404


def test_bad_json_body_is_400(served):
    base, _ = served
    req = urllib.request.Request(base + "/workspaces", data=b"{not json", method="POST",
                                 headers={"Content-Type": "application/json"})
    with pytest.raises(urllib.error.HTTPError) as exc:
        urllib.request.urlopen(req, timeout=10)
    assert exc.value.code == 400


# ── 看板端点、确认与签字、静态页 ──────────────────────────────────────────────
def test_requirement_board_and_confirm(served, tmp_path):
    from framework.contracts import requirement
    from tests.fixtures.packs_factory import REQUIREMENT, make_workspace

    base, _ = served
    ws = make_workspace(tmp_path, "toy", confirmed=False)  # 夹具的工作区落在同一个 home 下
    status, _, body = call(base, "/workspaces")
    rows = json.loads(body)
    assert status == 200 and [r["id"] for r in rows] == ["toy"]
    assert rows[0]["requirement"]["confirmed"] is False

    status, _, body = call(base, "/workspaces/toy/requirement")
    doc = json.loads(body)
    assert status == 200 and doc["text"] == REQUIREMENT
    assert [s["heading"] for s in doc["sections"]] == ["问题", "怎么算好"]

    assert call(base, "/workspaces/toy/requirement/confirm", {})[0] == 400  # 不署名不确认
    status, _, body = call(base, "/workspaces/toy/requirement/confirm", {"by": "张三"})
    doc = json.loads(body)
    assert status == 201 and doc["confirmed"] and doc["version"] == 1 and doc["by"] == "张三"
    assert doc["dirty"] is False and requirement.lock_path(ws.root).is_file()
    # 改了：dirty，页面拿 confirmed_text 做 diff；再确认成 v2
    ws.requirement.write_text(REQUIREMENT + "\n## 预算\n\n一天。\n", encoding="utf-8")
    doc = json.loads(call(base, "/workspaces/toy/requirement")[2])
    assert doc["dirty"] and doc["confirmed_text"] == REQUIREMENT
    status, _, body = call(base, "/workspaces/toy/requirement/confirm", {"by": "张三"})
    assert status == 201 and json.loads(body)["version"] == 2
    # 内容没变再确认：422 一句话
    status, _, body = call(base, "/workspaces/toy/requirement/confirm", {"by": "张三"})
    assert status == 422 and "内容没变" in json.loads(body)["error"]
    # 盘上的东西不合约：回 422 一句话，不是断连接让页面「Failed to fetch」
    (ws.flows / "boom.yaml").write_text("name: boom\n", encoding="utf-8")
    doc = json.loads(call(base, "/workspaces/toy")[2])
    assert doc["flows"][0]["problems"] == ["boom.yaml: 缺 title"]
    requirement.lock_path(ws.root).write_text("{}", encoding="utf-8")
    status, _, body = call(base, "/workspaces/toy")
    assert status == 422 and "不是一份确认记录" in json.loads(body)["error"]


def test_output_board_and_sign(served, tmp_path):
    from tests.fixtures.runs_factory import good_analysis, make_run, write_analysis

    base, _ = served
    run_dir, pack = make_run(tmp_path)
    doc_dir = write_analysis(pack, good_analysis(run_dir))
    (pack.workspace.flows / "research.yaml").write_text(
        (paths.workflows_root() / "research.yaml").read_text(encoding="utf-8"), encoding="utf-8")
    status, _, body = call(base, "/workspaces/toy")
    doc = json.loads(body)
    assert status == 200
    experiment = next(s for s in doc["stages"] if s["slug"] == "experiment")
    assert [o["id"] for o in experiment["outputs"]] == ["experiment/1"]
    assert experiment["outputs"][0]["from"] == ["design/1"]
    assert experiment["outputs"][0]["signed"] is None
    [flow] = doc["flows"]
    assert flow["name"] == "research" and flow["waiting"] == "assistant"  # 产出没记流程，流程还没动
    status, _, body = call(base, "/workspaces/toy/outputs/analysis/1")
    doc = json.loads(body)
    assert status == 200 and doc["id"] == f"analysis/{doc_dir.name}"
    assert [f["path"] for f in doc["files"]] == ["analysis.md"]
    assert call(base, "/workspaces/toy/outputs/analysis/9")[0] == 404
    assert call(base, "/workspaces/toy/outputs/runs/1")[0] == 404

    assert call(base, "/workspaces/toy/outputs/analysis/1/sign", {"by": ""})[0] == 400
    status, _, body = call(base, "/workspaces/toy/outputs/analysis/1/sign",
                           {"by": "李四", "note": "看过了"})
    doc = json.loads(body)
    assert status == 201 and doc["signed"]["by"] == "李四" and doc["signed"]["stale"] is False
    status, _, body = call(base, "/workspaces/toy/outputs/analysis/1/sign", {"by": "李四"})
    assert status == 422 and "已经签过了" in json.loads(body)["error"]
    (doc_dir / "analysis.md").write_text("改了", encoding="utf-8")
    doc = json.loads(call(base, "/workspaces/toy/outputs/analysis/1")[2])
    assert doc["signed"]["stale"] is True


def test_file_view_endpoints(served, tmp_path):
    from tests.fixtures.runs_factory import make_run

    base, _ = served
    make_run(tmp_path)
    status, _, body = call(base, "/workspaces/toy/files")
    doc = json.loads(body)
    assert status == 200 and doc["path"] == ""
    assert "experiment" in [e["name"] for e in doc["entries"]]
    status, _, body = call(base, "/workspaces/toy/files?path=experiment%2F1")
    assert status == 200 and "ledger.tsv" in [e["name"] for e in json.loads(body)["entries"]]
    status, _, body = call(base, "/workspaces/toy/file?path=experiment%2F1%2Fledger.tsv")
    doc = json.loads(body)
    assert status == 200 and doc["text"] is not None and doc["truncated"] is False
    status, ctype, body = call(base, "/workspaces/toy/raw?path=requirement.md")
    assert status == 200 and ctype.startswith("text/markdown") and body.startswith("#")
    assert call(base, "/workspaces/toy/files?path=nope")[0] == 404
    assert call(base, "/workspaces/toy/file?path=nope.txt")[0] == 404
    status, _, body = call(base, "/workspaces/toy/file?path=..%2F..%2Fetc%2Fpasswd")
    assert status == 422 and "要在工作区里" in json.loads(body)["error"]
    assert call(base, "/workspaces/toy/raw?path=%2Fetc%2Fpasswd")[0] == 422


def test_jobs_endpoints(served, tmp_path):
    """作业清单与单个作业（外层 #63）：工作区看板带全部作业。"""
    import os

    from framework.workspace import jobs
    from tests.fixtures.runs_factory import make_run

    base, _ = served
    make_run(tmp_path)
    assert json.loads(call(base, "/workspaces/toy/jobs")[2]) == []
    assert call(base, "/workspaces/toy/jobs/nope")[0] == 404
    job = jobs.Job(job_id="job-1", cap="auto-research", stage="experiment",
                   argv=["cap", "auto-research", "--continue", "experiment/1"], pid=os.getpid(),
                   started_at="t", output="experiment/1")
    jobs._save(tmp_path / "workspaces" / "toy" / ".ai4sci" / "jobs", job)
    status, _, body = call(base, "/workspaces/toy/jobs/job-1")
    assert status == 200 and json.loads(body)["effective_status"] == "running"
    doc = json.loads(call(base, "/workspaces/toy")[2])
    assert [j["job_id"] for j in doc["jobs"]] == ["job-1"] and doc["running"] == 1
    doc = json.loads(call(base, "/workspaces/toy/outputs/experiment/1")[2])
    assert [j["job_id"] for j in doc["jobs"]] == ["job-1"]


def test_check_workflow_endpoint(served):
    """编辑台边拼边问：同一个 body 只查不存。"""
    base, _ = served
    assert call(base, "/workflows/check")[0] == 404  # GET 下没有它，只有 POST
    doc = {"name": "w", "title": "t", "summary": "s", "stages": ["假设", {"设计": ["design"]}]}
    status, _, body = call(base, "/workflows/check", doc)
    assert status == 200 and json.loads(body) == {"covers": ["设计"], "remarks": [], "problems": []}
    status, _, body = call(base, "/workflows/check", {**doc, "stages": [{"设计": ["nope"]}]})
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
                        workflows=lambda: WORKFLOWS, check_workflow=check_workflow,
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
    """编辑台存流程（外层 #68）：存成 201 回清单里的样子；形状 / 不通 422；同名 409。"""
    base, _ = served
    doc = {"name": "w", "title": "t", "summary": "s", "stages": [{"设计": ["design"]}]}
    status, _, body = call(base, "/workflows", doc)
    assert status == 201 and json.loads(body)["covers"] == ["实验"]
    assert call(base, "/workflows", {**doc, "stages": []})[0] == 422
    assert call(base, "/workflows", {**doc, "name": "taken"})[0] == 409


def test_stop_job_endpoint_kills_and_records(served, tmp_path):
    """外层 #115：页面上的「停止」与 `ai4sci job stop` 同一个函数；不在跑的 422、没有的 404。"""
    import subprocess
    import sys
    import time

    from framework.workspace import jobs, outputs
    from framework.workspace import root as workspace

    base, _ = served
    ws = workspace.create(tmp_path / "workspaces", "w1", template="# w1\n\n## 问题\n\n有。\n")
    directory, _ = outputs.open_output(ws, "design", title="t", by="design", inputs=[], params={},
                                       flow=None, step=None, requirement=1, chat_id=None)
    proc = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(300)"],
                            start_new_session=True)
    time.sleep(0.3)
    ws.jobs.mkdir(parents=True)
    record = jobs.Job(job_id="job-s", cap="design", stage="design", argv=[], pid=proc.pid,
                      started_at="t", output="design/1")
    (ws.jobs / "job-s.json").write_text(json.dumps(record.__dict__), encoding="utf-8")
    assert call(base, "/workspaces/w1/jobs/job-s/stop", {"by": ""})[0] == 400
    status, _, body = call(base, "/workspaces/w1/jobs/job-s/stop", {"by": "李四"})
    doc = json.loads(body)
    assert status == 201 and doc["status"] == "stopped" and "李四" in doc["result"]
    proc.wait(timeout=5)
    assert call(base, "/workspaces/w1/jobs/job-s/stop", {"by": "李四"})[0] == 422
    assert call(base, "/workspaces/w1/jobs/nope/stop", {"by": "李四"})[0] == 404
    status, _, body = call(base, "/workspaces/w1/outputs/design/1")
    assert json.loads(body)["status"] == "failed"
