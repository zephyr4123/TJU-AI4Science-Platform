"""`ai4sci agent list | check <名字> | use <名字> [--for chat|executor] [--model] [--effort]`：
底座（纲领 P-25）。

在 cli 层。清单在按人的 `~/.config/ai4sci/agents.yaml`（`framework.agents`）；
有哪几家是 `backends._BACKENDS`
定的，没有 `add`。`check` 四句人话（装了没 / 版本 / 登录 / 说话）一行一项打出来，不过也只是报告、
记录照留，
退出码说过没过；`use` 换助理或执行层用哪家、改这家新对话用的模型与深度，值要在那家清单上。
助理能跑这几条。
"""

from __future__ import annotations

import argparse
import sys

from backends import BackendNotFound
from framework import agents
from framework.chat import settings
from framework.cli._common import EXIT_INVALID, EXIT_OK, EXIT_USAGE


def cmd_list(args: argparse.Namespace) -> int:
    try:
        registry = agents.load()
    except agents.AgentsInvalid as exc:
        print(str(exc), file=sys.stderr)
        return EXIT_INVALID
    for entry in registry.entries.values():
        roles = [agents.ROLE_LABELS[r] for r in agents.ROLES if registry.role(r) == entry.name]
        print(entry.summary() + ("\t(" + "、".join(roles) + ")" if roles else ""))
    return EXIT_OK


def cmd_check(args: argparse.Namespace) -> int:
    try:
        report = settings.check("agents", args.name)
    except (BackendNotFound, agents.AgentsInvalid) as exc:
        print(str(exc), file=sys.stderr)
        return EXIT_USAGE
    entry = next(e for e in report["agents"]["entries"] if e["name"] == args.name)
    for item in (entry["last_check"] or {}).get("items", []):
        print(f"  {'✓' if item['ok'] else '✗'} {item['name']}\t{item['note']}")
    print(f"ok {args.name}\t{'可用' if report['ok'] else '检查没过'}")
    return EXIT_OK if report["ok"] else EXIT_INVALID


def cmd_use(args: argparse.Namespace) -> int:
    roles = tuple(args.roles or ())
    if not roles and args.model is None and args.effort is None:
        print("要么 --for chat|executor 换用哪家，要么 --model / --effort 改缺省，至少给一样",
              file=sys.stderr)
        return EXIT_USAGE
    try:
        entry = agents.use(args.name, roles=roles, model=args.model, effort=args.effort)
    except (BackendNotFound, agents.AgentsInvalid, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return EXIT_USAGE
    used = "、".join(agents.ROLE_LABELS[r] for r in roles)
    print(f"ok {entry.name}\t{entry.model}\t{entry.effort}" + (f"\t{used}" if used else "")
          + f"\t写入 {agents.path()}")
    return EXIT_OK


def add_parser(groups: argparse._SubParsersAction) -> None:
    group = groups.add_parser("agent", help="底座：有哪几家 coding agent、检查、换用哪家与缺省")
    actions = group.add_subparsers(dest="action", required=True)
    listing = actions.add_parser("list", help="清单：名字、版本、新对话用的模型与深度、上次检查")
    listing.set_defaults(func=cmd_list)
    checking = actions.add_parser("check", help="四句话：装了没、版本够不够、登录了没、能不能说话")
    checking.add_argument("name")
    checking.set_defaults(func=cmd_check)
    using = actions.add_parser("use", help="换助理 / 执行层用哪家，或改这家新对话用的模型与深度")
    using.add_argument("name")
    using.add_argument("--for", dest="roles", action="append", choices=agents.ROLES,
                       help="chat 是对话的助理，executor 是写代码的执行层；可重复")
    using.add_argument("--model", default=None, help="新对话用的模型：那家清单里的名字")
    using.add_argument("--effort", default=None, help="新对话用的思考深度：那家清单里的档位")
    using.set_defaults(func=cmd_use)
