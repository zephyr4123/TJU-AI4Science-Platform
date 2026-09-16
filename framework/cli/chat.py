"""`ai4sci chat new|send|list`：在终端里和协调 agent 聊，网页没来之前的入口，也是排障入口。

在 cli 层，调 `framework.chat`。`send` 把事件逐行打到 stdout：文本原样，工具一行一个，
最后一行 `done` 或 `error`；退出码照旧 0 / 1 / 2。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from backends import BackendNotFound, ChatEvent, get_chat
from framework.chat import conversation, guide
from framework.cli._common import (
    EXIT_INVALID,
    EXIT_OK,
    EXIT_USAGE,
    add_runs_root,
    runs_root,
    setup_logging,
)

DEFAULT_BACKEND = "claude_code"


def cmd_new(args: argparse.Namespace) -> int:
    try:
        get_chat(args.backend)
    except BackendNotFound as exc:
        print(str(exc), file=sys.stderr)
        return EXIT_USAGE
    cwd = Path(args.cwd) if args.cwd else guide.REPO_ROOT
    if not cwd.is_dir():
        print(f"工作目录不存在：{cwd}", file=sys.stderr)
        return EXIT_USAGE
    conv = conversation.new_conversation(runs_root(args), args.backend, cwd)
    print(f"ok {conv.chat_id}\t{conv.dir}\tnext=ai4sci chat send {conv.chat_id} \"<说话>\"")
    return EXIT_OK


def cmd_send(args: argparse.Namespace) -> int:
    try:
        conv = conversation.load_conversation(runs_root(args), args.chat_id)
    except conversation.ConversationNotFound as exc:
        print(str(exc), file=sys.stderr)
        return EXIT_USAGE
    text = args.text
    if text.startswith("@"):
        path = Path(text[1:])
        if not path.is_file():
            print(f"消息文件不存在：{path}", file=sys.stderr)
            return EXIT_USAGE
        text = path.read_text(encoding="utf-8")
    try:
        system_prompt = guide.system_prompt()
    except guide.GuideMissing as exc:
        print(str(exc), file=sys.stderr)
        return EXIT_INVALID
    setup_logging()
    last: ChatEvent | None = None
    try:
        for event in conversation.send(
            conv, get_chat(conv.backend), text, system_prompt=system_prompt,
            allowed_paths=guide.allowed_paths(Path(conv.cwd)), bash_rules=guide.BASH_RULES,
        ):
            last = event
            print(render(event), flush=True)
    except (conversation.ConversationBusy, ValueError, BackendNotFound) as exc:
        print(str(exc), file=sys.stderr)
        return EXIT_INVALID
    if last is None or last.kind != "done":
        return EXIT_INVALID
    return EXIT_OK


def cmd_list(args: argparse.Namespace) -> int:
    for conv in conversation.list_conversations(runs_root(args)):
        print(f"{conv.chat_id}\tturns={conv.turns}\tcost_usd={conv.cost_usd:.4f}"
              f"\tbackend={conv.backend}")
    return EXIT_OK


def render(event: ChatEvent) -> str:
    """一个事件一行（文本事件可能多行）。给人看的摘要，全文在 events.jsonl。"""
    if event.kind == "text":
        return event.text
    if event.kind == "tool_use":
        return f"[tool] {event.tool} {json.dumps(event.tool_input, ensure_ascii=False)[:200]}"
    if event.kind == "tool_result":
        head = event.text.strip().splitlines()[:1]
        return f"[result{' error' if event.is_error else ''}] {head[0][:200] if head else ''}"
    if event.kind == "denied":
        return f"[denied] {event.tool}: {event.text}"
    if event.kind == "init":
        return f"[init] session={event.session_id}"
    if event.kind == "done":
        return (f"done\tcost_usd={event.cost_usd:.4f}\tduration_s={event.duration_s:.1f}"
                f"\tsession={event.session_id}")
    return f"error\t{event.text}"


def add_parser(groups: argparse._SubParsersAction) -> None:
    chat = groups.add_parser("chat", help="和协调 agent 聊（终端入口）")
    actions = chat.add_subparsers(dest="action", required=True)

    creating = actions.add_parser("new", help="开一段对话：runs/chats/<id>/")
    creating.add_argument("--backend", default=DEFAULT_BACKEND, help="agent 后端名")
    creating.add_argument("--cwd", default=None, help="agent 的工作目录，缺省平台仓根")
    add_runs_root(creating)
    creating.set_defaults(func=cmd_new)

    sending = actions.add_parser("send", help="发一句话，事件逐行打出，最后一行 done / error")
    sending.add_argument("chat_id")
    sending.add_argument("text", help="消息；写 @<文件> 就读那个文件")
    add_runs_root(sending)
    sending.set_defaults(func=cmd_send)

    listing = actions.add_parser("list", help="列出全部对话")
    add_runs_root(listing)
    listing.set_defaults(func=cmd_list)
