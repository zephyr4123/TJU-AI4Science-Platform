"""HTTP 后端：端点形状、按域分前缀、SSE 事件流、忙与错误的状态码。真 server 起在随机端口。"""

from __future__ import annotations

import getpass
import json
import os
import sys
import threading
import urllib.error
import urllib.request

import pytest

from backends import AgentProbe, BackendNotFound, available_backends
from framework import agents, keys, paths
from framework.capabilities import stage_table
from framework.chat.server import ChatServer
from framework.cli import serve as serve_cli
from framework.workspace import project as project_mod
from tests.fixtures import spaces
from tests.fixtures.scripted_chat import KNOBS, ScriptedChat, reply, with_tool

CATALOG = [{"name": "design", "stage": "设计"}, {"name": "auto-research", "stage": "实验"}]
WORKFLOWS = [{"name": "w", "title": "一条", "summary": "…",
              "stages": [{"kind": "stage", "stage": "设计",
                          "caps": [{"cap": "design", "with": {}}]}],
              "covers": ["设计"], "remarks": [], "problems": []}]
PROMPTS = {"project": "研究助理指南", "studio": "流程助理指南"}


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

    chat.providers_asked = []  # 每次起适配器按的哪个供应商（老对话照它开时记的，外层 #266）

    def factory(name: str, provider: str | None = None):
        # 顶着真适配器的名字（P-25 按人的设置按名字查每家的清单），两家都是同一份剧本
        if name not in available_backends():
            raise BackendNotFound(f"未知的 agent 后端 {name!r}")
        chat.providers_asked.append(provider)
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
                              installed=True, version="codex-cli 0.160.0")
        return AgentProbe(items=[("装了没", True, "/x"), ("说话", True, "pong")],
                          installed=True, version="2.1.278", logged_in=True, spoke_s=0.8)

    def add_compute(body: dict) -> dict:
        added.append(body)
        return {"agents": {}, "computes": [{"name": body["name"]}], "storage": {}}

    added: list[dict] = []
    spaces.make_project(tmp_path, "p")
    server = ChatServer(("127.0.0.1", 0), home=tmp_path, catalog=lambda: CATALOG,
                        workflows=lambda: WORKFLOWS, check_workflow=check_workflow,
                        save_workflow=save_workflow, descriptors=descriptors,
                        stage_table=stage_table, chat_factory=factory, probe_agent=probe_agent,
                        add_compute=add_compute, system_prompts=PROMPTS, ui_dir=ui_dir(tmp_path),
                        logout_agent=lambda name: ([sys.executable, "-c", ""], dict(os.environ)))
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
    """项目 p 里起一个工作区（served 夹具已经建了项目 p）。"""
    status, _, body = call(base, "/projects/p/workspaces", {"id": ws_id, "title": title})
    assert status == 201, body
    return json.loads(body)


def listed_workspaces(base, project_id="p"):
    return json.loads(call(base, f"/projects/{project_id}")[2])["workspaces"]


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
    spaces.make_project(tmp_path, "p")
    server = ChatServer(("127.0.0.1", 0), home=tmp_path, catalog=serve_cli._catalog,
                        skills=serve_cli._skills, skill=serve_cli._skill,
                        skill_names=serve_cli._skill_names,
                        workflows=serve_cli._workflows, check_workflow=serve_cli._check_workflow,
                        descriptors=serve_cli._descriptor_map, stage_table=stage_table,
                        system_prompts=PROMPTS)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_address[1]}"
    try:
        new_workspace(base, "w1", "一个课题")
        for path in ("/stages", "/cap", "/workflows", "/templates", "/projects", "/projects/p",
                     "/projects/p/workspaces/w1"):
            status, _, body = call(base, path)
            assert status == 200, (path, body)
            assert _unnamed(json.loads(body), path) == [], path
        caps = json.loads(call(base, "/cap")[2])
        assert {c["name"]: c["title"] for c in caps}["auto-research"] == "AutoResearch"
        assert all(c["brief"] and all(p["label"] for p in c["params"]) for c in caps)
        # 能力库的两半各带 tag：/cap 是步骤，/skills 是 skill（名字、一行、正文、脚本、used_by）
        assert {c["kind"] for c in caps} == {"步骤"}
        status, _, body = call(base, "/skills")
        skills = {s["name"]: s for s in json.loads(body)}
        assert status == 200 and {"pdf", "download"} <= set(skills)
        assert skills["pdf"]["kind"] == "skill" and skills["pdf"]["title"] == "pdf"
        assert skills["pdf"]["brief"] and skills["pdf"]["scripts"]
        # 位置是能力镜头里的一行一组（外层 #205）；出处不给页面
        assert (skills["pdf"]["stage"], skills["pdf"]["tag"]) == ("通用", "资料")
        assert skills["scanpy"]["stage"] == "实验" and skills["scanpy"]["tag"] == "生物"
        assert all("where" not in s and "library" not in s for s in skills.values())
        assert skills["pdf"]["used_by"] == ["reproduce"]
        assert all("body" not in s for s in skills.values())  # 几百个，正文按名字单取
        status, _, body = call(base, "/skills/pdf")
        one = json.loads(body)
        assert status == 200 and one["body"].startswith("#") and one["used_by"] == ["reproduce"]
        assert call(base, "/skills/no-such-skill")[0] == 404
        flows = {w["name"]: w for w in json.loads(call(base, "/workflows")[2])}
        assert flows["reproduce"]["stages"][0]["caps"] == [
            {"cap": "pdf", "with": {}, "kind": "skill"},
            {"cap": "download", "with": {}, "kind": "skill"}]
        assert flows["reproduce"]["stages"][1]["caps"][0]["kind"] == "步骤"
        # 工作区里取来的实例：进度里的格子同样带 kind（看板按它分两行画）
        instance = tmp_path / "projects" / "p" / "workspaces" / "w1" / "flows" / "reproduce.yaml"
        instance.parent.mkdir(parents=True, exist_ok=True)
        instance.write_text((paths.workflows_root() / "reproduce.yaml").read_text(encoding="utf-8"),
                            encoding="utf-8")
        [taken] = json.loads(call(base, "/projects/p/workspaces/w1/flows")[2])
        assert taken["problems"] == []
        assert [c["kind"] for c in taken["items"][0]["caps"]] == ["skill", "skill"]
        assert taken["items"][1]["caps"][0]["kind"] == "步骤"

    finally:
        server.shutdown()
        server.server_close()


def test_workspaces_are_created_listed_and_read(served, tmp_path):
    """工作区（纲领 P-15）：起、列、读一整份；名字规矩与重名的状态码；URL 片段拼不出路径。"""
    base, _ = served
    assert listed_workspaces(base) == []
    made = new_workspace(base, "rahman-nll", "Rahman 稳定性")
    assert made["id"] == "rahman-nll" and made["title"] == "Rahman 稳定性"
    assert made["requirement"]["confirmed"] is False and made["running"] == 0
    requirement = tmp_path / "projects" / "p" / "workspaces" / "rahman-nll" / "requirement.md"
    assert requirement.read_text(encoding="utf-8").startswith("# Rahman 稳定性\n")
    assert "## 问题" in requirement.read_text(encoding="utf-8")  # 按 generic 模板起草
    assert call(base, "/projects/p/workspaces", {"id": "rahman-nll"})[0] == 409
    assert call(base, "/projects/p/workspaces", {"id": "Bad Name"})[0] == 400
    assert call(base, "/projects/p/workspaces", {"id": "x2", "template": "nope"})[0] == 400
    assert call(base, "/projects/p/workspaces", {})[0] == 400
    status, _, body = call(base, "/projects/p/workspaces/rahman-nll")
    doc = json.loads(body)
    assert status == 200 and doc["flows"] == [] and doc["jobs"] == []
    assert all(s["outputs"] == [] for s in doc["stages"])
    assert doc["requirement"]["title"] == "Rahman 稳定性" and doc["requirement"]["pending"]
    assert [w["id"] for w in listed_workspaces(base)] == ["rahman-nll"]
    assert call(base, "/projects/p/workspaces/nope")[0] == 404
    assert call(base, "/projects/p/workspaces/../etc")[0] == 404
    assert call(base, "/projects/p/workspaces/rahman-nll/nothing")[0] == 404
    assert call(base, "/projects/nope")[0] == 404 and call(base, "/projects/nope/chats")[0] == 404


@pytest.mark.parametrize("prefix", ["/projects/p", "/studio"])
def test_chat_lifecycle_in_both_scopes(served, tmp_path, prefix):
    """对话四个端点在两个域下共用一套：项目的对话落在项目里，编辑台的落在 studio/ 里；
    两位助理各拿各的指南、各写各的目录（P-16）。"""
    base, chat = served
    new_workspace(base, "w1")
    status, _, body = call(base, f"{prefix}/chats", {})
    assert status == 201
    meta = json.loads(body)
    chat_id = meta["chat_id"]
    assert meta["backend"] == "claude_code" and meta["turns"] == 0
    where = tmp_path / ("studio" if prefix == "/studio" else "projects/p/.ai4sci")
    assert (where / "chats" / chat_id / "meta.json").is_file()

    status, ctype, body = call(base, f"{prefix}/chats/{chat_id}/messages", {"text": "你好"})
    assert status == 200 and ctype.startswith("text/event-stream")
    events = sse_events(body)
    assert [e["event"] for e in events] == ["init", "text", "done"]
    assert events[-1]["cost_usd"] == pytest.approx(0.01) and events[-1]["session_id"]
    call_ = chat.calls[-1]
    if prefix == "/studio":
        # 流程助理站在服务的平台的家里的 studio/ 里，只写人存的那层库；出厂的只读（外层 #149）
        assert call_["system_prompt"] == "流程助理指南"
        assert call_["cwd"] == tmp_path / "studio"
        assert call_["allowed_paths"] == [tmp_path / "studio" / "workflows"]
        assert call_["readable_paths"] == [paths.workflows_root()]
    else:
        made = spaces.make_project(tmp_path, "p")
        assert call_["system_prompt"] == "研究助理指南" and call_["cwd"] == made.root
        assert call_["allowed_paths"] == [made.root]
        assert call_["readable_paths"] == [paths.workflows_root(), paths.user_workflows_root(),
                                           paths.templates_root()]

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
    other = "/studio" if prefix != "/studio" else "/projects/p"
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


def test_chats_take_backend_and_tuning_from_settings_only(served):
    """外层 #257：哪家、模型、思考深度只在设置里改。开对话照设置抄具体值进 meta（P-25），之后改设置
    不动已开的；开对话与发消息的 body 带这三样一律 400——没有调用方了，带了就是旧页面，
    不悄悄忽略。"""
    from backends import Tuning

    base, chat = served
    chat.turns.append(reply("三"))
    assert call(base, "/settings/agents", {"agents": {"claude_code": {"model": "b"}}})[0] == 200
    status, _, body = call(base, "/studio/chats", {})
    meta = json.loads(body)
    assert status == 201
    assert (meta["backend"], meta["model"], meta["effort"]) == ("claude_code", "b", "low")
    for key, value in (("backend", "codex"), ("model", "a"), ("effort", "high"), ("model", None)):
        status, _, body = call(base, "/studio/chats", {key: value})
        assert status == 400 and "在设置里改" in json.loads(body)["error"], (key, value)
        status, _, body = call(base, f"/studio/chats/{meta['chat_id']}/messages",
                               {"text": "你好", key: value})
        assert status == 400 and "在设置里改" in json.loads(body)["error"], (key, value)
    # 改设置只影响之后开的对话：已开的这段照它 meta 里记的
    assert call(base, "/settings/agents", {"agents": {"claude_code": {"model": "a"}}})[0] == 200
    status, _, body = call(base, f"/studio/chats/{meta['chat_id']}/messages", {"text": "你好"})
    assert status == 200 and sse_events(body)[-1]["event"] == "done"
    assert chat.calls[-1]["tuning"] == Tuning(model="b", effort="low")
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
    # 登录命令照服务自己这份安装给，页面照抄（外层 #274）
    assert codex["login"] == f"{paths.cli()} agent login codex"
    assert codex["models"][0]["id"] == "a"  # 清单跟着服务接的那家适配器（剧本）走
    assert [c["name"] for c in snap["computes"]] == ["local"]
    # 每个供应商能不能联网照官方文档登记，页面标「不能联网」只提醒不拦；自定义不知道（外层 #266）
    rows = {p["id"]: p["web_search"] for p in codex["providers"]}
    assert rows["official"] is True and rows["deepseek"] is False and rows["custom"] is None
    assert snap["storage"]["home"] == str(tmp_path) and snap["storage"]["writable"] is True
    # 家里每块多大要走遍整棵树，不在这一份里，存放页打开时单独取（外层 #268）
    assert "parts" not in snap["storage"]
    (tmp_path / "projects" / "sizes.bin").write_bytes(b"x" * 1000)
    status, _, body = call(base, "/settings/storage")
    assert status == 200
    parts = {p["label"]: p["bytes"] for p in json.loads(body)["parts"]}
    assert parts["项目"] >= 1000 and list(parts)[-1] == "设置与 key"
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
    assert call(base, "/projects/p/chats/nope")[0] == 404
    assert call(base, "/projects/p/chats/nope/messages", {"text": "x"})[0] == 404
    assert call(base, "/projects/nope/chats", {})[0] == 404
    assert call(base, "/projects/p/workspaces/w1/chats", {})[0] == 404  # 对话归项目，不归工作区
    chat_id = json.loads(call(base, "/projects/p/chats", {})[2])["chat_id"]
    assert call(base, f"/projects/p/chats/{chat_id}/messages", {"text": "  "})[0] == 400
    assert call(base, f"/projects/p/chats/{chat_id}/messages", {})[0] == 400
    (tmp_path / "projects" / "p" / ".ai4sci" / "chats" / chat_id / "inflight.json").write_text(
        "{}", encoding="utf-8")
    status, _, body = call(base, f"/projects/p/chats/{chat_id}/messages", {"text": "插队"})
    assert status == 409 and "在跑" in json.loads(body)["error"]
    assert call(base, "/studio/requirement")[0] == 404  # 编辑台下只有对话
    assert call(base, "/studio/requirement/confirm", {})[0] == 404


def test_bad_json_body_is_400(served):
    base, _ = served
    req = urllib.request.Request(base + "/projects", data=b"{not json", method="POST",
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
    status, _, body = call(base, "/projects/p")
    rows = json.loads(body)["workspaces"]
    assert status == 200 and [r["id"] for r in rows] == ["toy"]
    assert rows[0]["requirement"]["confirmed"] is False

    status, _, body = call(base, "/projects/p/workspaces/toy/requirement")
    doc = json.loads(body)
    assert status == 200 and doc["text"] == REQUIREMENT
    assert [s["heading"] for s in doc["sections"]] == ["问题", "怎么算好"]

    # 不用署名：本地部署，按的就是跑服务的这个人，记登录名（与 CLI 的缺省一样）
    status, _, body = call(base, "/projects/p/workspaces/toy/requirement/confirm", {})
    doc = json.loads(body)
    assert status == 201 and doc["confirmed"] and doc["version"] == 1
    assert doc["by"] == getpass.getuser()
    assert doc["dirty"] is False and requirement.lock_path(ws.root).is_file()
    # 改了：dirty，页面拿 confirmed_text 做 diff；再确认成 v2
    ws.requirement.write_text(REQUIREMENT + "\n## 预算\n\n一天。\n", encoding="utf-8")
    doc = json.loads(call(base, "/projects/p/workspaces/toy/requirement")[2])
    assert doc["dirty"] and doc["confirmed_text"] == REQUIREMENT
    status, _, body = call(base, "/projects/p/workspaces/toy/requirement/confirm", {})
    assert status == 201 and json.loads(body)["version"] == 2
    # 内容没变再确认：422 一句话
    status, _, body = call(base, "/projects/p/workspaces/toy/requirement/confirm", {})
    assert status == 422 and "内容没变" in json.loads(body)["error"]
    # 盘上的东西不合约：回 422 一句话，不是断连接让页面「Failed to fetch」
    (ws.flows / "boom.yaml").write_text("name: boom\n", encoding="utf-8")
    doc = json.loads(call(base, "/projects/p/workspaces/toy")[2])
    assert doc["flows"][0]["problems"] == ["boom.yaml: 缺 title"]
    requirement.lock_path(ws.root).write_text("{}", encoding="utf-8")
    status, _, body = call(base, "/projects/p/workspaces/toy")
    assert status == 422 and "不是一份确认记录" in json.loads(body)["error"]


def test_output_board_and_sign(served, tmp_path):
    from tests.fixtures.runs_factory import good_analysis, make_run, write_analysis

    base, _ = served
    run_dir, pack = make_run(tmp_path)
    doc_dir = write_analysis(pack, good_analysis(run_dir))
    (pack.workspace.flows / "open.yaml").unlink()  # 夹具那条敞开的流程不是这里要看的
    (pack.workspace.flows / "research.yaml").write_text(
        (paths.workflows_root() / "research.yaml").read_text(encoding="utf-8"), encoding="utf-8")
    status, _, body = call(base, "/projects/p/workspaces/toy")
    doc = json.loads(body)
    assert status == 200
    experiment = next(s for s in doc["stages"] if s["slug"] == "experiment")
    assert [o["id"] for o in experiment["outputs"]] == ["experiment/1"]
    assert experiment["outputs"][0]["from"] == ["design/1"]
    assert experiment["outputs"][0]["signed"] is None
    [flow] = doc["flows"]
    assert flow["name"] == "research" and flow["waiting"] == "assistant"  # 产出没记流程，流程还没动
    status, _, body = call(base, "/projects/p/workspaces/toy/outputs/analysis/1")
    doc = json.loads(body)
    assert status == 200 and doc["id"] == f"analysis/{doc_dir.name}"
    assert [f["path"] for f in doc["files"]] == ["analysis.md"]
    assert call(base, "/projects/p/workspaces/toy/outputs/analysis/9")[0] == 404
    assert call(base, "/projects/p/workspaces/toy/outputs/runs/1")[0] == 404

    status, _, body = call(base, "/projects/p/workspaces/toy/outputs/analysis/1/sign", {})
    doc = json.loads(body)
    assert status == 201 and doc["signed"]["stale"] is False
    assert doc["signed"]["by"] == getpass.getuser()
    status, _, body = call(base, "/projects/p/workspaces/toy/outputs/analysis/1/sign", {})
    assert status == 422 and "已经签过了" in json.loads(body)["error"]
    (doc_dir / "analysis.md").write_text("改了", encoding="utf-8")
    doc = json.loads(call(base, "/projects/p/workspaces/toy/outputs/analysis/1")[2])
    assert doc["signed"]["stale"] is True


def test_file_view_endpoints(served, tmp_path):
    from tests.fixtures.runs_factory import make_run

    base, _ = served
    make_run(tmp_path)
    status, _, body = call(base, "/projects/p/workspaces/toy/files")
    doc = json.loads(body)
    assert status == 200 and doc["path"] == ""
    assert "experiment" in [e["name"] for e in doc["entries"]]
    status, _, body = call(base, "/projects/p/workspaces/toy/files?path=experiment%2F1")
    assert status == 200 and "ledger.tsv" in [e["name"] for e in json.loads(body)["entries"]]
    status, _, body = call(base, "/projects/p/workspaces/toy/file?path=experiment%2F1%2Fledger.tsv")
    doc = json.loads(body)
    assert status == 200 and doc["text"] is not None and doc["truncated"] is False
    status, ctype, body = call(base, "/projects/p/workspaces/toy/raw?path=requirement.md")
    assert status == 200 and ctype.startswith("text/markdown") and body.startswith("#")
    assert call(base, "/projects/p/workspaces/toy/files?path=nope")[0] == 404
    assert call(base, "/projects/p/workspaces/toy/file?path=nope.txt")[0] == 404
    status, _, body = call(base, "/projects/p/workspaces/toy/file?path=..%2F..%2Fetc%2Fpasswd")
    assert status == 422 and "要在工作区里" in json.loads(body)["error"]
    assert call(base, "/projects/p/workspaces/toy/raw?path=%2Fetc%2Fpasswd")[0] == 422


def test_jobs_endpoints(served, tmp_path):
    """作业清单与单个作业（外层 #63）：工作区看板带全部作业。"""
    import os

    from framework.workspace import jobs
    from tests.fixtures.runs_factory import make_run

    base, _ = served
    make_run(tmp_path)
    assert json.loads(call(base, "/projects/p/workspaces/toy/jobs")[2]) == []
    assert call(base, "/projects/p/workspaces/toy/jobs/nope")[0] == 404
    job = jobs.Job(job_id="job-1", cap="auto-research", stage="experiment",
                   argv=["cap", "auto-research", "--continue", "experiment/1"], pid=os.getpid(),
                   started_at="t", output="experiment/1")
    jobs._save(tmp_path / "projects" / "p" / "workspaces" / "toy" / ".ai4sci" / "jobs", job)
    status, _, body = call(base, "/projects/p/workspaces/toy/jobs/job-1")
    assert status == 200 and json.loads(body)["effective_status"] == "running"
    doc = json.loads(call(base, "/projects/p/workspaces/toy")[2])
    assert [j["job_id"] for j in doc["jobs"]] == ["job-1"] and doc["running"] == 1
    doc = json.loads(call(base, "/projects/p/workspaces/toy/outputs/experiment/1")[2])
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

    import procs
    from framework.workspace import jobs, outputs

    base, _ = served
    ws = spaces.make_workspace(tmp_path, "w1", template="# w1\n\n## 问题\n\n有。\n")
    directory, _ = outputs.open_output(ws, "design", title="t", by="design", inputs=[], params={},
                                       flow=None, step=None, requirement=1, chat_id=None)
    proc = procs.spawn([sys.executable, "-c", "import time; time.sleep(300)"], detach=True,
                       stdin=subprocess.DEVNULL)
    time.sleep(0.3)
    ws.jobs.mkdir(parents=True)
    record = jobs.Job(job_id="job-s", cap="design", stage="design", argv=[], pid=proc.pid,
                      started_at="t", output="design/1")
    (ws.jobs / "job-s.json").write_text(json.dumps(record.__dict__), encoding="utf-8")
    status, _, body = call(base, "/projects/p/workspaces/w1/jobs/job-s/stop", {})
    doc = json.loads(body)
    assert status == 201 and doc["status"] == "stopped" and getpass.getuser() in doc["result"]
    proc.wait(timeout=5)
    assert call(base, "/projects/p/workspaces/w1/jobs/job-s/stop", {})[0] == 422
    assert call(base, "/projects/p/workspaces/w1/jobs/nope/stop", {})[0] == 404
    status, _, body = call(base, "/projects/p/workspaces/w1/outputs/design/1")
    assert json.loads(body)["status"] == "failed"


def test_remove_endpoints_cascade_and_refuse(served, tmp_path):
    """删（主人 2026-09-22）：对话、产出、流程实例、工作区各一条 `POST …/remove`，库里的流程
    `POST /workflows/<name>/remove`。拒 409、没有 404、出厂的 403；目录外没清的随 leftovers
    回去。"""
    from framework.workspace import outputs as ws_outputs
    from framework.workspace import root as ws_root

    base, chat = served
    new_workspace(base, "w1")
    ws = ws_root.load(tmp_path / "projects" / "p" / "workspaces" / "w1")
    # 对话：发过一句才有 session；删了目录没了、剧本后端被叫去忘掉那条会话
    chat_id = json.loads(call(base, "/projects/p/chats", {})[2])["chat_id"]
    call(base, f"/projects/p/chats/{chat_id}/messages", {"text": "你好"})
    status, _, body = call(base, f"/projects/p/chats/{chat_id}/remove", {})
    assert status == 200 and json.loads(body) == {"removed": chat_id, "leftovers": []}
    assert chat.forgotten and not (project_mod.of(ws).chats / chat_id).exists()
    assert call(base, f"/projects/p/chats/{chat_id}/remove", {})[0] == 404
    # 产出：被引用的拒 409，叶子 200
    d1, m1 = ws_outputs.open_output(ws, "design", title="t", by="design", inputs=[], params={},
                                    flow=None, step=None, requirement=1, chat_id=None)
    ws_outputs.close_output(d1, m1, ok=True, line="ok")
    d2, m2 = ws_outputs.open_output(ws, "experiment", title="t", by="auto-research",
                                    inputs=["design/1"], params={}, flow="research", step=2,
                                    requirement=1, chat_id=None)
    ws_outputs.close_output(d2, m2, ok=True, line="ok")
    status, _, body = call(base, "/projects/p/workspaces/w1/outputs/design/1/remove", {})
    assert status == 409 and "被 experiment/1 读过" in json.loads(body)["error"]
    # 流程实例：挂着产出拒 409
    (ws.flows / "research.yaml").write_text("name: research\n", encoding="utf-8")
    status, _, body = call(base, "/projects/p/workspaces/w1/flows/research/remove", {})
    assert status == 409 and "挂着 experiment/1" in json.loads(body)["error"]
    assert call(base, "/projects/p/workspaces/w1/outputs/experiment/1/remove", {})[0] == 200
    assert call(base, "/projects/p/workspaces/w1/flows/research/remove", {})[0] == 200
    assert not d2.exists() and not (ws.flows / "research.yaml").exists()
    # 库里的流程：出厂的 403，没有的 404；人存的在服务的平台的家里的 studio/workflows/ 下，删得掉
    status, _, body = call(base, "/workflows/research/remove", {})
    assert status == 403 and "出厂" in json.loads(body)["error"]
    assert call(base, "/workflows/nope/remove", {})[0] == 404
    mine = tmp_path / "studio" / "workflows" / "mine.yaml"
    mine.parent.mkdir(parents=True, exist_ok=True)
    mine.write_text("name: mine\n", encoding="utf-8")
    assert call(base, "/workflows/mine/remove", {})[0] == 200 and not mine.exists()
    # 整个工作区：目录没了、清单里没了
    status, _, body = call(base, "/projects/p/workspaces/w1/remove", {})
    assert status == 200 and json.loads(body)["removed"] == "w1"
    assert not ws.root.exists()
    assert listed_workspaces(base) == []
    assert call(base, "/projects/p/workspaces/w1/remove", {})[0] == 404
    # 整个项目：级联；清单里没了
    new_workspace(base, "w2")
    chat_id = json.loads(call(base, "/projects/p/chats", {})[2])["chat_id"]
    call(base, f"/projects/p/chats/{chat_id}/messages", {"text": "你好"})
    status, _, body = call(base, "/projects/p/remove", {})
    assert status == 200 and json.loads(body)["removed"] == "p"
    assert json.loads(call(base, "/projects")[2]) == []
    assert not (tmp_path / "projects" / "p").exists()
    assert call(base, "/projects/p/remove", {})[0] == 404


def test_chat_doc_shows_a_turn_running_elsewhere_and_jobs_still_to_wake_it(served, tmp_path):
    """外层 #230：叫醒那一轮是作业进程起的、不经过服务。对话接口从盘上读出正在跑的那一轮
    （running），并说还有几个作业会来叫醒它（waiting）：页面据此定时重读、摆出这一轮、锁住输入框。"""
    import os

    from framework.chat import conversation as conv_mod
    from framework.workspace import jobs
    from framework.workspace import project as project_mod
    from tests.fixtures.scripted_chat import ScriptedChat, reply

    base, _ = served
    ws = spaces.make_workspace(tmp_path, "w", project_id="p")
    conv = conv_mod.new_conversation(project_mod.of(ws).chats, "claude_code", ws.root)
    doc = json.loads(call(base, f"/projects/p/chats/{conv.chat_id}")[2])
    assert doc["running"] is None and doc["waiting"] == 0
    jobs._save(ws.jobs, jobs.Job(job_id="job-1", cap="literature-search", stage="literature",
                                 argv=[], pid=os.getpid(), started_at="t", chat_id=conv.chat_id))
    stream = conv_mod.send(conv, ScriptedChat([reply("读完了")]), "作业跑完了",
                           system_prompt="g", allowed_paths=[], bash_rules=(), origin="框架")
    next(stream)
    doc = json.loads(call(base, f"/projects/p/chats/{conv.chat_id}")[2])
    assert doc["waiting"] == 1
    assert (doc["running"]["turn"], doc["running"]["origin"], doc["running"]["message"]) == (
        1, "框架", "作业跑完了")
    stream.close()


def test_home_side_panel_endpoints(served, tmp_path):
    """首页右栏（外层 #256）：/attention 跨项目列要人做的与在跑的；/usage?days= 汇总花费，
    days 缺省 30、不是正整数是 422。"""
    base, _ = served
    spaces.make_workspace(tmp_path, "draft")  # 需求没确认：在等人
    status, _, body = call(base, "/attention")
    assert status == 200
    assert [(i["kind"], i["workspace"]) for i in json.loads(body)] == [("requirement", "draft")]
    status, _, body = call(base, "/usage")
    got = json.loads(body)
    assert status == 200 and got["days"] == 30 and len(got["by_day"]) == 30
    assert got["total"] == {"cost_usd": None, "unknown": 0, "tokens": 0, "input_tokens": 0,
                            "cached_tokens": 0, "count": 0}
    assert json.loads(call(base, "/usage?days=7")[2])["days"] == 7
    assert call(base, "/usage?days=0")[0] == 422
    assert call(base, "/usage?days=x")[0] == 422


# ── 请求的来源：只认发给本机、同源的（外层 #283）────────────────────────────
def asked(base, method, path, headers, body=None):
    """照原样发一个请求：Host、Origin、Content-Type 都由用例给（urllib 会自己补 Host）。
    返回状态码、响应头与解出来的 JSON（不是 JSON 的是原文）。"""
    import http.client
    from urllib.parse import urlsplit

    where = urlsplit(base)
    conn = http.client.HTTPConnection(where.hostname, where.port, timeout=10)
    try:
        conn.putrequest(method, path, skip_host=True, skip_accept_encoding=True)
        data = None if body is None else (body if isinstance(body, bytes)
                                          else json.dumps(body).encode("utf-8"))
        for name, value in headers.items():
            conn.putheader(name, value)
        if data is not None:
            conn.putheader("Content-Length", str(len(data)))
        conn.endheaders(data)
        resp = conn.getresponse()
        raw = resp.read().decode("utf-8", errors="replace")
        try:
            doc = json.loads(raw)
        except ValueError:
            doc = raw
        return resp.status, resp.headers, doc
    finally:
        conn.close()


def test_requests_from_other_sites_are_refused(served, tmp_path):
    """任何网页都能对本机服务发「简单请求」（不预检的 POST）：存 key、清空家、让助理动手；DNS
    rebinding 之后还能同源读走对话与文件。服务只认发给 127.0.0.1 / localhost 的、带 Origin 就得与
    Host 同源、POST 只收 JSON。被拒的一件事都没做成。"""
    base, _ = served
    here = base.removeprefix("http://")
    json_type = {"Content-Type": "application/json"}
    new_project = {"id": "evil", "title": "x"}
    # 别的网站：Origin 不是自己
    status, _, doc = asked(base, "POST", "/projects",
                           {"Host": here, "Origin": "http://evil.example", **json_type},
                           new_project)
    assert status == 403 and "Origin" in doc["error"]
    # 本机别的端口上的页面也不是同源
    status, _, _ = asked(base, "POST", "/projects",
                         {"Host": here, "Origin": "http://localhost:8888", **json_type},
                         new_project)
    assert status == 403
    # DNS rebinding：浏览器以为同源，Host 是攻击者的域名；读也不行，页面本身也不给
    for path in ("/settings", "/projects/p", "/"):
        status, _, doc = asked(base, "GET", path, {"Host": "evil.example" + here[here.index(":"):]})
        assert status == 403 and "Host" in doc["error"], path
    assert asked(base, "GET", "/health", {})[0] == 403  # 不带 Host
    # 沙箱里的 iframe、file:// 打开的页面发的是 Origin: null
    status, _, doc = asked(base, "POST", "/projects",
                           {"Host": here, "Origin": "null", **json_type}, new_project)
    assert status == 403 and "null" in doc["error"]
    # 表单与 text/plain 的 fetch 不用预检：不是 JSON 一律不收，没有 body 的也一样
    status, _, doc = asked(base, "POST", "/projects", {"Host": here, "Content-Type": "text/plain"},
                           new_project)
    assert status == 415 and "-H 'Content-Type: application/json'" in doc["error"]
    status, _, _ = asked(base, "POST", "/settings/reset",
                         {"Host": here, "Content-Type": "application/x-www-form-urlencoded"},
                         b"confirm=x")
    assert status == 415
    assert asked(base, "POST", "/projects/p/chats", {"Host": here})[0] == 415
    assert not (tmp_path / "projects" / "evil").exists(), "被拒的请求建出了项目"
    assert json.loads(call(base, "/projects/p/chats")[2]) == []


def test_the_page_curl_the_dev_proxy_and_an_ssh_tunnel_still_get_through(served, tmp_path):
    """被拒的只该是别人的网页。同源的页面、curl（不带 Origin）、Vite 开发代理（changeOrigin:
    false，Host 与 Origin 都是 localhost:5173）、SSH 隧道（127.0.0.1:18765 转到服务的端口）都
    照常。"""
    base, _ = served
    here = base.removeprefix("http://")
    json_type = {"Content-Type": "application/json; charset=utf-8"}
    shapes = {"页面": {"Host": here, "Origin": base},
              "curl": {"Host": here},
              "Vite 代理": {"Host": "localhost:5173", "Origin": "http://localhost:5173"},
              "SSH 隧道": {"Host": "127.0.0.1:18765", "Origin": "http://127.0.0.1:18765"}}
    for n, (label, headers) in enumerate(shapes.items()):
        status, _, doc = asked(base, "POST", "/projects", {**headers, **json_type},
                               {"id": f"p{n}", "title": label})
        assert status == 201, (label, doc)
        assert asked(base, "GET", "/settings", headers)[0] == 200, label
        assert asked(base, "GET", "/", headers)[0] == 200, label
    assert asked(base, "GET", "/health", {"Host": "LOCALHOST:8765"})[0] == 200


def test_the_gate_takes_the_host_the_server_was_told_to_listen_on():
    """人显式让服务听在非回环的地址上（`--host 192.168.1.5`）：发给那个地址的也认；别的照样拒。"""
    from framework.chat.server import refusal

    hosts = frozenset({"127.0.0.1", "localhost", "192.168.1.5"})
    assert refusal("GET", {"Host": "192.168.1.5:8765"}, hosts) is None
    assert refusal("POST", {"Host": "192.168.1.5:8765", "Origin": "http://192.168.1.5:8765",
                            "Content-Type": "application/json"}, hosts) is None
    assert refusal("GET", {"Host": "192.168.1.6:8765"}, hosts) is not None
    # 认不出的 Host 一律拒：带用户名的、带路径的、不是端口的
    for odd in ("localhost:80@evil.example", "localhost/x", "localhost:abc", "localhost:"):
        assert refusal("GET", {"Host": odd}, hosts) is not None, odd


def test_no_page_can_be_framed_and_raw_files_run_sandboxed(served, tmp_path):
    """别的网站把页面嵌进 iframe 诱导点击（清除那颗按住生效的键）：每个响应都禁止被嵌。`/raw`
    原样端出 agent 写的 HTML / SVG：不许按内容猜类型、当沙箱里的文档跑，拿不到页面的来源。HEAD 与
    OPTIONS 照旧 501，不发任何 CORS 头。"""
    from tests.fixtures.runs_factory import make_run

    base, _ = served
    make_run(tmp_path)
    here = {"Host": base.removeprefix("http://")}
    responses = [asked(base, "GET", path, here) for path in
                 ("/health", "/", "/assets/app-abc123.js", "/studio/x/y/z")]
    responses.append(asked(base, "GET", "/health", {"Host": "evil.example"}))
    responses += [asked(base, method, "/health", here) for method in ("HEAD", "OPTIONS")]
    for status, headers, _ in responses:
        assert headers["X-Frame-Options"] == "DENY", status
        assert "frame-ancestors 'none'" in headers["Content-Security-Policy"], status
    assert [r[0] for r in responses[-2:]] == [501, 501]
    for _, headers, _ in responses[-2:]:
        assert not [h for h in headers if h.lower().startswith("access-control-")]
    status, headers, _ = asked(base, "GET", "/projects/p/workspaces/toy/raw?path=requirement.md",
                               here)
    assert status == 200 and headers["X-Content-Type-Options"] == "nosniff"
    policy = headers["Content-Security-Policy"]
    assert "sandbox" in policy and "frame-ancestors 'none'" in policy


def test_dev_proxy_lists_every_api_root():
    """开发时 Vite 只把登记过的前缀转给 serve：server 加了端点、vite.config.ts 忘了登记，
    页面拿到的是 index.html（外层 #256 加 /attention /usage 时撞过）。两边的清单一字不差。"""
    import re
    from pathlib import Path

    from framework.chat.server import API_ROOTS
    config_path = Path(__file__).parents[1] / "ui" / "web" / "vite.config.ts"
    config = config_path.read_text(encoding="utf-8")
    listed = re.search(r"const API_PREFIXES = \[([^\]]*)\]", config)
    assert listed, "vite.config.ts 里找不到 API_PREFIXES"
    assert re.findall(r"'/([a-z]+)'", listed.group(1)) == list(API_ROOTS)


def test_reset_needs_the_word_and_a_home_the_platform_made(served, tmp_path):
    """外层 #263：设置页「清除全部数据」——要带「清除」两个字；不是平台建的家（没有标记）409，
    清完留一个只有标记的空家。"""
    base, _ = served
    assert call(base, "/settings/reset", {})[0] == 400
    status, _, body = call(base, "/settings/reset", {"confirm": "清除"})
    assert status == 409 and "标记" in json.loads(body)["error"]
    paths.mark(tmp_path)
    (tmp_path / "keys.yaml").write_text("deepseek: sk-test\n", encoding="utf-8")
    status, _, body = call(base, "/settings/reset", {"confirm": "清除"})
    assert status == 200 and json.loads(body)["done"][-1].startswith("已清空")
    assert [p.name for p in tmp_path.iterdir()] == [paths.MARKER_NAME]


def test_keys_are_saved_in_the_home_and_only_the_last_four_come_back(served):
    """外层 #265：设置页粘贴的 key 存进家里的 keys.yaml；回来的整份里只有末四位，
    整把 key 不出服务。"""
    base, _ = served
    status, _, body = call(base, "/settings/keys",
                           {"name": "deepseek", "value": "sk-abcdef0123456789"})
    assert status == 200 and json.loads(body)["keys"] == {"deepseek": "…6789"}
    assert "sk-abcdef" not in body and "sk-abcdef" not in call(base, "/settings")[2]
    assert keys.get("deepseek") == "sk-abcdef0123456789"
    assert call(base, "/settings/keys", {"name": "Deep Seek", "value": "x"})[0] == 400
    assert call(base, "/settings/keys", {"name": "deepseek"})[0] == 400
    status, _, body = call(base, "/settings/keys/deepseek/remove", {})
    assert status == 200 and json.loads(body)["keys"] == {} and keys.get("deepseek") is None


def test_a_chat_keeps_the_provider_it_was_opened_with(served):
    """外层 #266 / P-25：开对话把供应商与模型一起抄进 meta，续这段对话照它接——改了设置只影响
    之后开的。"""
    base, chat = served
    agents.path().write_text(
        "agents:\n  claude_code: {provider: deepseek, model: a, effort: low}\n", encoding="utf-8")
    status, _, body = call(base, "/projects/p/chats", {})
    assert status == 201 and json.loads(body)["provider"] == "deepseek"
    chat_id = json.loads(body)["chat_id"]
    agents.path().write_text("agents:\n  claude_code: {provider: official, model: a}\n",
                             encoding="utf-8")
    call(base, f"/projects/p/chats/{chat_id}/messages", {"text": "你好"})
    assert chat.providers_asked[-1] == "deepseek"
