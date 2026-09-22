"""`ai4sci output new <stage> --title <一句> [--from ...] [--flow]`：
助理不经能力也能在一个阶段下开一次产出（纲领 P-19）。

在 cli 层。文献、假设、写作三个阶段现在没有能力，助理在对话里自己写东西：先在这儿开目录、写好 meta，
然后直接往目录里写文件。`by` 记成 assistant；人自己在终端开的，`--by human`。
门、输入的冻结核对、照流程与断点，与 `cap` 同一套（复用 cap 的函数）。
"""

from __future__ import annotations

import argparse
import os
import sys

from framework.cli._common import EXIT_INVALID, EXIT_OK, EXIT_USAGE, current_workspace
from framework.cli.cap import FLOW_HELP, FROM_HELP, _place_in_flow
from framework.cli.workspace import report
from framework.contracts import output, requirement, workflows
from framework.contracts.stages import STAGE_SLUGS, name_of
from framework.workspace import jobs, outputs, removal

BY_CHOICES = ("assistant", "human")


def cmd_new(args: argparse.Namespace) -> int:
    ws = current_workspace()
    if isinstance(ws, int):
        return ws
    if args.stage not in STAGE_SLUGS:
        print(f"阶段目录只认 {STAGE_SLUGS}，得到 {args.stage!r}", file=sys.stderr)
        return EXIT_USAGE
    try:
        version = requirement.require_confirmed(ws.root)
        inputs = outputs.resolve_inputs(ws, list(args.inputs or []))
        # 手写的产出在流程里按阶段找位置：没点名能力，只有阶段名有用
        title = args.title.strip() or name_of(args.stage)
        flow, step = _place_in_flow(ws, args.by, name_of(args.stage), inputs, args.flow)
    except (requirement.NotConfirmed, ValueError, output.OutputNotFound,
            workflows.WorkflowInvalid) as exc:
        print(str(exc), file=sys.stderr)
        return EXIT_INVALID
    directory, meta = outputs.open_output(
        ws, args.stage, title=title, by=args.by,
        inputs=list(inputs.ids), params={}, flow=flow, step=step, requirement=version,
        chat_id=os.environ.get(jobs.CHAT_ID_ENV))
    # 手写的产出没有"跑完"这一说：开了就算成，里面写什么由写的人定
    outputs.close_output(directory, meta, ok=True, line="手写")
    print(f"ok {meta.id}\t{directory}"
          f"\tnext=往这个目录里写文件；写完要人签的话 ai4sci sign {meta.id}")
    return EXIT_OK


def cmd_remove(args: argparse.Namespace) -> int:
    """删一次产出：只能删叶子（没被下游读过的）；正在跑的拒。"""
    ws = current_workspace()
    if isinstance(ws, int):
        return ws
    try:
        removed = removal.remove_output(ws, args.id)
    except (ValueError, output.OutputNotFound) as exc:  # RemovalRefused 也是 ValueError
        print(str(exc), file=sys.stderr)
        return EXIT_INVALID
    return report(removed, f"ok 删了产出 {removed.what}")


def add_parser(groups: argparse._SubParsersAction) -> None:
    out = groups.add_parser("output", help="产出：不经能力在一个阶段下开一次产出目录")
    actions = out.add_subparsers(dest="action", required=True)
    new = actions.add_parser("new", help="开一次产出：建 <stage>/<n>/ 并写 meta，然后往里写文件")
    new.add_argument("stage", help=f"阶段目录：{' / '.join(STAGE_SLUGS)}")
    new.add_argument("--title", default="", help="给人看的一句标签，比如「文献综述初稿」")
    new.add_argument("--from", dest="inputs", action="append", metavar="STAGE/N", help=FROM_HELP)
    new.add_argument("--flow", default="", help=FLOW_HELP)
    new.add_argument("--by", default="assistant", choices=BY_CHOICES, help="谁写的；缺省助理")
    new.set_defaults(func=cmd_new)
    removing = actions.add_parser("remove", help="删一次产出：只能删没被下游读过的叶子")
    removing.add_argument("id", metavar="STAGE/N", help="产出 id，比如 design/2")
    removing.set_defaults(func=cmd_remove)
