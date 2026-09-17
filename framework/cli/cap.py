"""`ai4sci cap <name> <run_id 或 task_dir>`：按名字跑一个能力的通用驱动（纲领 P-10、P-12）。

在 cli 层。每个能力的子命令是从它的描述符**生成**的：位置参数按 level 定（run 级是 run_id，
task 级是任务包目录），`--backend` 只在 needs_executor 时有，`--compute` 只在 needs_compute
时有，每个 `Param` 变成一个选项——所以"CLI 参数与描述符一致"是构造保证，不靠人对。
跑完即退，用退出码表态；能力之间怎么串是协调层的事，这里没有顺序。

`--detach` 是每颗按钮都有的开关（外层 #63）：把去掉它的同一条命令起成独立进程当作业，立刻打印
作业号退出；子进程跑完把结论行回写进作业记录，作业属于某段对话的就去叫醒它（chat.notify）。
这里是作业唯一的起点与终点，能力自己不知道自己是不是作业。
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from framework.capabilities import discover
from framework.chat import notify
from framework.cli._common import (
    EXIT_INVALID,
    EXIT_OK,
    EXIT_USAGE,
    add_runs_root,
    open_run_dir,
    resolve_ports,
    runs_root,
    setup_logging,
)
from framework.contracts.capability import PARAM_TYPES, Capability, CapabilityFailed, Ports
from framework.contracts.publish import NotPublished
from framework.run import flow_state, jobs
from framework.run.context import TaskInvalid


def cmd_cap(args: argparse.Namespace) -> int:
    descriptor = args.module.DESCRIPTOR
    if descriptor.level == "task":
        target = Path(args.task_dir)
        if not descriptor.creates_target and not target.is_dir():
            print(f"任务目录不存在：{target}", file=sys.stderr)
            return EXIT_USAGE
    else:
        target = open_run_dir(args)
        if isinstance(target, int):
            return target
    ports = resolve_ports(getattr(args, "backend", None), getattr(args, "compute", None))
    if isinstance(ports, int):
        return ports
    job_id = os.environ.get(jobs.JOB_ID_ENV)
    if args.detach:
        if job_id:
            print(f"已经在作业 {job_id} 里了，作业里不能再 --detach", file=sys.stderr)
            return EXIT_USAGE
        return _detach(args, descriptor.name, descriptor.level, target)
    setup_logging()
    code, line = _run(args, descriptor, target, ports)
    print(line, file=sys.stdout if code == EXIT_OK else sys.stderr)
    if code == EXIT_OK and descriptor.level == "run":
        flow_state.record_press(target, descriptor.name)  # 记它落在流的第几步；没照流就不记
    if job_id:
        job = jobs.finish(runs_root(args), job_id, exit_code=code, result=line)
        if job.chat_id:
            # 作业是某段对话里按的：跑完以框架的身份叫醒那段对话，结果记回作业
            jobs.mark_wake(runs_root(args), job_id, notify.wake(runs_root(args), job))
    return code


def _run(args: argparse.Namespace, descriptor: Capability, target: Path,
         ports: Ports) -> tuple[int, str]:
    """跑一颗能力：退出码与那一行话（成功是结论行，失败是能力自己说的那一句，P-7）。"""
    params = {p.name: getattr(args, p.name) for p in descriptor.params}
    try:
        return EXIT_OK, args.module.run(target, ports, **params)
    except (CapabilityFailed, NotPublished, TaskInvalid) as exc:
        return EXIT_INVALID, str(exc)


def _detach(args: argparse.Namespace, name: str, level: str, target: Path) -> int:
    argv = [a for a in args.argv if a != "--detach"]
    job = jobs.spawn(runs_root(args), argv, cap=name, level=level,
                     target=args.run_id if level != "task" else str(target),
                     chat_id=os.environ.get(jobs.CHAT_ID_ENV))
    print(f"job {job.job_id}\tcap={name}\ttarget={job.target}\tpid={job.pid}"
          f"\tnext=ai4sci show job {job.job_id}")
    return EXIT_OK


def add_parser(groups: argparse._SubParsersAction) -> None:
    cap = groups.add_parser("cap", help="按名字跑一个能力，跑完即退（清单：ai4sci show caps）")
    actions = cap.add_subparsers(dest="name", required=True)
    for name, module in discover().items():
        descriptor = module.DESCRIPTOR
        sub = actions.add_parser(name, help=descriptor.summary)
        if descriptor.level == "task":
            sub.add_argument("task_dir", help="要新建的任务包目录" if descriptor.creates_target
                             else "任务包目录")
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
        sub.add_argument("--detach", action="store_true",
                         help="起成后台作业，立刻打印作业号；进度看 ai4sci show job <作业号>")
        sub.set_defaults(func=cmd_cap, module=module)
