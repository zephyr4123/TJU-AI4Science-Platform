"""子命令之间共用的那点东西：退出码、日志、当前工作区、按名字取端口。

为什么不放在 `__init__.py`：`__init__` 要 import 各子命令模块来装配 parser，子命令
再回头 import `__init__` 就成了循环。共用的东西沉到一个谁都能 import 的小模块，方向
就还是单向的。

当前工作区（纲领 P-15）：命令不带工作区路径，从 cwd 往上找 `requirement.md`（`AI4SCI_WORKSPACE`
可指定），找不到退 2 并说清怎么办。协调 agent 的工作目录就是工作区，所以它敲的命令一个路径都不带。
"""

from __future__ import annotations

import logging
import sys

from backends import BackendNotFound, get_backend
from compute import ComputeNotFound
from framework import computes
from framework.contracts.capability import Ports
from framework.workspace import root
from framework.workspace.root import Workspace

EXIT_OK = 0
EXIT_INVALID = 1
EXIT_USAGE = 2


def setup_logging() -> None:
    """内环每轮一条结构化 info 走 stderr；stdout 只留给给协调层读的结论。"""
    logging.basicConfig(level=logging.INFO, stream=sys.stderr,
                        format="%(asctime)s %(name)s %(message)s")


def current_workspace() -> Workspace | int:
    try:
        return root.find()
    except root.WorkspaceNotFound as exc:
        print(str(exc), file=sys.stderr)
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
