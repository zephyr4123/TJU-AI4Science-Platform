"""`ai4sci` 命令行：协调层驱动框架的唯一入口（workflow.md §5）。

每条子命令只干一件事、跑完就退，用退出码表态，不常驻、不等人（P-10）：

    0  通过
    1  没通过（问题一行一条打到 stderr）
    2  用法错误：目录不存在、发现阶段的拓扑冲突
"""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import UTC, datetime
from pathlib import Path

from backends import BackendNotFound, get_backend
from compute import ComputeNotFound, get_compute
from framework import ledger, loop, packs

EXIT_OK = 0
EXIT_INVALID = 1
EXIT_USAGE = 2

# framework/ 的上一级就是仓根，`task list` 不给 --root 时按它兜底。
REPO_ROOT = Path(__file__).resolve().parent.parent
DOMAINS_DIRNAME = "domains"


def _default_domains_root(task_dir: Path) -> Path:
    """缺省领域根：<task_dir>/../../domains，即任务包同一个仓里的 domains/。"""
    return task_dir.resolve().parent.parent / DOMAINS_DIRNAME


def _cmd_task_validate(args: argparse.Namespace) -> int:
    task_dir = Path(args.task_dir)
    if not task_dir.is_dir():
        print(f"任务目录不存在：{task_dir}", file=sys.stderr)
        return EXIT_USAGE
    domains_root = Path(args.domains) if args.domains else _default_domains_root(task_dir)
    problems = packs.validate_task(task_dir, domains_root)
    if problems:
        for problem in problems:
            print(problem, file=sys.stderr)
        return EXIT_INVALID
    # 校验通过意味着 manifest.id 已经和目录名对上，这里可以直接拿目录名当 id。
    print(f"ok {task_dir.resolve().name}")
    return EXIT_OK


def _cmd_task_list(args: argparse.Namespace) -> int:
    root = Path(args.root) if args.root else REPO_ROOT
    if not root.is_dir():
        print(f"搜索路径不存在：{root}", file=sys.stderr)
        return EXIT_USAGE
    try:
        found = packs.discover_tasks(root)
    except (ValueError, NotADirectoryError) as exc:
        # 发现阶段的冲突是拓扑错误：报清楚并退非零，不静默跳过坏包（P-7）。
        print(str(exc), file=sys.stderr)
        return EXIT_USAGE
    for task_id in sorted(found):
        print(f"{task_id}\t{found[task_id]}")
    return EXIT_OK


# ── run / loop / status：实验内环的驱动面（workflow.md §5）──────────────
def _setup_logging() -> None:
    """内环每轮一条结构化 info 走 stderr；stdout 只留给给协调层读的结论。"""
    logging.basicConfig(level=logging.INFO, stream=sys.stderr,
                        format="%(asctime)s %(name)s %(message)s")


def _runs_root(args: argparse.Namespace) -> Path:
    return Path(args.runs_root) if getattr(args, "runs_root", None) else loop.default_runs_root()


def _cmd_run_new(args: argparse.Namespace) -> int:
    task_dir = Path(args.task_dir)
    if not task_dir.is_dir():
        print(f"任务目录不存在：{task_dir}", file=sys.stderr)
        return EXIT_USAGE
    run_id = args.run_id or f"{task_dir.resolve().name}-{datetime.now(UTC):%Y%m%dT%H%M%SZ}"
    try:
        run_dir = loop.new_run(task_dir, _runs_root(args), run_id)
    except loop.TaskInvalid as exc:
        # 校验不过就停在门口，绝不建一个注定跑不出结果的 run（P-7）
        print(str(exc), file=sys.stderr)
        return EXIT_INVALID
    except FileExistsError as exc:
        print(str(exc), file=sys.stderr)
        return EXIT_USAGE
    print(f"ok {run_id}\t{run_dir}")
    return EXIT_OK


def _cmd_run_extend(args: argparse.Namespace) -> int:
    run_dir = _runs_root(args) / args.run_id
    if not (run_dir / "checkpoint.json").is_file():
        print(f"run 不存在或没有 checkpoint：{run_dir}", file=sys.stderr)
        return EXIT_USAGE
    if args.patience is None and args.max_iterations is None and args.max_cost_usd is None:
        print("至少给一项：--patience / --max-iterations / --max-cost-usd", file=sys.stderr)
        return EXIT_USAGE
    _setup_logging()
    done = loop.extend_run(run_dir, patience=args.patience, max_iterations=args.max_iterations,
                           max_cost_usd=args.max_cost_usd, reason=args.reason)
    print(f"ok {args.run_id}\tcleared={done['cleared']}\t{'；'.join(done['changes'])}")
    return EXIT_OK


def _open_run(args: argparse.Namespace) -> tuple[Path, object, object] | int:
    run_dir = _runs_root(args) / args.run_id
    if not (run_dir / "checkpoint.json").is_file():
        print(f"run 不存在或没有 checkpoint：{run_dir}", file=sys.stderr)
        return EXIT_USAGE
    try:
        return run_dir, get_backend(args.backend), get_compute(args.compute)
    except (BackendNotFound, ComputeNotFound) as exc:
        # 名字对不上就报错退出，绝不静默回退到某个默认后端（纲领 §5）
        print(str(exc), file=sys.stderr)
        return EXIT_USAGE


def _cmd_loop(args: argparse.Namespace) -> int:
    opened = _open_run(args)
    if isinstance(opened, int):
        return opened
    run_dir, runner, compute = opened
    _setup_logging()
    go = loop.resume_loop if args.action == "resume" else loop.run_loop
    try:
        stop = go(run_dir, runner, compute, args.max_iters)
    except (loop.ResumeMismatch, loop.InflightPending, loop.TaskInvalid) as exc:
        # 三者都是"现状不允许往下跑"：把那句话原样给协调层，别留半个栈让人猜（P-7）
        print(str(exc), file=sys.stderr)
        return EXIT_INVALID
    print(f"stop {stop.reason}\titer={stop.iter}\tbest={stop.best_metric}")
    return EXIT_OK


def _cmd_status(args: argparse.Namespace) -> int:
    """协调层读盘的入口：best、账本尾部、停止原因，一屏看完。"""
    run_dir = _runs_root(args) / args.run_id
    if not (run_dir / "checkpoint.json").is_file():
        print(f"run 不存在或没有 checkpoint：{run_dir}", file=sys.stderr)
        return EXIT_USAGE
    state = loop.read_checkpoint(run_dir)
    print(f"run_id\t{state['run_id']}")
    print(f"last_iter\t{state['last_iter']}")
    print(f"best_iter\t{state['best_iter']}")
    print(f"best_metric\t{state['best_metric']}")
    print(f"best_commit\t{state['best_commit']}")
    print(f"stop_reason\t{state.get('stop_reason') or '-'}")
    ledger_path = run_dir / "experiment" / "ledger.tsv"
    rows = ledger.read(ledger_path)
    print(f"ledger_rows\t{len(rows)}")
    for row in rows[-args.tail:]:
        metric = "-" if row.metric is None else f"{row.metric:.6g}"
        print(f"{row.iter}\t{row.status}\t{metric}\t{row.commit[:12]}\t{row.note}")
    # 账本 × git 的对账放在 status 里跑：不对账的状态只是"它自己说它没事"（P-3）
    problems = ledger.reconcile(ledger_path, run_dir / "work")
    if problems:
        for problem in problems:
            print(problem, file=sys.stderr)
        return EXIT_INVALID
    return EXIT_OK


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="ai4sci", description="TJU AI for Science 平台 CLI")
    groups = parser.add_subparsers(dest="group", required=True)

    task = groups.add_parser("task", help="任务包相关")
    task_actions = task.add_subparsers(dest="action", required=True)

    validate = task_actions.add_parser("validate", help="校验一个任务包是否合契约")
    validate.add_argument("task_dir", help="任务包目录")
    validate.add_argument(
        "--domains", default=None, help="领域包根目录，缺省 <task_dir>/../../domains"
    )
    validate.set_defaults(func=_cmd_task_validate)

    listing = task_actions.add_parser("list", help="列出搜索路径下的任务包")
    listing.add_argument("--root", default=None, help="仓根或 tasks/ 目录，缺省为本仓根")
    listing.set_defaults(func=_cmd_task_list)

    run = groups.add_parser("run", help="run 目录相关")
    run_actions = run.add_subparsers(dest="action", required=True)
    creating = run_actions.add_parser("new", help="按任务包建一个 run")
    creating.add_argument("task_dir", help="任务包目录")
    creating.add_argument("--run-id", default=None, help="缺省 <任务名>-<UTC 时间戳>")
    _add_runs_root(creating)
    creating.set_defaults(func=_cmd_run_new)
    extending = run_actions.add_parser("extend", help="给已停的 run 续命：改预算、清停止标记")
    extending.add_argument("run_id")
    extending.add_argument("--patience", type=int, default=None, help="连续不改进几轮才停")
    extending.add_argument("--max-iterations", type=int, default=None, help="总轮数上限")
    extending.add_argument("--max-cost-usd", type=float, default=None, help="总花费上限")
    extending.add_argument("--reason", default="", help="为什么续命，记进 journal.md")
    _add_runs_root(extending)
    extending.set_defaults(func=_cmd_run_extend)

    loop_group = groups.add_parser("loop", help="实验内环")
    loop_actions = loop_group.add_subparsers(dest="action", required=True)
    for action, help_text in (("run", "跑内环，到停止条件即退"),
                              ("resume", "从 checkpoint 与账本续跑")):
        sub = loop_actions.add_parser(action, help=help_text)
        sub.add_argument("run_id")
        sub.add_argument("--backend", default="claude_code", help="执行层后端名")
        sub.add_argument("--compute", default="local", help="算力后端名")
        sub.add_argument("--max-iters", type=int, default=None,
                         help="本次增量最多跑几轮（上限仍是 manifest 的 budget.max_iterations；"
                              "配额用完只是这一批跑完，run 不会被判停，再跑一次接着往下）")
        _add_runs_root(sub)
        sub.set_defaults(func=_cmd_loop)

    status = groups.add_parser("status", help="打印 best、账本尾部与停止原因")
    status.add_argument("run_id")
    status.add_argument("--tail", type=int, default=5, help="账本尾部行数，缺省 5")
    _add_runs_root(status)
    status.set_defaults(func=_cmd_status)

    return parser


def _add_runs_root(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--runs-root", default=None,
                        help="runs 根目录，缺省读环境变量 AI4SCI_RUNS_ROOT，再缺省 <仓根>/runs")


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    sys.exit(main())
