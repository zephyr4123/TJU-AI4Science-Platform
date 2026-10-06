"""`ai4sci reset`：清除平台的家（外层 #263）——两家 CLI 在平台里的登录登出、整个 `~/.ai4sci` 删掉。

只给人：没有终端（agent 起的子进程）就拒，有终端也要敲「清除」两个字确认，没有 `--yes`。
删之前先念一遍家在哪、每块多大；闸（标记、主目录、在跑的作业）在 `framework/chat/reset.py`。
"""

from __future__ import annotations

import argparse
import sys

from framework import paths
from framework.chat import reset, settings
from framework.cli._common import EXIT_INVALID, EXIT_OK, EXIT_USAGE

CONFIRM_WORD = "清除"


def cmd_reset(args: argparse.Namespace) -> int:
    del args
    if not sys.stdin.isatty():
        print("清除只能人在终端里做（要敲字确认）", file=sys.stderr)
        return EXIT_USAGE
    home = paths.home()
    try:
        reset.check(home)
    except reset.ResetRefused as exc:
        print(str(exc), file=sys.stderr)
        return EXIT_INVALID
    storage = settings.storage_table(home)
    print(f"要删除平台的家 {home}：")
    for part in storage["parts"]:
        print(f"  {part['label']}\t{part['bytes'] / 1e6:.1f} MB")
    answer = input(f"删了找不回来。确认请输入「{CONFIRM_WORD}」：").strip()
    if answer != CONFIRM_WORD:
        print("没删", file=sys.stderr)
        return EXIT_USAGE
    try:
        for line in reset.reset(home):
            print(line)
    except reset.ResetRefused as exc:
        print(str(exc), file=sys.stderr)
        return EXIT_INVALID
    return EXIT_OK


def add_parser(groups: argparse._SubParsersAction) -> None:
    group = groups.add_parser("reset", help="清除平台的家：登出、删掉全部数据（只给人）")
    group.set_defaults(func=cmd_reset)
