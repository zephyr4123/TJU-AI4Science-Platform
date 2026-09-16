"""`ai4sci cap <name> <run_id 或 task_dir>`：按名字跑一个能力的通用驱动（纲领 P-10、P-12）。

在 cli 层。每个能力的子命令是从它的描述符**生成**的：位置参数按 level 定（run 级是 run_id，
task 级是任务包目录），`--backend` 只在 needs_executor 时有，`--compute` 只在 needs_compute
时有，每个 `Param` 变成一个选项——所以"CLI 参数与描述符一致"是构造保证，不靠人对。
跑完即退，用退出码表态；能力之间怎么串是协调层的事，这里没有顺序。
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from framework.capabilities import discover
from framework.cli._common import (
    EXIT_INVALID,
    EXIT_OK,
    EXIT_USAGE,
    add_runs_root,
    open_run_dir,
    resolve_ports,
    setup_logging,
)
from framework.contracts.capability import PARAM_TYPES, CapabilityFailed
from framework.contracts.publish import NotPublished
from framework.run.context import TaskInvalid


def cmd_cap(args: argparse.Namespace) -> int:
    descriptor = args.module.DESCRIPTOR
    if descriptor.level == "task":
        target = Path(args.task_dir)
        if not target.is_dir():
            print(f"任务目录不存在：{target}", file=sys.stderr)
            return EXIT_USAGE
    else:
        target = open_run_dir(args)
        if isinstance(target, int):
            return target
    ports = resolve_ports(getattr(args, "backend", None), getattr(args, "compute", None))
    if isinstance(ports, int):
        return ports
    params = {p.name: getattr(args, p.name) for p in descriptor.params}
    setup_logging()
    try:
        line = args.module.run(target, ports, **params)
    except (CapabilityFailed, NotPublished, TaskInvalid) as exc:
        # 能力自己说的那句话原样给协调层，别留半个栈让人猜（P-7）
        print(str(exc), file=sys.stderr)
        return EXIT_INVALID
    print(line)
    return EXIT_OK


def add_parser(groups: argparse._SubParsersAction) -> None:
    cap = groups.add_parser("cap", help="按名字跑一个能力，跑完即退（清单：ai4sci show caps）")
    actions = cap.add_subparsers(dest="name", required=True)
    for name, module in discover().items():
        descriptor = module.DESCRIPTOR
        sub = actions.add_parser(name, help=descriptor.summary)
        if descriptor.level == "task":
            sub.add_argument("task_dir", help="任务包目录")
        else:
            sub.add_argument("run_id")
        if descriptor.needs_executor:
            sub.add_argument("--backend", default="claude_code", help="执行层后端名")
        if descriptor.needs_compute:
            sub.add_argument("--compute", default="local", help="算力后端名")
        for param in descriptor.params:
            # argparse 把 help 当 % 格式串：描述符里写"1%"是给人看的，这里得转义
            flag, help_text = f"--{param.name.replace('_', '-')}", param.help.replace("%", "%%")
            if param.type == "bool":
                sub.add_argument(flag, dest=param.name, action="store_true", help=help_text)
            else:
                sub.add_argument(flag, dest=param.name, type=PARAM_TYPES[param.type],
                                 default=param.default, help=help_text)
        if descriptor.level != "task":
            add_runs_root(sub)
        sub.set_defaults(func=cmd_cap, module=module)
