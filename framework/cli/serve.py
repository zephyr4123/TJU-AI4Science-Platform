"""`ai4sci serve`：起网页的后端（HTTP + SSE），常驻直到 Ctrl-C。

cli 层里唯一常驻的命令：它不是"跑一个能力"，是给页面一个门。节点清单从 `capabilities.discover`
拿，以函数传给 server（chat 层不认识 capabilities）。
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from framework.capabilities import discover
from framework.chat import guide
from framework.chat.server import ChatServer
from framework.cli._common import (
    EXIT_INVALID,
    EXIT_OK,
    EXIT_USAGE,
    add_runs_root,
    runs_root,
    setup_logging,
)


def _catalog() -> list[dict]:
    return [module.DESCRIPTOR.to_dict() for module in discover().values()]


def cmd_serve(args: argparse.Namespace) -> int:
    cwd = Path(args.cwd) if args.cwd else guide.REPO_ROOT
    if not cwd.is_dir():
        print(f"工作目录不存在：{cwd}", file=sys.stderr)
        return EXIT_USAGE
    setup_logging()
    try:
        server = ChatServer((args.host, args.port), runs_root=runs_root(args), cwd=cwd,
                            catalog=_catalog)
    except guide.GuideMissing as exc:
        print(str(exc), file=sys.stderr)
        return EXIT_INVALID
    host, port = server.server_address[:2]
    print(f"ok http://{host}:{port}\tcwd={cwd}\truns={server.runs_root}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return EXIT_OK


def add_parser(groups: argparse._SubParsersAction) -> None:
    serving = groups.add_parser("serve", help="起网页后端：HTTP + SSE，常驻")
    serving.add_argument("--host", default="127.0.0.1")
    serving.add_argument("--port", type=int, default=8765)
    serving.add_argument("--cwd", default=None, help="协调 agent 的工作目录，缺省平台仓根")
    add_runs_root(serving)
    serving.set_defaults(func=cmd_serve)
