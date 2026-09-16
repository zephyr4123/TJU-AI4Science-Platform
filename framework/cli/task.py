"""`ai4sci task validate|list|env build|design`：任务包这一侧的驱动面。

在 cli 层。校验、列表、建环境只调 contracts；`design` 是接任务时协调 agent 按的那个按钮，
它要执行层端口，所以还调 executor（`executor.design`）。跑完即退，停点用一行 `next=` 说给
协调层听，要不要按下一步是人的事（P-10）。
"""

from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path

from framework.cli._common import (
    EXIT_INVALID,
    EXIT_OK,
    EXIT_USAGE,
    add_runs_root,
    resolve_ports,
    runs_root,
    setup_logging,
)
from framework.contracts import env, packs
from framework.executor.design import BRIEF_NAME, DesignFailed, design_task

# framework/cli/ 往上两级就是仓根，`task list` 不给 --root 时按它兜底。
REPO_ROOT = Path(__file__).resolve().parents[2]
DOMAINS_DIRNAME = "domains"


def _default_domains_root(task_dir: Path) -> Path:
    """缺省领域根：<task_dir>/../../domains，即任务包同一个仓里的 domains/。"""
    return task_dir.resolve().parent.parent / DOMAINS_DIRNAME


def cmd_validate(args: argparse.Namespace) -> int:
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


def cmd_list(args: argparse.Namespace) -> int:
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


def cmd_env_build(args: argparse.Namespace) -> int:
    """按 env/ 建 <task_dir>/.venv，给 make_run0.sh 与人手工跑用；run 有自己的一份。"""
    task_dir = Path(args.task_dir)
    if not task_dir.is_dir():
        print(f"任务目录不存在：{task_dir}", file=sys.stderr)
        return EXIT_USAGE
    try:
        python = env.build_venv(task_dir, task_dir / env.VENV_DIRNAME)
    except env.EnvBuildError as exc:
        print(str(exc), file=sys.stderr)
        return EXIT_INVALID
    print(f"ok {python}")
    return EXIT_OK


def cmd_design(args: argparse.Namespace) -> int:
    """接任务的按钮：执行层写草稿 → 框架封 harness、ruff、validate（不查 run_0）→ 停。"""
    task_dir = Path(args.task_dir)
    if not task_dir.is_dir():
        print(f"任务目录不存在：{task_dir}", file=sys.stderr)
        return EXIT_USAGE
    domains_root = Path(args.domains) if args.domains else _default_domains_root(task_dir)
    feedback = args.feedback or ""
    if feedback.startswith("@"):
        path = Path(feedback[1:])
        if not path.is_file():
            print(f"--feedback 指的文件不存在：{path}", file=sys.stderr)
            return EXIT_USAGE
        feedback = path.read_text(encoding="utf-8")
    ports = resolve_ports(args.backend, None)
    if isinstance(ports, int):
        return ports
    setup_logging()
    try:
        outcome = design_task(task_dir, domains_root, ports.runner, runs_root(args),
                              feedback=feedback)
    except DesignFailed as exc:
        print(str(exc), file=sys.stderr)
        return EXIT_INVALID
    for problem in outcome.problems:
        print(problem, file=sys.stderr)
    cost = "nan" if math.isnan(outcome.cost_usd) else f"{outcome.cost_usd:.4f}"
    if outcome.problems:
        status = "draft"
        nxt = f"把 stderr 的问题喂回：ai4sci task design {task_dir} --feedback @<文件>"
    else:
        status = "ok"
        nxt = "人签 harness/evaluate.py → bash harness/make_run0.sh → ai4sci task validate"
    print(f"design {status}\tsession={outcome.session}\tchanged={len(outcome.changed_files)}"
          f"\tsealed={','.join(outcome.sealed) or '-'}\tlint={len(outcome.lint_problems)}"
          f"\tvalidate={len(outcome.validate_problems)}\tcost_usd={cost}\tlog={outcome.log_dir}"
          f"\tnext={nxt}")
    return EXIT_INVALID if outcome.problems else EXIT_OK


def add_parser(groups: argparse._SubParsersAction) -> None:
    task = groups.add_parser("task", help="任务包相关")
    actions = task.add_subparsers(dest="action", required=True)

    validate = actions.add_parser("validate", help="校验一个任务包是否合契约")
    validate.add_argument("task_dir", help="任务包目录")
    validate.add_argument(
        "--domains", default=None, help="领域包根目录，缺省 <task_dir>/../../domains"
    )
    validate.set_defaults(func=cmd_validate)

    listing = actions.add_parser("list", help="列出搜索路径下的任务包")
    listing.add_argument("--root", default=None, help="仓根或 tasks/ 目录，缺省为本仓根")
    listing.set_defaults(func=cmd_list)

    environment = actions.add_parser("env", help="任务环境相关")
    env_actions = environment.add_subparsers(dest="env_action", required=True)
    building = env_actions.add_parser("build", help="按 env/ 建 <task_dir>/.venv（uv）")
    building.add_argument("task_dir", help="任务包目录")
    building.set_defaults(func=cmd_env_build)

    designing = actions.add_parser(
        "design", help="起执行层给任务包写 harness 与基线草稿，封 harness、ruff、校验，然后停"
    )
    designing.add_argument("task_dir", help=f"任务包目录，要先有 manifest.yaml 与 {BRIEF_NAME}")
    designing.add_argument(
        "--domains", default=None, help="领域包根目录，缺省 <task_dir>/../../domains"
    )
    designing.add_argument("--backend", default="claude_code", help="执行层后端名")
    designing.add_argument(
        "--feedback", default="", help="喂回执行层的修改意见（改第二版）；写 @<文件> 就读那个文件"
    )
    add_runs_root(designing)
    designing.set_defaults(func=cmd_design)
