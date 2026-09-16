"""`ai4sci flow check <能力>...`：按描述符对吃吐文件，说这条流通不通。

在 cli 层。名字对不上退 2（用法错误），不通退 1、一行一条，通退 0 打一行。`--json` 给编排
看板：steps 与 problems。不跑任何东西——跑还是一次一个按钮（P-10）。
"""

from __future__ import annotations

import argparse
import json
import sys

from framework.capabilities import discover
from framework.cli._common import EXIT_INVALID, EXIT_OK, EXIT_USAGE
from framework.contracts.flow import check_flow


def cmd_check(args: argparse.Namespace) -> int:
    found = discover()
    unknown = [name for name in args.steps if name not in found]
    if unknown:
        print(f"没有这些能力：{unknown}（有的：{sorted(found)}）", file=sys.stderr)
        return EXIT_USAGE
    steps = [found[name].DESCRIPTOR for name in args.steps]
    problems = check_flow(steps)
    if args.json:
        print(json.dumps({"steps": list(args.steps), "problems": problems},
                         ensure_ascii=False, indent=2))
        return EXIT_INVALID if problems else EXIT_OK
    if problems:
        for problem in problems:
            print(problem, file=sys.stderr)
        return EXIT_INVALID
    print(f"ok {len(steps)} 步：{' → '.join(args.steps)}")
    return EXIT_OK


def add_parser(groups: argparse._SubParsersAction) -> None:
    flow = groups.add_parser("flow", help="一串能力摆成的流")
    actions = flow.add_subparsers(dest="action", required=True)
    checking = actions.add_parser("check", help="按描述符对吃吐文件，说这条流通不通；不跑")
    checking.add_argument("steps", nargs="+", help="能力名，按顺序")
    checking.add_argument("--json", action="store_true", help="打 JSON（给编排看板）")
    checking.set_defaults(func=cmd_check)
