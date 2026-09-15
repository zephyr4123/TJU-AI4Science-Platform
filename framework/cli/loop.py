"""`ai4sci loop run|resume`：驱动实验内环这个能力。

在 cli 层：能力跑完即退，CLI 只负责把端口（backend / compute）按名字取出来注入进去，
并把"现状不允许往下跑"的三种异常翻成退出码 1（P-7、P-10）。
"""

from __future__ import annotations

import argparse
import sys

from framework.capabilities import experiment
from framework.cli._common import (
    EXIT_INVALID,
    EXIT_OK,
    add_runs_root,
    open_run_dir,
    resolve_ports,
    setup_logging,
)
from framework.run.context import TaskInvalid


def cmd_loop(args: argparse.Namespace) -> int:
    run_dir = open_run_dir(args)
    if isinstance(run_dir, int):
        return run_dir
    ports = resolve_ports(args.backend, args.compute)
    if isinstance(ports, int):
        return ports
    setup_logging()
    go = experiment.resume_loop if args.action == "resume" else experiment.run_loop
    try:
        stop = go(run_dir, ports.runner, ports.compute, args.max_iters)
    except (experiment.ResumeMismatch, experiment.InflightPending, TaskInvalid) as exc:
        # 三者都是"现状不允许往下跑"：把那句话原样给协调层，别留半个栈让人猜（P-7）
        print(str(exc), file=sys.stderr)
        return EXIT_INVALID
    print(f"stop {stop.reason}\titer={stop.iter}\tbest={stop.best_metric}")
    return EXIT_OK


def add_parser(groups: argparse._SubParsersAction) -> None:
    group = groups.add_parser("loop", help="实验内环")
    actions = group.add_subparsers(dest="action", required=True)
    for action, help_text in (("run", "跑内环，到停止条件即退"),
                              ("resume", "从 checkpoint 与账本续跑")):
        sub = actions.add_parser(action, help=help_text)
        sub.add_argument("run_id")
        sub.add_argument("--backend", default="claude_code", help="执行层后端名")
        sub.add_argument("--compute", default="local", help="算力后端名")
        sub.add_argument("--max-iters", type=int, default=None,
                         help="本次增量最多跑几轮（上限仍是 manifest 的 budget.max_iterations；"
                              "配额用完只是这一批跑完，run 不会被判停，再跑一次接着往下）")
        add_runs_root(sub)
        sub.set_defaults(func=cmd_loop)
