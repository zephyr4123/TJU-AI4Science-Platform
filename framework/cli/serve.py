"""`ai4sci serve`：起网页的后端（HTTP + SSE）并把页面端出去，常驻直到 Ctrl-C。

cli 层里唯一常驻的命令：它不是"跑一个能力"，是给页面一个门。能力清单、工作流库、工作区里的流实例
与流通不通检查从 `capabilities.discover` 与 `contracts.workflows` 拿，以函数传给 server
（chat 层不认识 capabilities）。数据根是 `AI4SCI_HOME`（缺省仓根）：工作区与编辑台的对话都在它下面。

页面是 `ui/web` 构建出来的静态文件（`ui/README.md`）：缺省端 `ui/web/dist`，没构建就只开接口。
TUI 不走这里——它是终端进程，直接当这些接口的客户端。
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from framework import paths
from framework.capabilities import discover
from framework.chat import guide
from framework.chat.server import ChatServer
from framework.cli._common import EXIT_INVALID, EXIT_OK, EXIT_USAGE, setup_logging
from framework.contracts import workflows
from framework.contracts.flow import check_flow, stage_remarks, stages_of
from framework.run.workspace import Workspace

DEFAULT_UI_DIR = paths.REPO_ROOT / "ui" / "web" / "dist"


def _descriptors() -> dict[str, object]:
    return {name: module.DESCRIPTOR for name, module in discover().items()}


def _catalog() -> list[dict]:
    """与 `ai4sci show caps --json` 同一个形状：描述符加反查出来的 used_by。"""
    uses = workflows.used_by(workflows.load_valid(paths.workflows_root()))
    return [{**module.DESCRIPTOR.to_dict(), "used_by": uses.get(name, [])}
            for name, module in discover().items()]


def _workflows() -> list[dict]:
    return workflows.describe_dir(paths.workflows_root(), _descriptors())


def _flows(ws: Workspace) -> list[dict]:
    """工作区里的流实例，与库同一套形状检查；坏文件是一条问题，不是一次 500。"""
    return workflows.describe_dir(ws.flows, _descriptors())


def _save_workflow(doc: dict) -> dict:
    """编辑台存流：核对形状与通不通，写进库，回它在清单里的样子。"""
    catalog = _descriptors()
    overwrite = bool(doc.pop("overwrite", False))
    saved = workflows.save_workflow(paths.workflows_root(), doc, catalog, overwrite=overwrite)
    [described] = workflows.describe([saved], catalog)
    return described


def _flow_check(steps: list[str]) -> dict:
    """与 `ai4sci show flow --json` 同一个形状；名字对不上也当问题报，页面不该为此拿 500。"""
    found = discover()
    unknown = [name for name in steps if name not in found]
    if unknown:
        return {"steps": steps, "covers": [], "remarks": [],
                "problems": [f"没有这些能力：{unknown}（有的：{sorted(found)}）"]}
    descriptors = [found[name].DESCRIPTOR for name in steps]
    covers = stages_of(descriptors)
    return {"steps": steps, "covers": covers, "remarks": stage_remarks(covers),
            "problems": check_flow(descriptors)}


def cmd_serve(args: argparse.Namespace) -> int:
    if args.ui:
        ui_dir = Path(args.ui)
        if not (ui_dir / "index.html").is_file():
            print(f"页面目录里没有 index.html：{ui_dir}", file=sys.stderr)
            return EXIT_USAGE
    else:
        ui_dir = DEFAULT_UI_DIR if (DEFAULT_UI_DIR / "index.html").is_file() else None
    setup_logging()
    try:
        server = ChatServer((args.host, args.port), home=paths.home(), catalog=_catalog,
                            workflows=_workflows, flows=_flows, flow_check=_flow_check,
                            save_workflow=_save_workflow, ui_dir=ui_dir)
    except guide.GuideMissing as exc:
        print(str(exc), file=sys.stderr)
        return EXIT_INVALID
    host, port = server.server_address[:2]
    print(f"ok http://{host}:{port}\thome={server.home}\tui={ui_dir or '-'}", flush=True)
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
    serving.add_argument("--ui", default=None,
                         help=f"页面构建目录，缺省 {DEFAULT_UI_DIR}（没构建就只开接口）")
    serving.set_defaults(func=cmd_serve)
