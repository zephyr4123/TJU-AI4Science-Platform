"""`ai4sci env resolve [--python X.Y] [--compute <名字>] [--from <requirements.txt>] <包名>…`
隔离新建 | `ai4sci env use --compute <名字> <解释器路径>` 用机器上现成的环境（外层 #117、
纲领 P-23）| `ai4sci env add --compute <名字> [--from <requirements.txt>] <包名>…` 往现成的
环境里补几个包（P-24）。

两条路是 P-23 的两问：隔离新建（版本锁死、换机器可复现；第一次要在那台机器上下几 GB）还是用机器上
现成的（几秒起跑；版本以那台机器为准，换机器要重选）。`resolve` 按几个包名算完整清单；`use` 探那个
解释器的版本、`pip freeze` 当清单（出处留档）、写 `materials/env/interpreter`，之后设计与实验在那台
机器上直接用它。

在 cli 层。非工程师的常态是「我没有环境」，助理只能手写一份清单——手写的三行让基线一 import 就炸。
`resolve` 把「几个包名 → 钉死传递依赖的完整清单」交给 uv（`experiment.env.resolve_lock`），
写进当前工作区的 `materials/env/`（python-version + requirements.lock）；会联网。`--compute <名字>`
到那台机器上算（P-23：清单按目标机器算，CUDA 版 torch 只在那边解析得对）。
已有 `materials/env/python-version` 时 `--python` 可省；两边都没有就退 2 说清。
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from compute import ComputeNotFound
from framework import computes
from framework.cli._common import (
    EXIT_INVALID,
    EXIT_OK,
    EXIT_USAGE,
    add_ws_option,
    current_workspace,
)
from framework.experiment import env


def cmd_resolve(args: argparse.Namespace) -> int:
    ws = current_workspace(args)
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
    packages = list(args.packages)
    if args.from_file:
        source = Path(args.from_file)
        if not source.is_file():
            print(f"--from 指的文件不存在：{source}", file=sys.stderr)
            return EXIT_USAGE
        packages += _requirements_of(source)
    if not packages:
        print("要么给几个包名，要么 --from <requirements.txt>（上游仓库里的）", file=sys.stderr)
        return EXIT_USAGE
    try:
        compute = computes.instance(args.compute) if args.compute else None
        lock = env.resolve_lock(target, version, packages, compute=compute)
    except (env.EnvBuildError, ComputeNotFound, computes.ComputesInvalid) as exc:
        print(str(exc), file=sys.stderr)
        return EXIT_INVALID
    pins = [line for line in lock.read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.startswith("#")]
    print(f"ok {lock.relative_to(ws.root)}\tpython={version}\tpins={len(pins)}"
          f"\tnext=需求「材料」里写明环境是这条命令算的；设计阶段按它建环境")
    return EXIT_OK


def _requirements_of(path: Path) -> list[str]:
    """上游仓库的 requirements.txt → 包名清单：注释、空行、`-r` / `-e` / `--` 这类 pip 选项跳过
    （它们指向别的文件或本地路径，uv pip compile 在临时目录里解析不了）。"""
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.split("#", 1)[0].strip()
        if not line or line.startswith("-"):
            continue
        out.append(line)
    return out


def cmd_use(args: argparse.Namespace) -> int:
    ws = current_workspace(args)
    if isinstance(ws, int):
        return ws
    if not args.python.startswith("/"):
        print(f"解释器要写绝对路径（compute check 的「已有环境」里列的），得到 {args.python!r}",
              file=sys.stderr)
        return EXIT_USAGE
    try:
        compute = computes.instance(args.compute)
        target = env.use_interpreter(ws.materials / env.ENV_DIRNAME, compute, args.python)
    except (env.EnvBuildError, ComputeNotFound, computes.ComputesInvalid) as exc:
        print(str(exc), file=sys.stderr)
        return EXIT_INVALID
    version = (target / env.PYTHON_VERSION_NAME).read_text(encoding="utf-8").strip()
    lock = (target / env.REQUIREMENTS_NAME).read_text(encoding="utf-8").splitlines()
    pins = [line for line in lock if line.strip() and not line.startswith("#")]
    print(f"ok materials/env/\tcompute={args.compute}\tpython={version}\tpins={len(pins)}"
          f"\tnext=需求「材料」里写明用的是 {args.compute} 上现成的环境（不隔离）；换机器要重选")
    return EXIT_OK


def cmd_add(args: argparse.Namespace) -> int:
    ws = current_workspace(args)
    if isinstance(ws, int):
        return ws
    packages = list(args.packages)
    if args.from_file:
        source = Path(args.from_file)
        if not source.is_file():
            print(f"--from 指的文件不存在：{source}", file=sys.stderr)
            return EXIT_USAGE
        packages += _requirements_of(source)
    if not packages:
        print("要么给几个包名，要么 --from <requirements.txt>（上游仓库里的）", file=sys.stderr)
        return EXIT_USAGE
    try:
        compute = computes.instance(args.compute)
        target = env.add_packages(ws.materials / env.ENV_DIRNAME, compute, packages)
    except (env.EnvBuildError, ComputeNotFound, computes.ComputesInvalid) as exc:
        print(str(exc), file=sys.stderr)
        return EXIT_INVALID
    lock = (target / env.REQUIREMENTS_NAME).read_text(encoding="utf-8").splitlines()
    pins = [line for line in lock if line.strip() and not line.startswith("#")]
    print(f"ok materials/env/\tcompute={args.compute}\tadded={len(packages)}"
          f"\tpins={len(pins)}\tnext=接着干：ai4sci cap reproduction --continue design/<n>"
          "（或重开一次）")
    return EXIT_OK


def add_parser(groups: argparse._SubParsersAction) -> None:
    group = groups.add_parser(
        "env", help="研究者的环境：隔离新建（resolve）、用现成的（use）、往现成的里补包（add）")
    actions = group.add_subparsers(dest="action", required=True)
    adding = actions.add_parser(
        "add", help="往机器上现成的环境里补几个包（pip install 进 env use 登记的那个解释器，"
                    "重新登记清单）")
    adding.add_argument("packages", nargs="*", help="要补的包，如 scipy torchjd==0.13.0")
    adding.add_argument("--from", dest="from_file", default="",
                        help="从一份 requirements.txt 读包名（复现：上游仓库里的那份）")
    adding.add_argument("--compute", required=True,
                        help="哪台机器（ai4sci show computes 里的名字）")
    add_ws_option(adding)
    adding.set_defaults(func=cmd_add)
    using = actions.add_parser(
        "use", help="用某台机器上现成的解释器：探版本、pip freeze 当清单、写 env/interpreter")
    using.add_argument("python", help="那台机器上解释器的绝对路径（compute check「已有环境」列的）")
    using.add_argument("--compute", required=True, help="哪台机器（ai4sci show computes 里的名字）")
    add_ws_option(using)
    using.set_defaults(func=cmd_use)
    resolving = actions.add_parser(
        "resolve", help="按几个包名算出钉死传递依赖的完整清单，写进 materials/env/（会联网）")
    resolving.add_argument("packages", nargs="*", help="要的包，如 torch numpy scipy")
    resolving.add_argument("--from", dest="from_file", default="",
                           help="从一份 requirements.txt 读包名（复现：上游仓库里的那份）")
    resolving.add_argument("--python", default="",
                           help="Python 版本 X.Y；materials/env/python-version 已有时可省")
    resolving.add_argument("--compute", default="",
                           help="到哪台机器上算（ai4sci show computes 里的名字）：GPU 版 torch"
                                "只在那边解析得对；缺省本机")
    add_ws_option(resolving)
    resolving.set_defaults(func=cmd_resolve)
