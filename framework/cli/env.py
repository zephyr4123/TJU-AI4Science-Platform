"""`ai4sci env resolve [--python X.Y] <包名>…`：研究者没有现成 Python 环境时，按几个包名算出完整的
`materials/env/`（外层 #117）。

在 cli 层。非工程师的常态是「我没有环境」，助理只能手写一份清单——手写的三行让基线一 import 就炸。
这条命令把「几个包名 → 钉死传递依赖的完整清单」交给 uv（`experiment.env.resolve_lock`），
写进当前工作区的 `materials/env/`（python-version + requirements.lock）；会联网。`--compute <名字>`
到那台机器上算（P-23：清单按目标机器算，CUDA 版 torch 只在那边解析得对）。
已有 `materials/env/python-version` 时 `--python` 可省；两边都没有就退 2 说清。
"""

from __future__ import annotations

import argparse
import sys

from compute import ComputeNotFound
from framework import computes
from framework.cli._common import EXIT_INVALID, EXIT_OK, EXIT_USAGE, current_workspace
from framework.experiment import env


def cmd_resolve(args: argparse.Namespace) -> int:
    ws = current_workspace()
    if isinstance(ws, int):
        return ws
    target = ws.materials / env.ENV_DIRNAME
    version = args.python
    if not version:
        path = target / env.PYTHON_VERSION_NAME
        if not path.is_file():
            print(f"没有 {path.relative_to(ws.root)}，要给 --python X.Y", file=sys.stderr)
            return EXIT_USAGE
        version = path.read_text(encoding="utf-8").strip()
    if not env.VERSION_RE.match(version):
        print(f"--python 要是 <major>.<minor> 如 3.12，得到 {version!r}", file=sys.stderr)
        return EXIT_USAGE
    try:
        compute = computes.instance(args.compute) if args.compute else None
        lock = env.resolve_lock(target, version, list(args.packages), compute=compute)
    except (env.EnvBuildError, ComputeNotFound, computes.ComputesInvalid) as exc:
        print(str(exc), file=sys.stderr)
        return EXIT_INVALID
    pins = [line for line in lock.read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.startswith("#")]
    print(f"ok {lock.relative_to(ws.root)}\tpython={version}\tpins={len(pins)}"
          f"\tnext=需求「材料」里写明环境是这条命令算的；设计阶段按它建环境")
    return EXIT_OK


def add_parser(groups: argparse._SubParsersAction) -> None:
    group = groups.add_parser("env", help="研究者的环境清单：按包名算出完整的 materials/env/")
    actions = group.add_subparsers(dest="action", required=True)
    resolving = actions.add_parser(
        "resolve", help="按几个包名算出钉死传递依赖的完整清单，写进 materials/env/（会联网）")
    resolving.add_argument("packages", nargs="+", help="要的包，如 torch numpy scipy")
    resolving.add_argument("--python", default="",
                           help="Python 版本 X.Y；materials/env/python-version 已有时可省")
    resolving.add_argument("--compute", default="",
                           help="到哪台机器上算（ai4sci show computes 里的名字）：GPU 版 torch"
                                "只在那边解析得对；缺省本机")
    resolving.set_defaults(func=cmd_resolve)
