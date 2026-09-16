"""`ai4sci task validate|list|env build|publish`：任务包这一侧的驱动面。

在 cli 层，只调 contracts。接任务与跑基线两个按钮是 task 级能力，走 `ai4sci cap design|baseline`
（子命令从描述符生成），不在这里。`publish` 是需求看板上那颗键：人按的，协调 agent 不该替人按。
"""

from __future__ import annotations

import argparse
import getpass
import sys
from pathlib import Path

from framework.cli._common import EXIT_INVALID, EXIT_OK, EXIT_USAGE
from framework.contracts import env, packs, publish

# framework/cli/ 往上两级就是仓根，`task list` 不给 --root 时按它兜底。
REPO_ROOT = Path(__file__).resolve().parents[2]


def cmd_validate(args: argparse.Namespace) -> int:
    task_dir = Path(args.task_dir)
    if not task_dir.is_dir():
        print(f"任务目录不存在：{task_dir}", file=sys.stderr)
        return EXIT_USAGE
    domains_root = Path(args.domains) if args.domains else packs.default_domains_root(task_dir)
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


def cmd_publish(args: argparse.Namespace) -> int:
    """需求看板的发布键：签 manifest.yaml 与 design.md，写 publish.json；后面的按钮都查它。"""
    task_dir = Path(args.task_dir)
    if not task_dir.is_dir():
        print(f"任务目录不存在：{task_dir}", file=sys.stderr)
        return EXIT_USAGE
    try:
        record = publish.publish_task(task_dir, by=args.by)
    except publish.PublishRefused as exc:
        print(str(exc), file=sys.stderr)
        return EXIT_INVALID
    print(f"ok {task_dir.resolve().name}\tby={record['by']}\tat={record['published_at']}"
          f"\tnext=ai4sci cap design {task_dir}")
    return EXIT_OK


def add_parser(groups: argparse._SubParsersAction) -> None:
    task = groups.add_parser("task", help="任务包相关")
    actions = task.add_subparsers(dest="action", required=True)

    validate = actions.add_parser("validate", help="校验一个任务包是否合契约")
    validate.add_argument("task_dir", help="任务包目录")
    validate.add_argument(
        "--domains", default=None,
        help=f"领域包根目录，缺省 ${packs.DOMAINS_ROOT_ENV} 或 <task_dir>/../../domains",
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

    publishing = actions.add_parser(
        "publish",
        help="发布需求：人看过 manifest.yaml 与 design.md 后按；写 publish.json，后面的按钮都查它",
    )
    publishing.add_argument("task_dir", help="任务包目录")
    publishing.add_argument("--by", default=getpass.getuser(),
                            help="谁发布的，记在钥匙上；缺省当前登录名")
    publishing.set_defaults(func=cmd_publish)
