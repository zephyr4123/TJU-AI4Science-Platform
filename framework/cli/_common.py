"""子命令之间共用的那点东西：退出码、日志、当前项目与工作区、按名字取端口。

为什么不放在 `__init__.py`：`__init__` 要 import 各子命令模块来装配 parser，子命令
再回头 import `__init__` 就成了循环。共用的东西沉到一个谁都能 import 的小模块，方向
就还是单向的。

当前项目与工作区（纲领 P-15，外层 #136）：命令不带路径。助理站在项目里（工作目录 = 项目，往上找
`project.md`，`AI4SCI_PROJECT` 可指定），工作区级的命令带 `--ws <名字>` 说清哪个；不带就从 cwd
往上找 `requirement.md`（人在终端、执行层在产出目录里都是这样）；站在项目里却不带 `--ws` 就退 2
并列出有哪些。
"""

from __future__ import annotations

import argparse
import logging
import sys

from backends import BackendNotFound, get_backend
from compute import ComputeNotFound
from framework import computes
from framework.contracts.capability import Ports
from framework.workspace import project, root
from framework.workspace.project import Project
from framework.workspace.root import Workspace

EXIT_OK = 0
EXIT_INVALID = 1
EXIT_USAGE = 2
WS_HELP = "哪个工作区（项目里的名字，ai4sci show project 列出）；不给就按当前目录"


def setup_logging() -> None:
    """内环每轮一条结构化 info 走 stderr；stdout 只留给给协调层读的结论。"""
    logging.basicConfig(level=logging.INFO, stream=sys.stderr,
                        format="%(asctime)s %(name)s %(message)s")


def add_ws_option(parser: argparse.ArgumentParser) -> None:
    """工作区级的命令都长一样的 `--ws`。"""
    parser.add_argument("--ws", default="", metavar="NAME", help=WS_HELP)


def current_project() -> Project | int:
    try:
        return project.find()
    except project.ProjectNotFound as exc:
        print(str(exc), file=sys.stderr)
        return EXIT_USAGE


def current_workspace(args: argparse.Namespace | None = None) -> Workspace | int:
    """`--ws` 给了就是当前项目里的那个；没给从 cwd 往上找。找不到退 2 并说清怎么办。"""
    ws_id = (getattr(args, "ws", "") or "").strip() if args is not None else ""
    try:
        if ws_id:
            return project.find().workspace(ws_id)
        return root.find()
    except (project.ProjectNotFound, root.WorkspaceInvalid) as exc:
        print(str(exc), file=sys.stderr)
        return EXIT_USAGE
    except root.WorkspaceNotFound as exc:
        message = str(exc)
        if not ws_id:
            try:  # 站在项目里、不在任何工作区里：把有哪些列给它
                found = project.find()
                have = ", ".join(w.id for w in found.workspaces()) or "-"
                message = f"你在项目 {found.id} 里、不在任何工作区里：带 --ws <名字>（有：{have}）"
            except project.ProjectNotFound:
                pass
        print(message, file=sys.stderr)
        return EXIT_USAGE


def resolve_ports(backend: str | None, compute: str | None) -> Ports | int:
    """按名字取端口，None 表示这个能力不要它。算力名字查按人的清单（P-23），空串是清单里的缺省；
    名字对不上退 2，绝不静默回退到默认后端（纲领 §5）。"""
    try:
        ports = Ports(runner=None if backend is None else get_backend(backend))
        if compute is not None:
            registry = computes.load()
            name = compute or registry.default
            entry = registry.get(name)
            ports.compute = computes.instance(name, registry)
            ports.compute_label = entry.label()
        return ports
    except (BackendNotFound, ComputeNotFound, computes.ComputesInvalid) as exc:
        print(str(exc), file=sys.stderr)
        return EXIT_USAGE
