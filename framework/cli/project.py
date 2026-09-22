"""`ai4sci project new <id> [--title] [--goal]` / `project remove <id>`：起一个项目、删一个项目
（纲领 P-15 改，外层 #136）。

在 cli 层。项目是一位助理的地盘：一个课题、几个工作区、共用原件、助理的对话。`new` 只写 project.md
与几个空目录，工作区另起（`ai4sci workspace new`）。人在终端里起，页面上是 `POST /projects`，两处调
同一个
`workspace.project.create`。删是级联：全部工作区、每段对话在 CLI 那边的会话、每台机器上的镜像。
"""

from __future__ import annotations

import argparse
import sys

from backends import get_chat
from framework import paths
from framework.chat import removal
from framework.cli._common import EXIT_INVALID, EXIT_OK, EXIT_USAGE
from framework.workspace import project


def cmd_new(args: argparse.Namespace) -> int:
    try:
        made = project.create(project.projects_root(paths.home()), args.id, title=args.title,
                              goal=args.goal)
    except project.ProjectInvalid as exc:
        print(str(exc), file=sys.stderr)
        return EXIT_INVALID
    print(f"ok {made.id}\t{made.root}"
          f"\tnext=cd {made.root}，ai4sci workspace new <名字> 起第一个工作区")
    return EXIT_OK


def cmd_remove(args: argparse.Namespace) -> int:
    """删整个项目：全部工作区、对话及其会话、机器上的镜像。有作业或对话在跑就拒。"""
    try:
        found = project.load(project.projects_root(paths.home()) / args.id)
    except project.ProjectNotFound as exc:
        print(str(exc), file=sys.stderr)
        return EXIT_USAGE
    try:
        removed = removal.remove_project(found, get_chat)
    except removal.RemovalRefused as exc:
        print(str(exc), file=sys.stderr)
        return EXIT_INVALID
    return report(removed, f"ok 删了项目 {removed.what}")


def report(removed: removal.Removed, line: str) -> int:
    """删完怎么说：全干净一行 ok；目录外有没清的，逐条打到 stderr、退出码非零——本机已删这件事
    也说清。"""
    if removed.clean:
        print(line)
        return EXIT_OK
    print(f"{line}（本机已删；下面这些没清干净）")
    for item in removed.leftovers:
        print(f"  ! {item}", file=sys.stderr)
    return EXIT_INVALID


def add_parser(groups: argparse._SubParsersAction) -> None:
    group = groups.add_parser("project", help="项目：一位助理的地盘，一个课题几个工作区")
    actions = group.add_subparsers(dest="action", required=True)
    creating = actions.add_parser("new", help="起一个项目：projects/<id>/ 与 project.md")
    creating.add_argument("id", help="项目名：小写英文、数字、连字符")
    creating.add_argument("--title", default="", help="项目标题，缺省同 id")
    creating.add_argument("--goal", default="", help="目标一段，写进 project.md")
    creating.set_defaults(func=cmd_new)
    removing = actions.add_parser(
        "remove", help="删整个项目（级联：全部工作区、对话及其会话、机器上的镜像）；有东西在跑就拒")
    removing.add_argument("id", help="项目名")
    removing.set_defaults(func=cmd_remove)
