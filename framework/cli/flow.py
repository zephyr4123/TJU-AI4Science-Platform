"""`ai4sci flow take <name> [--as <新名>]`：把库里的一条流程取到当前工作区当实例（纲领 P-15）。

在 cli 层。流程分两层：库（`workflows/`，流程助理改）→ 实例（工作区 `flows/`，研究助理按这份需求
改参数、增删阶段与断点）。取流程就是把库里那份复制成实例，过一遍同样的检查再落盘；之后
研究助理直接改 `flows/<name>.yaml`，`show flows` 校验，每个能力 `--flow <name>` 照它跑
（只有一条流程时可省）。
同名实例已在就拒绝：改实例直接改文件，不重取。
"""

from __future__ import annotations

import argparse
import sys

import yaml

from framework import paths
from framework.capabilities import abilities
from framework.cli._common import (
    EXIT_INVALID,
    EXIT_OK,
    EXIT_USAGE,
    add_ws_option,
    current_workspace,
)
from framework.cli.project import report
from framework.contracts import workflows
from framework.workspace import removal


def cmd_take(args: argparse.Namespace) -> int:
    ws = current_workspace(args)
    if isinstance(ws, int):
        return ws
    library = paths.workflows_root()
    source = library / f"{args.name}.yaml"
    if not source.is_file():
        available = ", ".join(sorted(p.stem for p in library.glob("*.yaml"))) or "-"
        print(f"库里没有叫 {args.name!r} 的流程（有：{available}）", file=sys.stderr)
        return EXIT_USAGE
    raw = yaml.safe_load(source.read_text(encoding="utf-8"))
    name = args.as_name or args.name
    if isinstance(raw, dict):
        raw["name"] = name  # 实例可以换个名字：同一条库里的流程按两种参数各取一份
    try:
        taken = workflows.save_workflow(ws.flows, raw, abilities.steps(),
                                        skills=abilities.skill_names())
    except (workflows.WorkflowInvalid, FileExistsError) as exc:
        print(str(exc), file=sys.stderr)
        return EXIT_INVALID
    print(f"ok {taken.name}\tflows/{taken.name}.yaml\t{len(taken.stages)} 项"
          f"\tnext=按需要改它的阶段、能力参数或断点，ai4sci show flows 校验；然后从第一项开始走")
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


def cmd_remove_workflow(args: argparse.Namespace) -> int:
    """删库里人自己存的一条流程；出厂的拒。"""
    try:
        workflows.remove_workflow(paths.workflows_root(), args.name)
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

    library = groups.add_parser("workflow", help="流程库：库里的流程文件（workflows/*.yaml）")
    library_actions = library.add_subparsers(dest="action", required=True)
    dropping = library_actions.add_parser("remove", help="删库里人自己存的一条流程；出厂的不能删")
    dropping.add_argument("name", help="流程名（文件名去掉 .yaml）")
    dropping.set_defaults(func=cmd_remove_workflow)
