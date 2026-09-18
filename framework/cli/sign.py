"""`ai4sci sign task | run <id> --by <谁>`：人的两处确认（发布需求、验收结果），终端这张脸。

在 cli 层。确认不是能力：不产出科研产物，只落一条记录——需求的 `task/publish.json`
（`contracts.publish`）、结果的 `accept.json`（`run.accept`）。后面的能力查的是记录，不是
谁签的；页面上的发布、验收写的是同一份记录。协调 agent 的指南写明它不替人签。
发布签的是当前工作区的需求，不带路径（P-15）。
"""

from __future__ import annotations

import argparse
import getpass
import sys

from framework.cli._common import EXIT_INVALID, EXIT_OK, current_workspace, open_run_dir
from framework.contracts import publish
from framework.run.accept import AcceptRefused, accept_run


def cmd_task(args: argparse.Namespace) -> int:
    """发布需求：签 manifest.yaml 与 design.md。"""
    ws = current_workspace()
    if isinstance(ws, int):
        return ws
    if not ws.task.is_dir():
        print(f"这个工作区还没有任务包：先 ai4sci cap init（{ws.task}）", file=sys.stderr)
        return EXIT_INVALID
    try:
        record = publish.publish_task(ws.task, by=args.by)
    except publish.PublishRefused as exc:
        print(str(exc), file=sys.stderr)
        return EXIT_INVALID
    print(f"ok {ws.id}\tby={record['by']}\tat={record['published_at']}\tnext=ai4sci cap design")
    return EXIT_OK


def cmd_run(args: argparse.Namespace) -> int:
    """验收结果：签 best 与验证结论。"""
    ws = current_workspace()
    if isinstance(ws, int):
        return ws
    run_dir = open_run_dir(ws, args.run_id)
    if isinstance(run_dir, int):
        return run_dir
    try:
        record = accept_run(run_dir, by=args.by)
    except AcceptRefused as exc:
        print(str(exc), file=sys.stderr)
        return EXIT_INVALID
    print(f"ok {args.run_id}\tby={record['by']}\tbest_iter={record['best_iter']}"
          f"\tbest_metric={record['best_metric']}\tverify={record['verify'] or '-'}")
    return EXIT_OK


def add_parser(groups: argparse._SubParsersAction) -> None:
    sign = groups.add_parser("sign", help="人的确认：发布需求、验收结果")
    what = sign.add_subparsers(dest="what", required=True)

    task = what.add_parser(
        "task", help="发布当前工作区的需求：看过 manifest.yaml 与 design.md 后签，写 publish.json")
    task.add_argument("--by", default=getpass.getuser(), help="谁签的，记在记录上；缺省当前登录名")
    task.set_defaults(func=cmd_task)

    run = what.add_parser("run", help="验收结果：看过 best、分析与验证后签，写 accept.json")
    run.add_argument("run_id")
    run.add_argument("--by", default=getpass.getuser(), help="谁签的，记在记录上；缺省当前登录名")
    run.set_defaults(func=cmd_run)
