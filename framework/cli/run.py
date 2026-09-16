"""`ai4sci run new|extend|accept`：建 run、给已停的 run 续命、验收结果。

在 cli 层，调的是 `framework.run.lifecycle`——建 run 不需要惊动任何能力。
"""

from __future__ import annotations

import argparse
import getpass
import sys
from datetime import UTC, datetime
from pathlib import Path

from framework.cli._common import (
    EXIT_INVALID,
    EXIT_OK,
    EXIT_USAGE,
    add_runs_root,
    open_run_dir,
    runs_root,
    setup_logging,
)
from framework.run.accept import AcceptRefused, accept_run
from framework.run.lifecycle import (
    EnvBuildError,
    NotPublished,
    TaskInvalid,
    extend_run,
    new_run,
)


def cmd_new(args: argparse.Namespace) -> int:
    task_dir = Path(args.task_dir)
    if not task_dir.is_dir():
        print(f"任务目录不存在：{task_dir}", file=sys.stderr)
        return EXIT_USAGE
    run_id = args.run_id or f"{task_dir.resolve().name}-{datetime.now(UTC):%Y%m%dT%H%M%SZ}"
    try:
        run_dir = new_run(task_dir, runs_root(args), run_id)
    except (NotPublished, TaskInvalid, EnvBuildError) as exc:
        # 没发布、校验不过、预检没过、环境建不出来都停在门口，绝不留一个注定跑不出结果的 run（P-7）
        print(str(exc), file=sys.stderr)
        return EXIT_INVALID
    except FileExistsError as exc:
        print(str(exc), file=sys.stderr)
        return EXIT_USAGE
    print(f"ok {run_id}\t{run_dir}")
    return EXIT_OK


def cmd_extend(args: argparse.Namespace) -> int:
    run_dir = runs_root(args) / args.run_id
    if not (run_dir / "checkpoint.json").is_file():
        print(f"run 不存在或没有 checkpoint：{run_dir}", file=sys.stderr)
        return EXIT_USAGE
    if args.patience is None and args.max_iterations is None and args.max_cost_usd is None:
        print("至少给一项：--patience / --max-iterations / --max-cost-usd", file=sys.stderr)
        return EXIT_USAGE
    setup_logging()
    done = extend_run(run_dir, patience=args.patience, max_iterations=args.max_iterations,
                      max_cost_usd=args.max_cost_usd, reason=args.reason)
    print(f"ok {args.run_id}\tcleared={done['cleared']}\t{'；'.join(done['changes'])}")
    return EXIT_OK


def cmd_accept(args: argparse.Namespace) -> int:
    """结果验收的键：签 best 与验证结论，写 accept.json。人按的；协调 agent 不该替人按。"""
    run_dir = open_run_dir(args)
    if isinstance(run_dir, int):
        return run_dir
    try:
        record = accept_run(run_dir, by=args.by)
    except AcceptRefused as exc:
        print(str(exc), file=sys.stderr)
        return EXIT_INVALID
    print(f"ok {args.run_id}\tby={record['by']}\tbest_iter={record['best_iter']}"
          f"\tbest_metric={record['best_metric']}\tverify={record['verify'] or '-'}")
    return EXIT_OK


def add_parser(groups: argparse._SubParsersAction) -> None:
    run = groups.add_parser("run", help="run 目录相关")
    actions = run.add_subparsers(dest="action", required=True)

    creating = actions.add_parser("new", help="按任务包建一个 run")
    creating.add_argument("task_dir", help="任务包目录")
    creating.add_argument("--run-id", default=None, help="缺省 <任务名>-<UTC 时间戳>")
    add_runs_root(creating)
    creating.set_defaults(func=cmd_new)

    extending = actions.add_parser("extend", help="给已停的 run 续命：改预算、清停止标记")
    extending.add_argument("run_id")
    extending.add_argument("--patience", type=int, default=None, help="连续不改进几轮才停")
    extending.add_argument("--max-iterations", type=int, default=None, help="总轮数上限")
    extending.add_argument("--max-cost-usd", type=float, default=None, help="总花费上限")
    extending.add_argument("--reason", default="", help="为什么续命，记进 journal.md")
    add_runs_root(extending)
    extending.set_defaults(func=cmd_extend)

    accepting = actions.add_parser(
        "accept", help="验收结果：人看过 best、分析与验证后按；写 accept.json，签 best 与验证结论")
    accepting.add_argument("run_id")
    accepting.add_argument("--by", default=getpass.getuser(),
                           help="谁验收的，记在记录上；缺省当前登录名")
    add_runs_root(accepting)
    accepting.set_defaults(func=cmd_accept)
