"""`ai4sci job stop <id>`：人叫停一个后台作业（外层 #115）。

在 cli 层。查询（`show jobs` / `show job`）在 show 里，这里只放会改状态的动作。停 = 杀整棵进程树、
作业记 stopped、它开的那次产出记 failed（原因「人停的」）。已经不在跑的作业退 2 说清状态，
不对着尸体说「停了」。页面上的同一个动作走 `POST /workspaces/<id>/jobs/<jid>/stop`，同一个函数
（`workspace.jobs.stop`）。
"""

from __future__ import annotations

import argparse
import getpass
import sys

from framework.cli._common import EXIT_OK, EXIT_USAGE, add_ws_option, current_workspace
from framework.contracts import output
from framework.workspace import jobs


def cmd_stop(args: argparse.Namespace) -> int:
    ws = current_workspace(args)
    if isinstance(ws, int):
        return ws
    try:
        job = jobs.stop(ws, args.job_id, by=args.by or getpass.getuser())
    except (jobs.JobNotFound, jobs.JobNotRunning, output.OutputNotFound) as exc:
        print(str(exc), file=sys.stderr)
        return EXIT_USAGE
    print(f"ok {job.job_id}\tstopped\t{job.cap}\t{job.output or '-'}\t{job.result}")
    return EXIT_OK


def add_parser(groups: argparse._SubParsersAction) -> None:
    job = groups.add_parser("job", help="后台作业：停一个")
    actions = job.add_subparsers(dest="action", required=True)
    stopping = actions.add_parser("stop", help="停一个正在跑的作业：杀进程树，作业与它的产出都记上")
    stopping.add_argument("job_id", help="作业号（ai4sci show jobs）")
    stopping.add_argument("--by", default="", help="谁停的，记在记录上；缺省当前登录名")
    add_ws_option(stopping)
    stopping.set_defaults(func=cmd_stop)
