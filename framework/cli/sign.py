"""`ai4sci sign <stage>/<n> --by <谁> [--note]`：人给一次产出签字，终端这张脸（纲领 P-19）。

在 cli 层。签字不是能力：不产出科研产物，只落一条记录——产出目录里的 `signed.json`
（`contracts.output.sign`）。流程里哪一项后面有断点，那一项的产出就得签了下游才能读；页面上的「签」
写的是同一份记录。只有人能签：助理的会话里调它一律拒（`refuse_if_assistant`），不靠指南里的一句「你不替人签」。
"""

from __future__ import annotations

import argparse
import getpass
import sys

from framework.cli._common import (
    EXIT_INVALID,
    EXIT_OK,
    EXIT_USAGE,
    add_ws_option,
    current_workspace,
    refuse_if_assistant,
)
from framework.contracts import output
from framework.workspace import outputs


def cmd_sign(args: argparse.Namespace) -> int:
    refused = refuse_if_assistant("给产出签字")
    if refused is not None:
        return refused
    ws = current_workspace(args)
    if isinstance(ws, int):
        return ws
    try:
        directory, meta = outputs.find_output(ws, args.output)
    except (ValueError, output.OutputNotFound) as exc:
        print(str(exc), file=sys.stderr)
        return EXIT_USAGE
    try:
        record = output.sign(directory, by=args.by, note=args.note)
    except output.SignRefused as exc:
        print(str(exc), file=sys.stderr)
        return EXIT_INVALID
    print(f"ok {meta.id}\tby={record['by']}\tat={record['signed_at']}")
    return EXIT_OK


def add_parser(groups: argparse._SubParsersAction) -> None:
    sign = groups.add_parser("sign", help="人的确认：给一次产出签字（流程里那一项是断点才需要）")
    sign.add_argument("output", metavar="STAGE/N", help="签哪次产出，比如 design/1")
    sign.add_argument("--by", default=getpass.getuser(), help="谁签的，记在记录上；缺省当前登录名")
    sign.add_argument("--note", default="", help="一句话：确认了什么")
    add_ws_option(sign)
    sign.set_defaults(func=cmd_sign)
