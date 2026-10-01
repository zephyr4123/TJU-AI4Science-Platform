"""`ai4sci skill list | show <name> [<文件>] | run <name> [--script <文件>] [参数…]`：工具包
（纲领 P-22）。

在 cli 层。在项目里只认本项目装载的那套（纲领 P-26，`workspace/loadout.py`）：平台自带的加
各工作区流程实例上挂的；装载之外的 show / run 拒，说清先挂到流程上。不在项目里（人在终端、
门禁）看三处库全部。`list` 打清单（名字、出处、一句话——与注入 prompt 的是同一份）；`show`
打正文、目录、目录里的其它文件，带上文件名就打那个文件（参考、模板、`manifest.yaml`：执行层的
读文件工具只放行工作目录，读 skill 目录得经这里）；`run` 起脚本：`uv run --locked`，`--script`
之后的参数原样递给脚本，stdout 与退出码原样透出。执行层的 Bash 白名单只放行这一组子命令
（`framework.skills.EXECUTOR_BASH_RULES`）。

`run` 不解析脚本的输出、不猜路径：写哪里由调用它的 agent 用 `--out` 定（助理 → `materials/`，
能力 → 自己的产出目录）。
"""

from __future__ import annotations

import argparse
import sys

from framework import skills
from framework.capabilities import discover
from framework.cli._common import (
    EXIT_INVALID,
    EXIT_OK,
    EXIT_USAGE,
    add_ws_option,
    current_workspace,
)
from framework.skills import run as runner
from framework.workspace import loadout


def cmd_list(args: argparse.Namespace) -> int:
    loaded = loadout.here()
    if loaded is None:
        found = skills.everything()
        rows = [(s.name, s.where, s.description) for s in found.skills]
        bad = [(i.name, i.problems[0]) for i in found.invalid]
    else:
        rows = [(s.name, s.where, s.description) for s in loaded.skills]
        bad = [*loaded.unavailable, *loaded.strays(discover())]
    for name, where, description in rows:
        print(f"{name}\t{where}\t{description}")
    for name, reason in bad:
        print(f"{name}\t不可用\t{reason}")
    if not rows and not bad:
        print("（一个 skill 都没有）", file=sys.stderr)
    return EXIT_OK


def cmd_show(args: argparse.Namespace) -> int:
    skill = _find(args.name)
    if isinstance(skill, int):
        return skill
    if args.file:
        try:
            print(skill.read(args.file), end="")
        except skills.SkillNotFound as exc:
            print(str(exc), file=sys.stderr)
            return EXIT_USAGE
        return EXIT_OK
    # 不打库在盘上的路径：agent 拿到它就能绕过装载直接读库里别的 skill（Codex 的沙箱读盘不拦）
    print(f"# {skill.name}\t{skill.where}")
    print(f"description: {skill.description}")
    if skill.compatibility:
        print(f"compatibility: {skill.compatibility}")
    for key, value in skill.metadata.items():
        print(f"{key}: {value}")
    if skill.scripts:
        print("scripts: " + ", ".join(p.name for p in skill.scripts))
    files = [f for f in skill.files() if not f.startswith(f"{skills.library.SCRIPTS_DIRNAME}/")]
    if files:
        print("files: " + ", ".join(files)
              + f"（读一个：ai4sci skill show {skill.name} <文件>）")
    print()
    print(skill.body)
    return EXIT_OK


def cmd_run(args: argparse.Namespace) -> int:
    skill = _find(args.name)
    if isinstance(skill, int):
        return skill
    script_args = list(args.script_args)
    picked, script_args = _take(script_args, "--script", args.script, "脚本的文件名")
    ws_name, script_args = _take(script_args, "--ws", args.ws, "工作区的名字")
    if picked is None or ws_name is None:
        return EXIT_USAGE
    try:
        script = runner.pick_script(skill, picked or None)
    except skills.SkillInvalid as exc:
        print(str(exc), file=sys.stderr)
        return EXIT_USAGE
    cwd = None
    if ws_name:
        # 助理站在项目里（纲领 P-15），脚本写的相对路径（materials/…）要落到那个工作区，不是项目：
        # 带 --ws 就在那个工作区里起脚本；不带照当前目录（人在终端 cd 进了工作区、执行层在产出
        # 目录里）
        ws = current_workspace(argparse.Namespace(ws=ws_name))
        if isinstance(ws, int):
            return ws
        cwd = ws.root
    try:
        return runner.run_script(script, script_args, cwd=cwd)
    except runner.UvMissing as exc:
        print(str(exc), file=sys.stderr)
        return EXIT_INVALID


def _take(script_args: list[str], flag: str, given: str | None,
          what: str) -> tuple[str | None, list[str]]:
    """平台自己的选项（`--script`、`--ws`）写在 skill 名后面也认：argparse 把名字后面的全当脚本
    参数，这里摘出第一个、不递给脚本。写在名字前面的由 argparse 收进 `given`。后面没跟值返回
    (None, …)（用法错误）；没写就是 ("", …)。SKILL.md 里一律写 `run <name> --script <文件>`。"""
    if flag not in script_args:
        return given or "", script_args
    at = script_args.index(flag)
    if at + 1 >= len(script_args):
        print(f"{flag} 后面要跟{what}", file=sys.stderr)
        return None, script_args
    return script_args[at + 1], script_args[:at] + script_args[at + 2:]


def _find(name: str):
    """按名字取一个 skill；在项目里只认装载的（纲领 P-26，站在哪见 `loadout.here`）。"""
    loaded = loadout.here()
    if loaded is not None and not loaded.has_skill(name):
        reason = dict([*loaded.unavailable, *loaded.strays(discover())]).get(name)
        print(f"skill {name!r} 挂在流程上，但用不了：{reason}" if reason else
              f"这个项目没有装载 skill {name!r}：要用先挂到工作区流程实例的格子上"
              f"（改 flows/<流程>.yaml，ai4sci show flows 校验）；"
              f"库里有什么用 ai4sci show skills --stage <阶段> <英文词> 查",
              file=sys.stderr)
        return EXIT_INVALID
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
    listing = actions.add_parser("list", help="清单：名字、出处、一句话（在项目里是本项目装载的）")
    listing.set_defaults(func=cmd_list)
    showing = actions.add_parser(
        "show", help="一个 skill 的全文、目录与文件清单；带文件名就打那个文件")
    showing.add_argument("name", help="skill 名（ai4sci skill list）")
    showing.add_argument("file", nargs="?", default="",
                         help="skill 目录里的一个文件（相对路径，如 references/api.md）")
    showing.set_defaults(func=cmd_show)
    running = actions.add_parser(
        "run", help="起 skill 的脚本：uv run --locked，其余参数原样递给脚本")
    running.add_argument("name", help="skill 名")
    running.add_argument("--script", default=None,
                         help="skill 有几个脚本时点名哪一个（文件名）；只有一个时不用给")
    running.add_argument("script_args", nargs=argparse.REMAINDER,
                         help="递给脚本的参数，如 --input x.pdf --out dir")
    add_ws_option(running)  # 在哪个工作区里起脚本（相对路径落在那儿）；写在名字前后都认
    running.set_defaults(func=cmd_run)
