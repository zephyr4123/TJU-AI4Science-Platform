"""网页的后端：HTTP 端点包住 conversation.py 与 boards.py，事件用 SSE 推，页面本身也从这里端出去。

标准库 ThreadingHTTPServer：十来个端点不值得引一个 web 框架。零模型：模型在适配器的子进程里。
能力清单（`/cap`）、工作流清单（`/workflows`）与流通不通检查（`/flow/check`）由调用方以函数
传入——这一层不认识 capabilities，依赖方向不能反过来。页面是这些端点的客户端，换一种 UI 也是
同一套（`ui/README.md`）。

    GET  /health                   {"ok": true}
    GET  /cap                      能力描述符清单：平台的全部按钮
    GET  /workflows                预装的工作流清单（`workflows/*.yaml`），每条带 problems
    GET  /flow/check?steps=a,b     {"steps", "problems"}：这串能力通不通，不跑
    GET  /chats                    全部对话的 meta + title（第一句话）
    POST /chats                    {"backend"?} → 新对话的 meta
    GET  /chats/<id>               meta + transcript + history（一轮一条 message / reply）
    POST /chats/<id>/messages      {"text"} → text/event-stream，每个事件一条 `event: <kind>`
    GET  /tasks                    需求看板：任务包清单（阶段、钥匙）
    GET  /tasks/<id>               manifest、design.md、发布前检查、预检
    POST /tasks/<id>/publish       {"by"} → 发布记录；这是人按的键，agent 不该替人按
    GET  /runs                     结果验收：run 清单（best、账本花费、验证、验收）
    GET  /runs/<id>                账本全部行、journal、分析全文、验证报告
    POST /runs/<id>/accept         {"by"} → 验收记录
    GET  /<其它>                   `ui_dir` 里的静态文件，找不到的路径回 index.html（单页应用）
"""

from __future__ import annotations

import json
import logging
import math
import mimetypes
from collections.abc import Callable
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlsplit

from backends import BackendNotFound, Chat, ChatEvent, get_chat
from framework.chat import boards, conversation, guide
from framework.contracts import packs, publish
from framework.run import accept, layout

LOGGER = logging.getLogger("ai4sci.serve")
DEFAULT_BACKEND = "claude_code"
MAX_BODY = 1 << 20
# 这些是接口；其余 GET 路径都当页面的静态文件。加端点要在这里登记，不然会被当成页面路由。
API_ROOTS = ("health", "cap", "workflows", "flow", "chats", "tasks", "runs")
INDEX_NAME = "index.html"


class ChatServer(ThreadingHTTPServer):
    """把运行参数挂在 server 上，handler 从 `self.server` 拿；不用全局变量。"""

    daemon_threads = True

    def __init__(self, address: tuple[str, int], *, runs_root: Path, cwd: Path,
                 catalog: Callable[[], list[dict[str, Any]]],
                 workflows: Callable[[], list[dict[str, Any]]],
                 flow_check: Callable[[list[str]], dict[str, Any]],
                 chat_factory: Callable[[str], Chat] = get_chat,
                 system_prompt: str | None = None, ui_dir: Path | None = None) -> None:
        super().__init__(address, Handler)
        self.runs_root = Path(runs_root)
        self.cwd = Path(cwd).resolve()
        self.catalog = catalog
        self.workflows = workflows
        self.flow_check = flow_check
        self.chat_factory = chat_factory
        # 页面构建目录；None 就是没构建，根路径回一句怎么构建，接口照常
        self.ui_dir = None if ui_dir is None else Path(ui_dir).resolve()
        # 指南在起服务时读一次：文件不在当场炸，不等第一条消息才发现
        self.system_prompt = guide.system_prompt() if system_prompt is None else system_prompt


class Handler(BaseHTTPRequestHandler):
    server: ChatServer

    def log_message(self, fmt: str, *args: Any) -> None:  # noqa: D401 - 走 logging，不打 stderr
        LOGGER.info("http %s", fmt % args)

    # ── GET ──────────────────────────────────────────────────────────────
    def do_GET(self) -> None:
        url = urlsplit(self.path)
        parts = [p for p in url.path.split("/") if p]
        if not parts or parts[0] not in API_ROOTS:
            return self._static(url.path)
        if parts == ["health"]:
            return self._json({"ok": True})
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
        if parts == ["chats"]:
            return self._json([{**c.to_dict(), "title": conversation.title(c)} for c in
                               conversation.list_conversations(self.server.runs_root)])
        if len(parts) == 2 and parts[0] == "chats":
            conv = self._conversation(parts[1])
            if conv is None:
                return None
            transcript = (conv.dir / conversation.TRANSCRIPT_NAME).read_text(encoding="utf-8")
            return self._json({**conv.to_dict(), "title": conversation.title(conv),
                               "transcript": transcript,
                               "history": conversation.read_turns(conv)})
        if parts == ["tasks"]:
            try:
                return self._json(boards.list_tasks(self.server.cwd))
            except (ValueError, NotADirectoryError) as exc:
                # 发现阶段的拓扑错误（id 重复、目录名对不上）是仓的毛病，说清楚，不静默跳过坏包
                return self._error(HTTPStatus.CONFLICT, str(exc))
        if len(parts) == 2 and parts[0] == "tasks":
            task_dir = self._task_dir(parts[1])
            return None if task_dir is None else self._json(boards.task_detail(task_dir))
        if parts == ["runs"]:
            return self._json(boards.list_runs(self.server.runs_root))
        if len(parts) == 2 and parts[0] == "runs":
            run_dir = self._run_dir(parts[1])
            return None if run_dir is None else self._json(boards.run_detail(run_dir))
        return self._error(HTTPStatus.NOT_FOUND, f"没有这个路径：{url.path}")

    # ── POST ─────────────────────────────────────────────────────────────
    def do_POST(self) -> None:
        parts = [p for p in urlsplit(self.path).path.split("/") if p]
        body = self._body()
        if body is None:
            return None
        if parts == ["chats"]:
            backend = str(body.get("backend") or DEFAULT_BACKEND)
            try:
                self.server.chat_factory(backend)  # 名字不对现在就报，别等发消息
            except BackendNotFound as exc:
                return self._error(HTTPStatus.BAD_REQUEST, str(exc))
            conv = conversation.new_conversation(self.server.runs_root, backend, self.server.cwd)
            return self._json(conv.to_dict(), HTTPStatus.CREATED)
        if len(parts) == 3 and parts[0] == "chats" and parts[2] == "messages":
            conv = self._conversation(parts[1])
            if conv is None:
                return None
            text = body.get("text")
            if not isinstance(text, str) or not text.strip():
                return self._error(HTTPStatus.BAD_REQUEST, "body 要有非空的 text")
            return self._stream(conv, text)
        if len(parts) == 3 and parts[0] == "tasks" and parts[2] == "publish":
            task_dir = self._task_dir(parts[1])
            if task_dir is None:
                return None
            by = self._by(body)
            if by is None:
                return None
            try:
                publish.publish_task(task_dir, by=by)
            except publish.PublishRefused as exc:
                return self._error(HTTPStatus.UNPROCESSABLE_ENTITY, str(exc))
            return self._json(boards.task_detail(task_dir), HTTPStatus.CREATED)
        if len(parts) == 3 and parts[0] == "runs" and parts[2] == "accept":
            run_dir = self._run_dir(parts[1])
            if run_dir is None:
                return None
            by = self._by(body)
            if by is None:
                return None
            try:
                accept.accept_run(run_dir, by=by)
            except accept.AcceptRefused as exc:
                return self._error(HTTPStatus.UNPROCESSABLE_ENTITY, str(exc))
            return self._json(boards.run_detail(run_dir), HTTPStatus.CREATED)
        return self._error(HTTPStatus.NOT_FOUND, f"没有这个路径：{self.path}")

    # ── 内部 ─────────────────────────────────────────────────────────────
    def _stream(self, conv: conversation.Conversation, text: str) -> None:
        try:
            chat = self.server.chat_factory(conv.backend)
            events = conversation.send(
                conv, chat, text, system_prompt=self.server.system_prompt,
                allowed_paths=guide.allowed_paths(self.server.cwd), bash_rules=guide.BASH_RULES)
            first = next(events)  # 忙、空消息这类错误在头响应之前就要报出来
        except conversation.ConversationBusy as exc:
            return self._error(HTTPStatus.CONFLICT, str(exc))
        except (ValueError, BackendNotFound) as exc:
            return self._error(HTTPStatus.BAD_REQUEST, str(exc))
        except StopIteration:
            return self._error(HTTPStatus.BAD_GATEWAY, "适配器一个事件都没吐")
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

    def _conversation(self, chat_id: str) -> conversation.Conversation | None:
        try:
            return conversation.load_conversation(self.server.runs_root, chat_id)
        except conversation.ConversationNotFound as exc:
            self._error(HTTPStatus.NOT_FOUND, str(exc))
            return None

    def _task_dir(self, task_id: str) -> Path | None:
        """任务目录只从发现结果里取，不拿 URL 片段拼路径：`..` 之类根本走不到文件系统。"""
        try:
            found = packs.discover_tasks(self.server.cwd)
        except (ValueError, NotADirectoryError) as exc:
            self._error(HTTPStatus.CONFLICT, str(exc))
            return None
        task_dir = found.get(task_id)
        if task_dir is None:
            self._error(HTTPStatus.NOT_FOUND, f"没有这个任务包：{task_id}")
        return task_dir

    def _run_dir(self, run_id: str) -> Path | None:
        run_dir = self.server.runs_root / run_id
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
