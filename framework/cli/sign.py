"""`ai4sci sign task <dir> | run <id> --by <谁>`：两颗人按的键，终端这张脸。

在 cli 层。键不是能力：不产出科研产物，只落一条签字记录——需求的 `publish.json`
（`contracts.publish`）、结果的 `accept.json`（`run.accept`）。后面的按钮查的是记录，不是
谁按的；页面上的两颗键写的是同一份记录。协调 agent 的指南写明它不替人按。
"""

from __future__ import annotations

import argparse
import getpass
import sys
from pathlib import Path

from framework.cli._common import EXIT_INVALID, EXIT_OK, EXIT_USAGE, add_runs_root, open_run_dir
from framework.contracts import publish
from framework.run.accept import AcceptRefused, accept_run


def cmd_task(args: argparse.Namespace) -> int:
    """发布需求：签 manifest.yaml 与 design.md。"""
    task_dir = Path(args.task_dir)
    if not task_dir.is_dir():
        print(f"任务目录不存在：{task_dir}", file=sys.stderr)
        return EXIT_USAGE
    try:
        record = publish.publish_task(task_dir, by=args.by)
    except publish.PublishRefused as exc:
        print(str(exc), file=sys.stderr)
        return EXIT_INVALID
    print(f"ok {task_dir.resolve().name}\tby={record['by']}\tat={record['published_at']}"
          f"\tnext=ai4sci cap design {task_dir}")
    return EXIT_OK


def cmd_run(args: argparse.Namespace) -> int:
    """验收结果：签 best 与验证结论。"""
    run_dir = open_run_dir(args)
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
    sign = groups.add_parser("sign", help="人按的两颗键：发布需求、验收结果")
    what = sign.add_subparsers(dest="what", required=True)

    task = what.add_parser(
        "task", help="发布需求：看过 manifest.yaml 与 design.md 后按，写 publish.json")
    task.add_argument("task_dir", help="任务包目录")
    task.add_argument("--by", default=getpass.getuser(), help="谁按的，记在记录上；缺省当前登录名")
    task.set_defaults(func=cmd_task)

    run = what.add_parser("run", help="验收结果：看过 best、分析与验证后按，写 accept.json")
    run.add_argument("run_id")
    run.add_argument("--by", default=getpass.getuser(), help="谁按的，记在记录上；缺省当前登录名")
    add_runs_root(run)
    run.set_defaults(func=cmd_run)
