"""网页的后端：几个 HTTP 端点包住 conversation.py，事件用 SSE 推。

标准库 ThreadingHTTPServer：三四个端点不值得引一个 web 框架（有第二个页面要更多再说）。
零模型：模型在适配器的子进程里。节点清单（`/cap`）由调用方以函数传入——这一层不认识
capabilities，依赖方向不能反过来。

    GET  /health                 {"ok": true}
    GET  /cap                    能力描述符清单（编排看板的节点定义）
    GET  /chats                  全部对话的 meta
    POST /chats                  {"backend"?} → 新对话的 meta
    GET  /chats/<id>             meta + transcript
    POST /chats/<id>/messages    {"text"} → text/event-stream，每个事件一条 `event: <kind>`
"""

from __future__ import annotations

import json
import logging
import math
from collections.abc import Callable
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from backends import BackendNotFound, Chat, ChatEvent, get_chat
from framework.chat import conversation, guide

LOGGER = logging.getLogger("ai4sci.serve")
DEFAULT_BACKEND = "claude_code"
MAX_BODY = 1 << 20


class ChatServer(ThreadingHTTPServer):
    """把运行参数挂在 server 上，handler 从 `self.server` 拿；不用全局变量。"""

    daemon_threads = True

    def __init__(self, address: tuple[str, int], *, runs_root: Path, cwd: Path,
                 catalog: Callable[[], list[dict[str, Any]]],
                 chat_factory: Callable[[str], Chat] = get_chat,
                 system_prompt: str | None = None) -> None:
        super().__init__(address, Handler)
        self.runs_root = Path(runs_root)
        self.cwd = Path(cwd).resolve()
        self.catalog = catalog
        self.chat_factory = chat_factory
        # 指南在起服务时读一次：文件不在当场炸，不等第一条消息才发现
        self.system_prompt = guide.system_prompt() if system_prompt is None else system_prompt


class Handler(BaseHTTPRequestHandler):
    server: ChatServer

    def log_message(self, fmt: str, *args: Any) -> None:  # noqa: D401 - 走 logging，不打 stderr
        LOGGER.info("http %s", fmt % args)

    # ── GET ──────────────────────────────────────────────────────────────
    def do_GET(self) -> None:
        parts = self.path.strip("/").split("/")
        if self.path == "/health":
            return self._json({"ok": True})
        if self.path == "/cap":
            return self._json(self.server.catalog())
        if self.path == "/chats":
            return self._json([c.to_dict() for c in
                               conversation.list_conversations(self.server.runs_root)])
        if len(parts) == 2 and parts[0] == "chats":
            conv = self._conversation(parts[1])
            if conv is None:
                return None
            transcript = (conv.dir / conversation.TRANSCRIPT_NAME).read_text(encoding="utf-8")
            return self._json({**conv.to_dict(), "transcript": transcript})
        return self._error(HTTPStatus.NOT_FOUND, f"没有这个路径：{self.path}")

    # ── POST ─────────────────────────────────────────────────────────────
    def do_POST(self) -> None:
        parts = self.path.strip("/").split("/")
        body = self._body()
        if body is None:
            return None
        if self.path == "/chats":
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

    def _conversation(self, chat_id: str) -> conversation.Conversation | None:
        try:
            return conversation.load_conversation(self.server.runs_root, chat_id)
        except conversation.ConversationNotFound as exc:
            self._error(HTTPStatus.NOT_FOUND, str(exc))
            return None

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
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _error(self, status: HTTPStatus, message: str) -> None:
        self._json({"error": message}, status)
