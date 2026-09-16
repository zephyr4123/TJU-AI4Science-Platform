"""`ai4sci flow list | check <能力>...`：列预装的工作流；按描述符对吃吐文件说一串能力通不通。

在 cli 层。名字对不上退 2（用法错误），不通退 1、一行一条，通退 0 打一行。`--json` 给编排
看板：steps 与 problems。不跑任何东西——跑还是一次一个按钮（P-10）。
"""

from __future__ import annotations

import argparse
import json
import sys

from framework.capabilities import discover
from framework.chat.guide import REPO_ROOT
from framework.cli._common import EXIT_INVALID, EXIT_OK, EXIT_USAGE
from framework.contracts import workflows
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


def cmd_list(args: argparse.Namespace) -> int:
    """列 `workflows/*.yaml`：每条工作流一行，能力步骤对不上吃吐文件的退 1。"""
    catalog = {name: module.DESCRIPTOR for name, module in discover().items()}
    try:
        found = workflows.describe(
            workflows.load_workflows(workflows.workflows_root(REPO_ROOT)), catalog)
    except workflows.WorkflowInvalid as exc:
        print(str(exc), file=sys.stderr)
        return EXIT_INVALID
    if args.json:
        print(json.dumps(found, ensure_ascii=False, indent=2))
    else:
        for wf in found:
            steps = " → ".join(s["cap"] or f"[{s['key']}]" if (s["cap"] or s["key"]) else s["by"]
                               for s in wf["steps"])
            print(f"{wf['name']}\t{wf['title']}\t{steps}")
            for problem in wf["problems"]:
                print(f"  ! {problem}", file=sys.stderr)
    return EXIT_INVALID if any(wf["problems"] for wf in found) else EXIT_OK


def add_parser(groups: argparse._SubParsersAction) -> None:
    flow = groups.add_parser("flow", help="工作流：预装的清单，与一串能力通不通的检查")
    actions = flow.add_subparsers(dest="action", required=True)
    listing = actions.add_parser("list", help="列 workflows/*.yaml，能力步骤顺便核对通不通")
    listing.add_argument("--json", action="store_true", help="打 JSON（给页面）")
    listing.set_defaults(func=cmd_list)
    checking = actions.add_parser("check", help="按描述符对吃吐文件，说这条流通不通；不跑")
    checking.add_argument("steps", nargs="+", help="能力名，按顺序")
    checking.add_argument("--json", action="store_true", help="打 JSON（给编排看板）")
    checking.set_defaults(func=cmd_check)
