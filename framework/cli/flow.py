"""`ai4sci flow take <name> [--as <新名>]`：把库里的一条流程取到当前工作区当实例（纲领 P-15）。

在 cli 层。流程分两层：库（出厂的 `workflows/` + 人在编辑台存的 `studio/workflows/`，流程助理只改
后者）→ 实例（工作区 `flows/`，研究助理按这份需求改参数、增删阶段与断点）。取流程就是把库里那份
复制成实例（两层都能取，名字全库唯一），过一遍同样的检查再落盘；之后
研究助理直接改 `flows/<name>.yaml`，`show flows` 校验，每个能力 `--flow <name>` 照它跑
（只有一条流程时可省）。
同名实例已在就拒绝：改实例直接改文件，不重取。
"""

from __future__ import annotations

import argparse
import sys

import yaml

from framework.capabilities import abilities
from framework.cli._common import (
    EXIT_INVALID,
    EXIT_OK,
    EXIT_USAGE,
    add_ws_option,
    current_workspace,
    library,
)
from framework.cli.project import report
from framework.contracts import workflows
from framework.workspace import removal


def cmd_take(args: argparse.Namespace) -> int:
    ws = current_workspace(args)
    if isinstance(ws, int):
        return ws
    lib = library()
    source = lib.find(args.name)
    if source is None:
        print(f"库里没有叫 {args.name!r} 的流程（有：{', '.join(lib.names()) or '-'}）",
              file=sys.stderr)
        return EXIT_USAGE
    raw = yaml.safe_load(source.read_text(encoding="utf-8"))
    name = args.as_name or args.name
    parent = lib.load(args.name)
    if isinstance(raw, dict):
        raw["name"] = name  # 实例可以换个名字：同一条库里的流程按两种参数各取一份
        if parent is not None:  # 实例也记取自哪条（P-15）：show flows 照它算差异
            raw["from"] = workflows.Origin(parent.name, parent.content_hash()).to_dict()
    try:
        taken = workflows.save_workflow(ws.flows, raw, abilities.steps(),
                                        skills=abilities.skill_names())
    except (workflows.WorkflowInvalid, FileExistsError) as exc:
        print(str(exc), file=sys.stderr)
        return EXIT_INVALID
    print(f"ok {taken.name}\tflows/{taken.name}.yaml\t{len(taken.stages)} 项"
          f"\tnext=按需要改它的阶段、能力参数或断点，ai4sci show flows 校验；然后从第一项开始走")
    # 取到手当场把流程的说明推给助理（外层 #287）：什么时候选它、断点要核什么、怎么走
    if taken.guide:
        print()
        print(taken.guide)
    return EXIT_OK


def cmd_remove(args: argparse.Namespace) -> int:
    """删工作区里的一条流程实例：有产出挂在它上面就拒。"""
    ws = current_workspace(args)
    if isinstance(ws, int):
        return ws
    try:
        removed = removal.remove_flow(ws, args.name)
    except FileNotFoundError as exc:
        print(str(exc), file=sys.stderr)
        return EXIT_USAGE
    except removal.RemovalRefused as exc:
        print(str(exc), file=sys.stderr)
        return EXIT_INVALID
    return report(removed, f"ok 删了流程实例 {removed.what}")


def cmd_new_workflow(args: argparse.Namespace) -> int:
    """在库里人存的那层起一条流程，名字与 `from` 由平台填（纲领 P-15）：`--from <名字>` 是派生，
    照抄那条、名字起成 `<家族名>-<序号>`；不带就是从零起一条，名字由流程助理给。"""
    lib = library()
    if args.parent:
        if args.name:
            print("派生的名字由平台起，不用给：去掉名字，或去掉 --from", file=sys.stderr)
            return EXIT_USAGE
        try:
            doc = lib.derive(args.parent)
        except FileNotFoundError as exc:
            print(str(exc), file=sys.stderr)
            return EXIT_USAGE
        if args.title:
            doc["title"] = args.title
    else:
        if not args.name or not args.title:
            print("从零起一条要给英文名与标题：ai4sci workflow new <name> --title <标题>"
                  "（从库里一条改，用 --from <名字>，名字由平台起）", file=sys.stderr)
            return EXIT_USAGE
        doc = {"name": args.name, "title": args.title, "summary": args.title,
               "stages": ["设计"]}
    try:
        saved = lib.save(doc, abilities.steps(), skills=abilities.skill_names(), draft=True)
    except (workflows.WorkflowInvalid, FileExistsError) as exc:
        print(str(exc), file=sys.stderr)
        return EXIT_INVALID
    origin = f"\tfrom={saved.origin.name}" if saved.origin else ""
    # 打实际路径：助理站在 studio/ 里、人在终端站在别处，照着都找得到
    print(f"ok {saved.name}\t{lib.find(saved.name)}{origin}"
          f"\tnext=改这个文件（阶段、能力、断点、标题、说明；起点与库里某条一样，改出不同之前"
          f" show workflows 会标「一模一样」），ai4sci show workflows 校验")
    return EXIT_OK


def cmd_remove_workflow(args: argparse.Namespace) -> int:
    """删库里人自己存的一条流程（平台的家里的 studio/workflows/）；出厂的拒。"""
    try:
        library().remove(args.name)
    except FileNotFoundError as exc:
        print(str(exc), file=sys.stderr)
        return EXIT_USAGE
    except workflows.WorkflowInvalid as exc:
        print(str(exc), file=sys.stderr)
        return EXIT_INVALID
    print(f"ok 删了库里的流程 {args.name}")
    return EXIT_OK


def add_parser(groups: argparse._SubParsersAction) -> None:
    flow = groups.add_parser("flow", help="流程实例：把库里的流程取到一个工作区")
    actions = flow.add_subparsers(dest="action", required=True)
    taking = actions.add_parser(
        "take", help="取一条：复制库里的 workflows/<name>.yaml 成 flows/<name>.yaml")
    taking.add_argument("name", help="库里的流程名（ai4sci show workflows）")
    taking.add_argument("--as", dest="as_name", default="", help="实例换个名字，缺省同名")
    add_ws_option(taking)
    taking.set_defaults(func=cmd_take)
    removing = actions.add_parser("remove", help="删工作区里的一条流程实例；有产出挂着就拒")
    removing.add_argument("name", help="实例名（flows/<name>.yaml）")
    add_ws_option(removing)
    removing.set_defaults(func=cmd_remove)

    lib = groups.add_parser(
        "workflow", help="流程库：人存的流程文件（家里的 studio/workflows/*.yaml）；出厂的只读")
    lib_actions = lib.add_subparsers(dest="action", required=True)
    making = lib_actions.add_parser(
        "new", help="起一条：--from <名字> 从库里一条派生（名字平台起），或 <name> --title 从零起")
    making.add_argument("name", nargs="?", default="", help="从零起时的英文名（小写、连字符）")
    making.add_argument("--from", dest="parent", default="", help="从库里哪条派生")
    making.add_argument("--title", default="", help="标题（中文，一句话）；派生时缺省照抄父流程的")
    making.set_defaults(func=cmd_new_workflow)
    dropping = lib_actions.add_parser("remove", help="删库里人自己存的一条流程；出厂的不能删")
    dropping.add_argument("name", help="流程名（文件名去掉 .yaml）")
    dropping.set_defaults(func=cmd_remove_workflow)
