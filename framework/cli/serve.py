"""`ai4sci serve`：起网页的后端（HTTP + SSE）并把页面端出去，常驻直到 Ctrl-C。

cli 层里唯一常驻的命令：它不是"跑一个能力"，是给页面一个门。能力清单、工作流清单与流通不通检查从
`capabilities.discover` 与 `workflows/` 拿，以函数传给 server（chat 层不认识 capabilities）。

页面是 `ui/web` 构建出来的静态文件（`ui/README.md`）：缺省端 `ui/web/dist`，没构建就只开接口。
TUI 不走这里——它是终端进程，直接当这些接口的客户端。
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
from framework.contracts import workflows
from framework.contracts.flow import check_flow

DEFAULT_UI_DIR = guide.REPO_ROOT / "ui" / "web" / "dist"


def _catalog() -> list[dict]:
    return [module.DESCRIPTOR.to_dict() for module in discover().values()]


def _workflows() -> list[dict]:
    catalog = {name: module.DESCRIPTOR for name, module in discover().items()}
    return workflows.describe(workflows.load_workflows(workflows.workflows_root(guide.REPO_ROOT)),
                              catalog)


def _flow_check(steps: list[str]) -> dict:
    """与 `ai4sci flow check --json` 同一个形状；名字对不上也当问题报，页面不该为此拿 500。"""
    found = discover()
    unknown = [name for name in steps if name not in found]
    if unknown:
        return {"steps": steps, "problems": [f"没有这些能力：{unknown}（有的：{sorted(found)}）"]}
    return {"steps": steps, "problems": check_flow([found[name].DESCRIPTOR for name in steps])}


def cmd_serve(args: argparse.Namespace) -> int:
    cwd = Path(args.cwd) if args.cwd else guide.REPO_ROOT
    if not cwd.is_dir():
        print(f"工作目录不存在：{cwd}", file=sys.stderr)
        return EXIT_USAGE
    if args.ui:
        ui_dir = Path(args.ui)
        if not (ui_dir / "index.html").is_file():
            print(f"页面目录里没有 index.html：{ui_dir}", file=sys.stderr)
            return EXIT_USAGE
    else:
        ui_dir = DEFAULT_UI_DIR if (DEFAULT_UI_DIR / "index.html").is_file() else None
    setup_logging()
    try:
        server = ChatServer((args.host, args.port), runs_root=runs_root(args), cwd=cwd,
                            catalog=_catalog, workflows=_workflows, flow_check=_flow_check,
                            ui_dir=ui_dir)
    except guide.GuideMissing as exc:
        print(str(exc), file=sys.stderr)
        return EXIT_INVALID
    host, port = server.server_address[:2]
    print(f"ok http://{host}:{port}\tcwd={cwd}\truns={server.runs_root}\tui={ui_dir or '-'}",
          flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return EXIT_OK


def add_parser(groups: argparse._SubParsersAction) -> None:
    serving = groups.add_parser("serve", help="起网页后端：HTTP + SSE，端出页面，常驻")
    serving.add_argument("--host", default="127.0.0.1")
    serving.add_argument("--port", type=int, default=8765)
    serving.add_argument("--cwd", default=None, help="协调 agent 的工作目录，缺省平台仓根")
    serving.add_argument("--ui", default=None,
                         help=f"页面构建目录，缺省 {DEFAULT_UI_DIR}（没构建就只开接口）")
    add_runs_root(serving)
    serving.set_defaults(func=cmd_serve)
