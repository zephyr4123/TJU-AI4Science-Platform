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
from framework.capabilities import discover
from framework.cli._common import EXIT_INVALID, EXIT_OK, EXIT_USAGE, current_workspace
from framework.contracts import workflows


def cmd_take(args: argparse.Namespace) -> int:
    ws = current_workspace()
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
    catalog = {cap: module.DESCRIPTOR for cap, module in discover().items()}
    try:
        taken = workflows.save_workflow(ws.flows, raw, catalog)
    except (workflows.WorkflowInvalid, FileExistsError) as exc:
        print(str(exc), file=sys.stderr)
        return EXIT_INVALID
    print(f"ok {taken.name}\tflows/{taken.name}.yaml\t{len(taken.stages)} 项"
          f"\tnext=按需要改它的阶段、能力参数或断点，ai4sci show flows 校验；然后从第一项开始走")
    return EXIT_OK


def add_parser(groups: argparse._SubParsersAction) -> None:
    flow = groups.add_parser("flow", help="流程实例：把库里的流程取到当前工作区")
    actions = flow.add_subparsers(dest="action", required=True)
    taking = actions.add_parser(
        "take", help="取一条：复制库里的 workflows/<name>.yaml 成 flows/<name>.yaml")
    taking.add_argument("name", help="库里的流程名（ai4sci show workflows）")
    taking.add_argument("--as", dest="as_name", default="", help="实例换个名字，缺省同名")
    taking.set_defaults(func=cmd_take)
