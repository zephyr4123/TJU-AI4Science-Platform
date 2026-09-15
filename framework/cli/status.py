"""`ai4sci status`：协调层读盘的入口。

在 cli 层，只读 run 的 checkpoint、账本与各能力的产物，不碰能力：看一眼状态不该把内环也拖起来。
"""

from __future__ import annotations

import argparse
import sys

from framework.cli._common import EXIT_INVALID, EXIT_OK, add_runs_root, open_run_dir
from framework.contracts.report import read_report
from framework.memory import ledger
from framework.run import layout
from framework.run.checkpoint import read_checkpoint


def cmd_status(args: argparse.Namespace) -> int:
    """打印 best、账本尾部、停止原因，一屏看完。"""
    run_dir = open_run_dir(args)
    if isinstance(run_dir, int):
        return run_dir
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
    analysis = layout.analysis_doc(run_dir)
    print(f"analysis\t{analysis.relative_to(run_dir) if analysis.is_file() else '-'}")
    report = layout.verify_report(run_dir)
    try:
        print(f"verify\t{read_report(report)['status'] if report.is_file() else '-'}")
    except ValueError as exc:
        # 报告不合约就当没有报告：打出来退 1，别把坏报告的 status 当结论
        print(str(exc), file=sys.stderr)
        return EXIT_INVALID
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
