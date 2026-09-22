"""`ai4sci workspace new <id> [--title] [--template]` / `workspace remove <id>`：在当前项目里起一个
工作区——一份需求的家（纲领 P-15、P-19）、删一个工作区。

在 cli 层。起工作区不是能力（不产出科研产物）、不是确认、不是查询：是在项目里开一个新容器，并按模板
起草 `requirement.md`（第一个一级标题是课题标题）。人在终端里起，页面上是
`POST /projects/<p>/workspaces`，
两处调同一个 `workspace.project.new_workspace`。删工作区级联的是它在每台机器上的镜像；对话归项目，
删工作区不动它。
"""

from __future__ import annotations

import argparse
import sys

from framework import paths
from framework.chat import removal
from framework.cli._common import EXIT_INVALID, EXIT_OK, EXIT_USAGE, current_project
from framework.cli.project import report
from framework.workspace import project, root

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
    found = current_project()
    if isinstance(found, int):
        return found
    try:
        template = read_template(args.template)
    except FileNotFoundError as exc:
        print(str(exc), file=sys.stderr)
        return EXIT_USAGE
    try:
        ws = project.new_workspace(found, args.id, title=args.title, template=template)
    except root.WorkspaceInvalid as exc:
        print(str(exc), file=sys.stderr)
        return EXIT_INVALID
    print(f"ok {ws.id}\t{ws.root}"
          f"\tnext=原件放进它的 materials/，和研究者把 requirement.md 写好"
          f"（工作区级的命令带 --ws {ws.id}）")
    return EXIT_OK


def cmd_remove(args: argparse.Namespace) -> int:
    """删当前项目里的一个工作区：需求、原件、产出、流程实例、作业记录，加每台机器上的镜像。
    有作业在跑、兄弟工作区读过它的产出就拒。"""
    found = current_project()
    if isinstance(found, int):
        return found
    try:
        ws = found.workspace(args.id)
    except (root.WorkspaceInvalid, root.WorkspaceNotFound) as exc:
        print(str(exc), file=sys.stderr)
        return EXIT_USAGE
    try:
        removed = removal.remove_workspace(ws)
    except removal.RemovalRefused as exc:
        print(str(exc), file=sys.stderr)
        return EXIT_INVALID
    return report(removed, f"ok 删了工作区 {removed.what}")


def add_parser(groups: argparse._SubParsersAction) -> None:
    space = groups.add_parser("workspace", help="工作区：项目里一份需求的家")
    actions = space.add_subparsers(dest="action", required=True)
    creating = actions.add_parser(
        "new", help="在当前项目里起一个工作区：workspaces/<id>/ 与按模板起草的 requirement.md")
    creating.add_argument("id", help="工作区名：小写英文、数字、连字符")
    creating.add_argument("--title", default="", help="课题标题，缺省同 id")
    creating.add_argument("--template", default=DEFAULT_TEMPLATE,
                          help="需求模板名（ai4sci show templates），缺省 generic")
    creating.set_defaults(func=cmd_new)
    removing = actions.add_parser(
        "remove",
        help="删当前项目里的一个工作区（级联机器上的镜像）；有作业在跑、兄弟读过它的产出就拒")
    removing.add_argument("id", help="工作区名")
    removing.set_defaults(func=cmd_remove)
