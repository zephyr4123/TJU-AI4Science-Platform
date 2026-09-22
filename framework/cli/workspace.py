"""`ai4sci workspace new <id> [--title] [--template]`：起一个工作区——一份需求的家（纲领 P-15、P-19）
。

在 cli 层。它不是能力（不产出科研产物）、不是确认、不是查询：是开一个新容器，并按模板起草
`requirement.md`（第一个一级标题是课题标题）。人在终端里起，页面上是 `POST /workspaces`，
两处调同一个
`workspace.root.create`。
"""

from __future__ import annotations

import argparse
import sys

from backends import get_chat
from framework import paths
from framework.chat import removal
from framework.cli._common import EXIT_INVALID, EXIT_OK, EXIT_USAGE
from framework.workspace import root

DEFAULT_TEMPLATE = "generic"


def read_template(name: str) -> str:
    """库里的一份需求模板原文；没有就 FileNotFoundError（信息带着有哪些）。"""
    library = paths.templates_root()
    path = library / f"{name}.md"
    if not path.is_file():
        available = ", ".join(sorted(p.stem for p in library.glob("*.md"))) or "-"
        raise FileNotFoundError(f"库里没有叫 {name!r} 的需求模板（有：{available}）")
    return path.read_text(encoding="utf-8")


def cmd_new(args: argparse.Namespace) -> int:
    try:
        template = read_template(args.template)
    except FileNotFoundError as exc:
        print(str(exc), file=sys.stderr)
        return EXIT_USAGE
    try:
        ws = root.create(root.workspaces_root(paths.home()), args.id, title=args.title,
                         template=template)
    except root.WorkspaceInvalid as exc:
        print(str(exc), file=sys.stderr)
        return EXIT_INVALID
    print(f"ok {ws.id}\t{ws.root}"
          f"\tnext=cd {ws.root}，原件放进 materials/，和研究者把 requirement.md 写好")
    return EXIT_OK


def cmd_remove(args: argparse.Namespace) -> int:
    """删整个工作区：需求、原件、产出、流程实例、对话、作业记录，加每段对话在 CLI 那边的会话、
    每台机器上的镜像。有作业或对话在跑就拒。"""
    try:
        ws = root.load(root.workspaces_root(paths.home()) / args.id)
    except root.WorkspaceNotFound as exc:
        print(str(exc), file=sys.stderr)
        return EXIT_USAGE
    try:
        removed = removal.remove_workspace(ws, get_chat)
    except removal.RemovalRefused as exc:
        print(str(exc), file=sys.stderr)
        return EXIT_INVALID
    return report(removed, f"ok 删了工作区 {removed.what}")


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
    space = groups.add_parser("workspace", help="工作区：一份需求的家")
    actions = space.add_subparsers(dest="action", required=True)
    creating = actions.add_parser(
        "new", help="起一个工作区：workspaces/<id>/ 与按模板起草的 requirement.md")
    creating.add_argument("id", help="工作区名：小写英文、数字、连字符")
    creating.add_argument("--title", default="", help="课题标题，缺省同 id")
    creating.add_argument("--template", default=DEFAULT_TEMPLATE,
                          help="需求模板名（ai4sci show templates），缺省 generic")
    creating.set_defaults(func=cmd_new)
    removing = actions.add_parser(
        "remove", help="删整个工作区（级联：产出、对话及其会话、机器上的镜像）；有东西在跑就拒")
    removing.add_argument("id", help="工作区名")
    removing.set_defaults(func=cmd_remove)
