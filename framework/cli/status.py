"""`ai4sci status`：协调层读盘的入口。

在 cli 层，只读 run 的 checkpoint 与账本，不碰能力：看一眼状态不该把内环也拖起来。
"""

from __future__ import annotations

import argparse
import sys

from framework.cli._common import EXIT_INVALID, EXIT_OK, EXIT_USAGE, add_runs_root, runs_root
from framework.memory import ledger
from framework.run import layout
from framework.run.checkpoint import read_checkpoint


def cmd_status(args: argparse.Namespace) -> int:
    """打印 best、账本尾部、停止原因，一屏看完。"""
    run_dir = runs_root(args) / args.run_id
    if not layout.checkpoint(run_dir).is_file():
        print(f"run 不存在或没有 checkpoint：{run_dir}", file=sys.stderr)
        return EXIT_USAGE
    state = read_checkpoint(run_dir)
    print(f"run_id\t{state['run_id']}")
    print(f"last_iter\t{state['last_iter']}")
    print(f"best_iter\t{state['best_iter']}")
    print(f"best_metric\t{state['best_metric']}")
    print(f"best_commit\t{state['best_commit']}")
    print(f"stop_reason\t{state.get('stop_reason') or '-'}")
    ledger_path = layout.ledger(run_dir)
    rows = ledger.read(ledger_path)
    print(f"ledger_rows\t{len(rows)}")
    for row in rows[-args.tail:]:
        metric = "-" if row.metric is None else f"{row.metric:.6g}"
        print(f"{row.iter}\t{row.status}\t{metric}\t{row.commit[:12]}\t{row.note}")
    # 账本 × git 的对账放在 status 里跑：不对账的状态只是"它自己说它没事"（P-3）
    problems = ledger.reconcile(ledger_path, layout.work(run_dir))
    if problems:
        for problem in problems:
            print(problem, file=sys.stderr)
        return EXIT_INVALID
    return EXIT_OK


def add_parser(groups: argparse._SubParsersAction) -> None:
    status = groups.add_parser("status", help="打印 best、账本尾部与停止原因")
    status.add_argument("run_id")
    status.add_argument("--tail", type=int, default=5, help="账本尾部行数，缺省 5")
    add_runs_root(status)
    status.set_defaults(func=cmd_status)
