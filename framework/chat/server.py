"""网页的后端：HTTP 端点包住 conversation.py 与 boards.py，事件用 SSE 推，页面本身也从这里端出去。

标准库 ThreadingHTTPServer：二十个端点不值得引一个 web 框架。零模型：模型在适配器的子进程里。
能力清单（`/cap`）、工作流库（`/workflows`）、流实例（`/workspaces/<id>/flows`）与流通不通检查
（`/flow/check`）由调用方以函数传入——这一层不认识 capabilities，依赖方向不能反过来。
页面是这些端点的客户端，换一种 UI 也是同一套（`ui/README.md`）。

端点按域分前缀（纲领 P-16）：工作区 `/workspaces/<id>/…` 是研究助理的域，`/studio/…` 是造流助理
的域，对话四个端点在两个前缀下共用一套实现；主页面的对话物理上到不了库。

    GET  /health                            {"ok": true}
    GET  /backends                          每家 agent 后端的旋钮：模型清单、思考深度档位、缺省
    GET  /stages                            七个科研阶段，按清单顺序
    GET  /cap                               能力描述符清单，每颗带 stage 与 used_by
    GET  /workflows                         库：`workflows/*.yaml`，covers / remarks / problems
    POST /workflows                         {name, title, summary, steps[, assumes, overwrite]}
    GET  /flow/check?steps=a,b              这串能力通不通，不跑
    GET  /workspaces                        工作区清单：标题、任务包走到哪、几个 run
    POST /workspaces                        {"id", "title"?} → 新工作区
    GET  /workspaces/<id>                   工作区 + 任务包细节 + 流实例 + run 清单
    POST /workspaces/<id>/publish           {"by"} → 发布记录；人按的键，agent 不替人按
    GET  /workspaces/<id>/flows             流实例：covers / remarks / problems
    GET  /workspaces/<id>/runs[/<rid>]      run 摘要清单 / 一个 run 的账本、分析、验证、作业
    POST /workspaces/<id>/runs/<rid>/accept {"by"} → 验收记录
    GET  /workspaces/<id>/jobs[/<jid>]      作业清单 / 一个作业
    GET  <域>/chats                         对话清单；<域> 是 /workspaces/<id> 或 /studio
    POST <域>/chats                         {"backend"?, "model"?, "effort"?} → 新对话的 meta
    GET  <域>/chats/<cid>                   meta + transcript + history
    POST <域>/chats/<cid>/messages          {"text", "model"?, "effort"?} → text/event-stream，
                                            一个事件一条；model / effort 给了就记进对话
                                            （null 是回到后端缺省）
    GET  /<其它>                            `ui_dir` 里的静态文件，找不到的回 index.html（单页应用）
"""

from __future__ import annotations

import json
import logging
import math
import mimetypes
from collections.abc import Callable
from dataclasses import asdict
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlsplit

from backends import BackendNotFound, Chat, ChatEvent, Tuning, available_backends, get_chat
from framework.chat import boards, conversation, guide, scope
from framework.contracts import publish
from framework.contracts.capability import STAGES
from framework.run import accept, jobs, layout, workspace
from framework.run.workspace import Workspace

LOGGER = logging.getLogger("ai4sci.serve")
DEFAULT_BACKEND = "claude_code"
MAX_BODY = 1 << 20
# 这些是接口；其余 GET 路径都当页面的静态文件。加端点要在这里登记，不然会被当成页面路由。
API_ROOTS = ("health", "backends", "stages", "cap", "workflows", "flow", "workspaces", "studio")
INDEX_NAME = "index.html"


class ChatServer(ThreadingHTTPServer):
    """把运行参数挂在 server 上，handler 从 `self.server` 拿；不用全局变量。"""

    daemon_threads = True

    def __init__(self, address: tuple[str, int], *, home: Path,
                 catalog: Callable[[], list[dict[str, Any]]],
                 workflows: Callable[[], list[dict[str, Any]]],
                 flows: Callable[[Workspace], list[dict[str, Any]]],
                 flow_check: Callable[[list[str]], dict[str, Any]],
                 save_workflow: Callable[[dict[str, Any]], dict[str, Any]] | None = None,
                 chat_factory: Callable[[str], Chat] = get_chat,
                 system_prompts: dict[str, str] | None = None,
                 ui_dir: Path | None = None) -> None:
        super().__init__(address, Handler)
        self.home = Path(home).resolve()
        self.catalog = catalog
        self.workflows = workflows
        self.flows = flows
        self.flow_check = flow_check
        # 编辑台存流：cli 注入（要对着能力清单核对，chat 层不认识 capabilities）；None 是不让存
        self.save_workflow = save_workflow
        self.chat_factory = chat_factory
        # 页面构建目录；None 就是没构建，根路径回一句怎么构建，接口照常
        self.ui_dir = None if ui_dir is None else Path(ui_dir).resolve()
        # 两份指南在起服务时各读一次：文件不在当场炸，不等第一条消息才发现
        self.system_prompts = ({kind: guide.system_prompt(kind) for kind in guide.KINDS}
                               if system_prompts is None else system_prompts)

    @property
    def workspaces_root(self) -> Path:
        return workspace.workspaces_root(self.home)


class Handler(BaseHTTPRequestHandler):
    server: ChatServer

    def log_message(self, fmt: str, *args: Any) -> None:  # noqa: D401 - 走 logging，不打 stderr
        LOGGER.info("http %s", fmt % args)

    # ── GET ──────────────────────────────────────────────────────────────
    def do_GET(self) -> None:
        # 盘上的东西不合约（坏的 yaml、坏的报告、少了快照）是 422 一句话，不是掉线：连接一断
        # 页面只看得到「Failed to fetch」，什么都说不清（实测：flows/ 里一个只有一行的文件）
        try:
            self._get()
        except ValueError as exc:
            LOGGER.warning("http_get_unprocessable path=%s why=%s", self.path, exc)
            self._error(HTTPStatus.UNPROCESSABLE_ENTITY, str(exc))
        except OSError as exc:
            LOGGER.exception("http_get_failed path=%s", self.path)
            self._error(HTTPStatus.INTERNAL_SERVER_ERROR, str(exc))

    def _get(self) -> None:
        url = urlsplit(self.path)
        parts = [p for p in url.path.split("/") if p]
        if not parts or parts[0] not in API_ROOTS:
            return self._static(url.path)
        if parts == ["health"]:
            return self._json({"ok": True})
        if parts == ["backends"]:
            return self._json([{"name": name, "default": name == DEFAULT_BACKEND,
                                **asdict(self.server.chat_factory(name).knobs())}
                               for name in available_backends()])
        if parts == ["stages"]:
            return self._json(list(STAGES))
        if parts == ["cap"]:
            return self._json(self.server.catalog())
        if parts == ["workflows"]:
            return self._json(self.server.workflows())
        if parts == ["flow", "check"]:
            raw = parse_qs(url.query).get("steps", [""])[0]
            steps = [s for s in raw.split(",") if s]
            if not steps:
                return self._error(HTTPStatus.BAD_REQUEST, "要有 steps=能力名,能力名")
            return self._json(self.server.flow_check(steps))
        if parts == ["workspaces"]:
            return self._json([boards.workspace_summary(ws) for ws in
                               workspace.list_workspaces(self.server.workspaces_root)])
        found = self._scope(parts)
        if found is None:
            return None
        where, rest = found
        if rest[:1] == ["chats"]:
            return self._get_chat(where, rest[1:])
        ws = where.workspace
        if ws is None:
            return self._error(HTTPStatus.NOT_FOUND, f"编辑台下只有对话：{url.path}")
        if rest == []:
            return self._json({**boards.workspace_detail(ws), "flows": self.server.flows(ws)})
        if rest == ["flows"]:
            return self._json(self.server.flows(ws))
        if rest == ["runs"]:
            return self._json(boards.list_runs(ws))
        if len(rest) == 2 and rest[0] == "runs":
            run_dir = self._run_dir(ws, rest[1])
            return None if run_dir is None else self._json(boards.run_detail(ws, run_dir))
        if rest == ["jobs"]:
            return self._json([job.to_dict() for job in jobs.list_jobs(ws.jobs)])
        if len(rest) == 2 and rest[0] == "jobs":
            try:
                return self._json(jobs.load(ws.jobs, rest[1]).to_dict())
            except jobs.JobNotFound as exc:
                return self._error(HTTPStatus.NOT_FOUND, str(exc))
        return self._error(HTTPStatus.NOT_FOUND, f"没有这个路径：{url.path}")

    def _get_chat(self, where: scope.Scope, rest: list[str]) -> None:
        if rest == []:
            return self._json([{**c.to_dict(), "title": conversation.title(c)} for c in
                               conversation.list_conversations(where.chats)])
        if len(rest) == 1:
            conv = self._conversation(where, rest[0])
            if conv is None:
                return None
            transcript = (conv.dir / conversation.TRANSCRIPT_NAME).read_text(encoding="utf-8")
            return self._json({**conv.to_dict(), "title": conversation.title(conv),
                               "transcript": transcript,
                               "history": conversation.read_turns(conv)})
        return self._error(HTTPStatus.NOT_FOUND, f"没有这个路径：{self.path}")

    # ── POST ─────────────────────────────────────────────────────────────
    def do_POST(self) -> None:
        self.streaming = False  # 头已经发出去（SSE）之后再出错，只能断流，不能再回一个 JSON
        try:
            self._post()
        except ValueError as exc:
            LOGGER.warning("http_post_unprocessable path=%s why=%s", self.path, exc)
            if self.streaming:
                raise
            self._error(HTTPStatus.UNPROCESSABLE_ENTITY, str(exc))
        except OSError as exc:
            LOGGER.exception("http_post_failed path=%s", self.path)
            if self.streaming:
                raise
            self._error(HTTPStatus.INTERNAL_SERVER_ERROR, str(exc))

    def _post(self) -> None:
        parts = [p for p in urlsplit(self.path).path.split("/") if p]
        body = self._body()
        if body is None:
            return None
        if parts == ["workflows"]:
            if self.server.save_workflow is None:
                return self._error(HTTPStatus.NOT_IMPLEMENTED, "这个服务没开存流")
            try:
                return self._json(self.server.save_workflow(body), HTTPStatus.CREATED)
            except ValueError as exc:  # WorkflowInvalid 继承 ValueError：形状不对、不通
                return self._error(HTTPStatus.UNPROCESSABLE_ENTITY, str(exc))
            except FileExistsError as exc:
                return self._error(HTTPStatus.CONFLICT, str(exc))
        if parts == ["workspaces"]:
            ws_id = body.get("id")
            if not isinstance(ws_id, str) or not ws_id.strip():
                return self._error(HTTPStatus.BAD_REQUEST, "body 要有非空的 id：工作区名")
            try:
                ws = workspace.create(self.server.workspaces_root, ws_id.strip(),
                                      title=str(body.get("title") or ""))
            except workspace.WorkspaceInvalid as exc:
                status = HTTPStatus.CONFLICT if "已经有" in str(exc) else HTTPStatus.BAD_REQUEST
                return self._error(status, str(exc))
            return self._json(boards.workspace_summary(ws), HTTPStatus.CREATED)
        found = self._scope(parts)
        if found is None:
            return None
        where, rest = found
        if rest == ["chats"]:
            backend = str(body.get("backend") or DEFAULT_BACKEND)
            try:
                chat = self.server.chat_factory(backend)  # 名字不对现在就报，别等发消息
            except BackendNotFound as exc:
                return self._error(HTTPStatus.BAD_REQUEST, str(exc))
            tuning = self._tuning(body, Tuning(), chat)
            if tuning is None:
                return None
            conv = conversation.new_conversation(where.chats, backend, where.cwd, tuning=tuning)
            return self._json(conv.to_dict(), HTTPStatus.CREATED)
        if len(rest) == 3 and rest[0] == "chats" and rest[2] == "messages":
            conv = self._conversation(where, rest[1])
            if conv is None:
                return None
            text = body.get("text")
            if not isinstance(text, str) or not text.strip():
                return self._error(HTTPStatus.BAD_REQUEST, "body 要有非空的 text")
            try:
                chat = self.server.chat_factory(conv.backend)
            except BackendNotFound as exc:
                return self._error(HTTPStatus.BAD_REQUEST, str(exc))
            tuning = self._tuning(body, conv.tuning, chat)
            if tuning is None:
                return None
            return self._stream(where, conv, chat, text, tuning)
        ws = where.workspace
        if ws is None:
            return self._error(HTTPStatus.NOT_FOUND, f"编辑台下只有对话：{self.path}")
        if rest == ["publish"]:
            by = self._by(body)
            if by is None:
                return None
            try:
                publish.publish_task(ws.task, by=by)
            except publish.PublishRefused as exc:
                return self._error(HTTPStatus.UNPROCESSABLE_ENTITY, str(exc))
            return self._json(boards.task_detail(ws.task), HTTPStatus.CREATED)
        if len(rest) == 3 and rest[0] == "runs" and rest[2] == "accept":
            run_dir = self._run_dir(ws, rest[1])
            if run_dir is None:
                return None
            by = self._by(body)
            if by is None:
                return None
            try:
                accept.accept_run(run_dir, by=by)
            except accept.AcceptRefused as exc:
                return self._error(HTTPStatus.UNPROCESSABLE_ENTITY, str(exc))
            return self._json(boards.run_detail(ws, run_dir), HTTPStatus.CREATED)
        return self._error(HTTPStatus.NOT_FOUND, f"没有这个路径：{self.path}")

    # ── 内部 ─────────────────────────────────────────────────────────────
    def _scope(self, parts: list[str]) -> tuple[scope.Scope, list[str]] | None:
        """路径前缀定域：`/studio/…` 是编辑台，`/workspaces/<id>/…` 是那个工作区；剩下的路径交回去。

        工作区只按名字从清单目录下取，不拿 URL 片段拼路径：`..` 之类先被名字规矩拒掉。"""
        if parts[0] == "studio":
            return scope.studio(self.server.home), parts[1:]
        if parts[0] == "workspaces" and len(parts) >= 2:
            ws_id = parts[1]
            if not workspace.ID_RE.fullmatch(ws_id):
                self._error(HTTPStatus.NOT_FOUND, f"没有这个工作区：{ws_id}")
                return None
            try:
                ws = workspace.load(self.server.workspaces_root / ws_id)
            except workspace.WorkspaceNotFound:
                self._error(HTTPStatus.NOT_FOUND, f"没有这个工作区：{ws_id}")
                return None
            return scope.for_workspace(ws), parts[2:]
        self._error(HTTPStatus.NOT_FOUND, f"没有这个路径：{self.path}")
        return None

    def _tuning(self, body: dict[str, Any], current: Tuning, chat: Chat) -> Tuning | None:
        """body 里的 model / effort：没给的键沿用 current，给 null 是回到后端缺省；
        不是字符串或不在这家后端的清单上就 400。"""
        picked: dict[str, str | None] = {}
        for key in ("model", "effort"):
            value = body.get(key, getattr(current, key))
            if value is not None and not isinstance(value, str):
                self._error(HTTPStatus.BAD_REQUEST, f"{key} 要是字符串或 null")
                return None
            picked[key] = value
        tuning = Tuning(**picked)
        try:
            chat.knobs().check(tuning)
        except ValueError as exc:
            self._error(HTTPStatus.BAD_REQUEST, str(exc))
            return None
        return tuning

    def _stream(self, where: scope.Scope, conv: conversation.Conversation, chat: Chat,
                text: str, tuning: Tuning) -> None:
        try:
            events = conversation.send(
                conv, chat, text, system_prompt=self.server.system_prompts[where.kind],
                allowed_paths=list(where.allowed_paths), bash_rules=guide.BASH_RULES,
                readable_paths=list(where.readable_paths), tuning=tuning)
            first = next(events)  # 忙、空消息这类错误在头响应之前就要报出来
        except conversation.ConversationBusy as exc:
            return self._error(HTTPStatus.CONFLICT, str(exc))
        except ValueError as exc:
            return self._error(HTTPStatus.BAD_REQUEST, str(exc))
        except StopIteration:
            return self._error(HTTPStatus.BAD_GATEWAY, "适配器一个事件都没吐")
        self.streaming = True
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self._sse(first)
        for event in events:
            self._sse(event)

    def _sse(self, event: ChatEvent) -> None:
        payload = {"kind": event.kind, "text": event.text, "tool": event.tool,
                   "tool_input": event.tool_input, "is_error": event.is_error,
                   "session_id": event.session_id,
                   "cost_usd": None if math.isnan(event.cost_usd) else event.cost_usd,
                   "duration_s": event.duration_s, "exit_code": event.exit_code}
        data = json.dumps(payload, ensure_ascii=False)
        self.wfile.write(f"event: {event.kind}\ndata: {data}\n\n".encode())
        self.wfile.flush()

    def _static(self, path: str) -> None:
        """页面的静态文件。找不到的路径回 index.html（单页应用自己认路由）；`assets/` 带哈希，
        可以长缓存。"""
        ui_dir = self.server.ui_dir
        if ui_dir is None:
            return self._error(HTTPStatus.NOT_FOUND,
                               "页面没构建：在 ui/web 里 npm run build（或 make ui），"
                               "也可以 ai4sci serve --ui <构建目录>")
        target = (ui_dir / path.lstrip("/")).resolve()
        if not target.is_relative_to(ui_dir):
            return self._error(HTTPStatus.FORBIDDEN, "路径越出页面目录")
        if target.is_dir():
            target = target / INDEX_NAME
        if not target.is_file():
            target = ui_dir / INDEX_NAME
            if not target.is_file():
                return self._error(HTTPStatus.NOT_FOUND, f"页面目录里没有 {INDEX_NAME}：{ui_dir}")
        data = target.read_bytes()
        ctype = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
        if ctype.startswith("text/") or ctype in ("application/javascript", "application/json"):
            ctype += "; charset=utf-8"
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "public, max-age=31536000, immutable"
                         if target.parent.name == "assets" else "no-cache")
        self.end_headers()
        self.wfile.write(data)

    def _conversation(self, where: scope.Scope, chat_id: str) -> conversation.Conversation | None:
        try:
            return conversation.load_conversation(where.chats, chat_id)
        except conversation.ConversationNotFound as exc:
            self._error(HTTPStatus.NOT_FOUND, str(exc))
            return None

    def _run_dir(self, ws: Workspace, run_id: str) -> Path | None:
        run_dir = ws.runs / run_id
        if run_id in ("", ".", "..") or "/" in run_id or not layout.checkpoint(run_dir).is_file():
            self._error(HTTPStatus.NOT_FOUND, f"run 不存在或没有 checkpoint：{run_id}")
            return None
        return run_dir

    def _by(self, body: dict[str, Any]) -> str | None:
        by = body.get("by")
        if not isinstance(by, str) or not by.strip():
            self._error(HTTPStatus.BAD_REQUEST, "body 要有非空的 by：谁按的键，记在记录上")
            return None
        return by.strip()

    def _body(self) -> dict[str, Any] | None:
        length = int(self.headers.get("Content-Length") or 0)
        if length > MAX_BODY:
            self._error(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, "body 太大")
            return None
        raw = self.rfile.read(length) if length else b""
        if not raw.strip():
            return {}
        try:
            body = json.loads(raw)
        except ValueError as exc:
            self._error(HTTPStatus.BAD_REQUEST, f"body 不是合法 JSON：{exc}")
            return None
        if not isinstance(body, dict):
            self._error(HTTPStatus.BAD_REQUEST, "body 要是 JSON 对象")
            return None
        return body

    def _json(self, payload: Any, status: HTTPStatus = HTTPStatus.OK) -> None:
        data = json.dumps(boards.jsonable(payload), ensure_ascii=False,
                          allow_nan=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _error(self, status: HTTPStatus, message: str) -> None:
        self._json({"error": message}, status)
