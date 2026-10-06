"""`ai4sci agent list | check <名字> | use <名字> [--for chat|executor] [--provider] [--model]
[--effort] | login <名字>`：底座（纲领 P-25）。

在 cli 层。清单在平台的家里的 `agents.yaml`（`framework.agents`，外层 #263）；
有哪几家是 `backends._BACKENDS`
定的，没有 `add`。`check` 四句人话（装了没 / 版本 / 登录 / 说话）一行一项打出来，不过也只是报告、
记录照留，
退出码说过没过；`use` 换助理或执行层用哪家、改这家新对话用的模型与深度，值要在那家清单上。
助理能跑前三条；`login` 只给人：在平台的家里登录那家的官方账号（CLI 自己开浏览器授权），没有终端
（agent 起的子进程）就拒——平台的账号是人的事。
"""

from __future__ import annotations

import argparse
import subprocess
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
    models = None if args.models is None else tuple(args.models.split(","))
    if not roles and all(v is None for v in (args.provider, args.base_url, models, args.model,
                                             args.effort)):
        print("要么 --for chat|executor 换用哪家，要么 --provider 换用谁的模型，要么 --model / "
              "--effort 改缺省，至少给一样", file=sys.stderr)
        return EXIT_USAGE
    try:
        entry = agents.use(args.name, roles=roles, provider=args.provider, base_url=args.base_url,
                           models=models, model=args.model, effort=args.effort)
    except (BackendNotFound, agents.AgentsInvalid, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return EXIT_USAGE
    used = "、".join(agents.ROLE_LABELS[r] for r in roles)
    print(f"ok {entry.name}\t{entry.provider}\t{entry.model}\t{entry.effort}"
          + (f"\t{used}" if used else "")
          + f"\t写入 {agents.path()}")
    return EXIT_OK


def cmd_login(args: argparse.Namespace) -> int:
    if not sys.stdin.isatty():
        print("登录要人在终端里亲手做：浏览器里授权，有时还要把页面给的码贴回来", file=sys.stderr)
        return EXIT_USAGE
    try:
        argv, env = agents.login_command(args.name)
    except BackendNotFound as exc:
        print(str(exc), file=sys.stderr)
        return EXIT_USAGE
    done = subprocess.run(argv, env=env, check=False)
    if done.returncode != 0:
        print(f"登录没成（退出码 {done.returncode}）", file=sys.stderr)
        return EXIT_INVALID
    print(f"ok {args.name}\t已在平台的家里登录；ai4sci agent check {args.name} 验一遍")
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
    using.add_argument("--provider", default=None,
                       help="用谁的模型：official、anthropic / openai、deepseek、kimi、custom；"
                            "key 在设置页填（外层 #266）")
    using.add_argument("--base-url", default=None, help="自定义供应商的接口地址")
    using.add_argument("--models", default=None, help="自定义供应商的模型名，逗号隔开")
    using.add_argument("--model", default=None, help="新对话用的模型：那家清单里的名字")
    using.add_argument("--effort", default=None, help="新对话用的思考深度：那家清单里的档位")
    using.set_defaults(func=cmd_use)
    login = actions.add_parser("login", help="在平台的家里登录这家的官方账号（只给人，要终端）")
    login.add_argument("name")
    login.set_defaults(func=cmd_login)
