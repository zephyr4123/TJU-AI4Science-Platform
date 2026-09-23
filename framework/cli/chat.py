"""`ai4sci chat new|send|list [--studio]`：在终端里和助理聊，网页没来之前的入口，也是排障入口。

在 cli 层，调 `framework.chat`。域由 `--studio` 定：给了就是编辑台的流程助理，不给就是当前项目的
研究助理（P-16；一个项目一位助理，外层 #136）。`send` 把事件逐行打到 stdout：助理的话逐字打
（delta），工具一行一个，最后一行 `done` 或 `error`；人这一轮说完，收件箱里排着的作业结果接着以
「框架」的身份念，
事件接在后面打。退出码照旧 0 / 1 / 2。`new` 与 `send` 的 `--model` / `--effort`
选模型与思考深度（外层 #86）：只认后端自报的清单，选了记进对话、之后每轮沿用；页面同一套。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from backends import BackendNotFound, ChatEvent, Tuning, get_chat
from framework import agents, paths
from framework.chat import conversation, guide, notify, removal, scope, settings
from framework.cli._common import (
    EXIT_INVALID,
    EXIT_OK,
    EXIT_USAGE,
    current_project,
    setup_logging,
)
from framework.cli.project import report


def _scope(args: argparse.Namespace) -> scope.Scope | int:
    if args.studio:
        return scope.studio(paths.home())
    found = current_project()
    return found if isinstance(found, int) else scope.for_project(found)


def _tuning(args: argparse.Namespace, current: Tuning, backend: str) -> Tuning | None | int:
    """命令行上的 `--model` / `--effort`：没给的沿用 current；给了就对着后端的清单核，不对退 2。
    两个都没给回 None（对话层沿用上次的，什么都不写）。"""
    if args.model is None and args.effort is None:
        return None
    try:
        chat = get_chat(backend)
    except BackendNotFound as exc:
        print(str(exc), file=sys.stderr)
        return EXIT_USAGE
    tuning = Tuning(model=args.model if args.model is not None else current.model,
                    effort=args.effort if args.effort is not None else current.effort)
    try:
        chat.knobs().check(tuning)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return EXIT_USAGE
    return tuning


def cmd_new(args: argparse.Namespace) -> int:
    """开一段：哪家、什么模型与深度都从按人的设置来（P-25：旋钮上只有具体值），命令行上给的压过它。"""
    try:
        backend = args.backend or agents.role_backend("chat")
        get_chat(backend)
        start = agents.tuning_for(backend)
    except (BackendNotFound, agents.AgentsInvalid) as exc:
        print(str(exc), file=sys.stderr)
        return EXIT_USAGE
    tuning = _tuning(args, start, backend)
    if isinstance(tuning, int):
        return tuning
    where = _scope(args)
    if isinstance(where, int):
        return where
    conv = conversation.new_conversation(where.chats, backend, where.cwd, tuning=tuning or start)
    studio = " --studio" if args.studio else ""
    print(f"ok {conv.chat_id}\t{conv.dir}\tnext=ai4sci chat send {conv.chat_id}{studio} \"<说话>\"")
    return EXIT_OK


def cmd_send(args: argparse.Namespace) -> int:
    where = _scope(args)
    if isinstance(where, int):
        return where
    try:
        conv = settings.ensure_tuned(conversation.load_conversation(where.chats, args.chat_id))
    except (conversation.ConversationNotFound, agents.AgentsInvalid) as exc:
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
        chat = get_chat(conv.backend)
        system_prompt = where.system_prompt(chat)
    except (guide.GuideMissing, BackendNotFound) as exc:
        print(str(exc), file=sys.stderr)
        return EXIT_INVALID
    tuning = _tuning(args, conv.tuning, conv.backend)
    if isinstance(tuning, int):
        return tuning
    setup_logging()
    last: ChatEvent | None = None
    streaming = False  # 正在逐字打一段话：完整的 text 来了只补个换行，不再打一遍
    try:
        for event in _turns(where, conv, chat, text, system_prompt, tuning):
            last = event
            if event.kind == "delta":
                print(event.text, end="", flush=True)
                streaming = True
            elif event.kind == "text" and streaming:
                print(flush=True)
                streaming = False
            else:
                print(render(event), flush=True)
    except (conversation.ConversationBusy, ValueError, BackendNotFound) as exc:
        print(str(exc), file=sys.stderr)
        return EXIT_INVALID
    if last is None or last.kind != "done":
        return EXIT_INVALID
    return EXIT_OK


def _turns(where: scope.Scope, conv: conversation.Conversation, chat, text: str,
           system_prompt: str, tuning: Tuning | None):
    """人这一轮，然后把收件箱里排着的念完（服务端 `_stream` 同一个顺序）。"""
    yield from conversation.send(
        conv, chat, text, system_prompt=system_prompt,
        allowed_paths=list(where.allowed_paths), bash_rules=guide.bash_rules(where.kind),
        readable_paths=list(where.readable_paths), tuning=tuning)
    yield from notify.follow_up(where, conv, chat, system_prompt)


def cmd_remove(args: argparse.Namespace) -> int:
    """删一段对话：目录 + 这家 CLI 存的那条会话；这一轮还在跑就拒。"""
    where = _scope(args)
    if isinstance(where, int):
        return where
    try:
        removed = removal.remove_chat(where, args.chat_id, get_chat)
    except conversation.ConversationNotFound as exc:
        print(str(exc), file=sys.stderr)
        return EXIT_USAGE
    except conversation.ConversationBusy as exc:
        print(str(exc), file=sys.stderr)
        return EXIT_INVALID
    return report(removed, f"ok 删了对话 {removed.what}")


def cmd_list(args: argparse.Namespace) -> int:
    where = _scope(args)
    if isinstance(where, int):
        return where
    for conv in conversation.list_conversations(where.chats):
        print(f"{conv.chat_id}\tturns={conv.turns}\tcost_usd={conv.cost_usd:.4f}"
              f"\tbackend={conv.backend}\tmodel={conv.model or '-'}\teffort={conv.effort or '-'}")
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
    chat = groups.add_parser(
        "chat", help="和助理聊（终端入口）：当前工作区的研究助理，或 --studio 流程助理")
    actions = chat.add_subparsers(dest="action", required=True)

    creating = actions.add_parser("new", help="开一段对话：<域>/chats/<id>/")
    creating.add_argument("--backend", default=None,
                          help="用哪家 agent；缺省照设置里「对话用」的那家（ai4sci agent list）")
    creating.add_argument("--studio", action="store_true", help="编辑台的流程助理，不看工作区")
    _add_knobs(creating)
    creating.set_defaults(func=cmd_new)

    sending = actions.add_parser("send", help="发一句话，事件逐行打出，最后一行 done / error")
    sending.add_argument("chat_id")
    sending.add_argument("text", help="消息；写 @<文件> 就读那个文件")
    sending.add_argument("--studio", action="store_true", help="编辑台的对话")
    _add_knobs(sending)
    sending.set_defaults(func=cmd_send)

    listing = actions.add_parser("list", help="列出这个域的全部对话")
    listing.add_argument("--studio", action="store_true", help="编辑台的对话")
    listing.set_defaults(func=cmd_list)

    removing = actions.add_parser("remove", help="删一段对话：目录 + 这家 CLI 存的会话；在跑就拒")
    removing.add_argument("chat_id")
    removing.add_argument("--studio", action="store_true", help="编辑台的对话")
    removing.set_defaults(func=cmd_remove)


def _add_knobs(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--model", default=None,
                        help="换模型：后端清单里的名字（GET /backends 看）")
    parser.add_argument("--effort", default=None, help="换思考深度：后端清单里的档位")
