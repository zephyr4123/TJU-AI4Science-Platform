"""`ai4sci skill list | show <name> | run <name> [--script <文件>] [参数…]`：工具包（纲领 P-22）。

在 cli 层。`list` 打清单（名字、库、一句话——与注入 prompt 的是同一份）；`show` 打正文、目录的
绝对路径、scripts/ 与 references/ 清单，agent 照正文里的命令跑；`run` 起脚本：`uv run --locked
--offline`，`--script` 之后的参数原样递给脚本，stdout 与退出码原样透出。两处库合起来按名字找，
名字全局唯一；执行层的 Bash 白名单只放行这一组子命令（`framework.skills.EXECUTOR_BASH_RULES`）。

`run` 不解析脚本的输出、不猜路径：写哪里由调用它的 agent 用 `--out` 定（助理 → `materials/`，
能力 → 自己的产出目录）。
"""

from __future__ import annotations

import argparse
import sys

from framework import skills
from framework.cli._common import EXIT_INVALID, EXIT_OK, EXIT_USAGE
from framework.skills import run as runner


def cmd_list(args: argparse.Namespace) -> int:
    try:
        found = skills.all_skills()
    except skills.SkillInvalid as exc:
        print(str(exc), file=sys.stderr)
        return EXIT_INVALID
    for skill in found:
        print(f"{skill.name}\t{skill.library}\t{skill.description}")
    if not found:
        print("（两处库里都没有 skill）", file=sys.stderr)
    return EXIT_OK


def cmd_show(args: argparse.Namespace) -> int:
    skill = _find(args.name)
    if isinstance(skill, int):
        return skill
    print(f"# {skill.name}\t{skill.library}\t{skill.dir}")
    print(f"description: {skill.description}")
    if skill.compatibility:
        print(f"compatibility: {skill.compatibility}")
    for key, value in skill.metadata.items():
        print(f"{key}: {value}")
    if skill.scripts:
        print("scripts: " + ", ".join(p.name for p in skill.scripts))
    if skill.references:
        print("references: " + ", ".join(p.name for p in skill.references))
    print()
    print(skill.body)
    return EXIT_OK


def cmd_run(args: argparse.Namespace) -> int:
    skill = _find(args.name)
    if isinstance(skill, int):
        return skill
    try:
        script = runner.pick_script(skill, args.script)
    except skills.SkillInvalid as exc:
        print(str(exc), file=sys.stderr)
        return EXIT_USAGE
    try:
        return runner.run_script(script, list(args.script_args))
    except runner.UvMissing as exc:
        print(str(exc), file=sys.stderr)
        return EXIT_INVALID


def _find(name: str):
    try:
        return skills.find(name)
    except skills.SkillNotFound as exc:
        print(str(exc), file=sys.stderr)
        return EXIT_USAGE
    except skills.SkillInvalid as exc:
        print(str(exc), file=sys.stderr)
        return EXIT_INVALID


def add_parser(groups: argparse._SubParsersAction) -> None:
    skill = groups.add_parser("skill", help="工具包：清单、读一个、起它的脚本")
    actions = skill.add_subparsers(dest="action", required=True)
    listing = actions.add_parser("list", help="清单：名字、库、一句话")
    listing.set_defaults(func=cmd_list)
    showing = actions.add_parser("show", help="一个 skill 的全文、目录与脚本清单")
    showing.add_argument("name", help="skill 名（ai4sci skill list）")
    showing.set_defaults(func=cmd_show)
    running = actions.add_parser(
        "run", help="起 skill 的脚本：uv run --locked --offline，其余参数原样递给脚本")
    running.add_argument("name", help="skill 名")
    running.add_argument("--script", default=None,
                         help="skill 有几个脚本时点名哪一个（文件名）；只有一个时不用给")
    running.add_argument("script_args", nargs=argparse.REMAINDER,
                         help="递给脚本的参数，如 --input x.pdf --out dir")
    running.set_defaults(func=cmd_run)
