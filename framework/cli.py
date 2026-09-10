"""`ai4sci` 命令行：协调层驱动框架的唯一入口（workflow.md §5）。

每条子命令只干一件事、跑完就退，用退出码表态，不常驻、不等人（P-10）：

    0  通过
    1  没通过（问题一行一条打到 stderr）
    2  用法错误：目录不存在、发现阶段的拓扑冲突
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from framework import packs

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

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    sys.exit(main())
