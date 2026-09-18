"""`ai4sci workspace new <id> [--title]`：起一个工作区——一份需求的家（纲领 P-15）。

在 cli 层。它不是能力（不产出科研产物）、不是键（不签字）、不是查询：是开一个新容器。人在终端里
起，页面上是 `POST /workspaces`，两处调同一个 `run.workspace.create`。任务包之后由 `cap init`
放进去。
"""

from __future__ import annotations

import argparse
import sys

from framework import paths
from framework.cli._common import EXIT_INVALID, EXIT_OK
from framework.run import workspace


def cmd_new(args: argparse.Namespace) -> int:
    try:
        ws = workspace.create(workspace.workspaces_root(paths.home()), args.id, title=args.title)
    except workspace.WorkspaceInvalid as exc:
        print(str(exc), file=sys.stderr)
        return EXIT_INVALID
    print(f"ok {ws.id}\t{ws.root}\tnext=cd {ws.root} 然后 ai4sci cap init …（起任务包）")
    return EXIT_OK


def add_parser(groups: argparse._SubParsersAction) -> None:
    space = groups.add_parser("workspace", help="工作区：一份需求的家")
    actions = space.add_subparsers(dest="action", required=True)
    creating = actions.add_parser("new", help="起一个工作区：workspaces/<id>/ 与标记文件")
    creating.add_argument("id", help="工作区名：小写英文、数字、连字符；也是任务包的 id")
    creating.add_argument("--title", default="", help="给人看的标题，缺省同 id")
    creating.set_defaults(func=cmd_new)
