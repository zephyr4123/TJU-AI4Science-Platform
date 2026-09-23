"""`ai4sci requirement confirm --by <谁>`：人确认当前工作区的需求，终端这张脸（纲领 P-19）。

在 cli 层。确认是唯一内置的门：没确认任何阶段不开工。页面上「确认需求」调的是同一个函数
（`contracts.requirement.confirm`）。只有人能确认：助理的会话里调它一律拒（`refuse_if_assistant`）。
"""

from __future__ import annotations

import argparse
import getpass
import sys

from framework.cli._common import (
    EXIT_INVALID,
    EXIT_OK,
    add_ws_option,
    current_workspace,
    refuse_if_assistant,
)
from framework.contracts import requirement


def cmd_confirm(args: argparse.Namespace) -> int:
    refused = refuse_if_assistant("确认需求")
    if refused is not None:
        return refused
    ws = current_workspace(args)
    if isinstance(ws, int):
        return ws
    try:
        record = requirement.confirm(ws.root, by=args.by)
    except requirement.ConfirmRefused as exc:
        print(str(exc), file=sys.stderr)
        return EXIT_INVALID
    print(f"ok {ws.id}\tv{record['version']}\tby={record['by']}\tat={record['confirmed_at']}"
          "\tnext=取一条流程 ai4sci flow take <name>，然后按流程走")
    return EXIT_OK


def add_parser(groups: argparse._SubParsersAction) -> None:
    req = groups.add_parser("requirement", help="需求：确认一个工作区的 requirement.md")
    actions = req.add_subparsers(dest="action", required=True)
    confirming = actions.add_parser("confirm", help="确认需求：写 requirement.lock，阶段才能开工")
    confirming.add_argument("--by", default=getpass.getuser(),
                            help="谁确认的，记在记录上；缺省当前登录名")
    add_ws_option(confirming)
    confirming.set_defaults(func=cmd_confirm)
