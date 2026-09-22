"""`ai4sci check [--only agents|computes|storage]`：冷启动自检（纲领 P-25）。

底座每家 probe、算力每台 check、存放（数据根在哪、可写、余量），三项同一种形状「探测 → 报告 → 写
last_check」，一行一项打出来；一项不过退出码非零，CI 跑得了不含登录的部分（`--only storage`）。
页面「设置」那块板走同一个函数（`chat/settings.check`）。
"""

from __future__ import annotations

import argparse
import sys

from backends import BackendNotFound
from framework import agents, computes
from framework.chat import settings
from framework.cli._common import EXIT_INVALID, EXIT_OK, EXIT_USAGE


def cmd_check(args: argparse.Namespace) -> int:
    try:
        report = settings.check(args.only or "all")
    except (BackendNotFound, agents.AgentsInvalid, computes.ComputesInvalid) as exc:
        print(str(exc), file=sys.stderr)
        return EXIT_USAGE
    table = report["agents"]
    if args.only in (None, "all", "agents"):
        for entry in table["entries"]:
            roles = [agents.ROLE_LABELS[r] for r in agents.ROLES if table[r] == entry["name"]]
            check = entry["last_check"] or {}
            print(f"{entry['title']}\t{'可用' if check.get('ok') else '检查没过'}"
                  + (f"\t{'、'.join(roles)}" if roles else ""))
            for item in check.get("items", []):
                print(f"  {'✓' if item['ok'] else '✗'} {item['name']}\t{item['note']}")
    if args.only in (None, "all", "computes"):
        for row in report["computes"]:
            check = row["last_check"] or {}
            state = "可用" if check.get("ok") else "检查没过"
            print(f"算力 {row['name']}\t{row['where']}\t{state}")
            for item in check.get("items", []):
                if isinstance(item, dict):
                    mark = "✓" if item.get("ok") else "✗"
                    print(f"  {mark} {item.get('name')}\t{item.get('note')}")
    if args.only in (None, "all", "storage"):
        storage = report["storage"]
        print(f"存放\t{storage['home']}\t{'可写' if storage['writable'] else '不可写'}"
              f"\t剩 {storage['free_gb']} GB\t{storage['workspaces']} 个工作区")
    print(f"ok\t{'全部通过' if report['ok'] else '没过：' + '、'.join(report['failed'])}")
    return EXIT_OK if report["ok"] else EXIT_INVALID


def add_parser(groups: argparse._SubParsersAction) -> None:
    group = groups.add_parser("check", help="冷启动自检：底座、算力、存放；一项不过退出码非零")
    group.add_argument("--only", choices=("agents", "computes", "storage"), default=None,
                       help="只查一项（CI 用 storage：不含登录）")
    group.set_defaults(func=cmd_check)
