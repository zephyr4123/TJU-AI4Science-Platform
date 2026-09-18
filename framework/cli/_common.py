"""子命令之间共用的那点东西：退出码、日志、当前工作区、开 run 目录、按名字取端口。

为什么不放在 `__init__.py`：`__init__` 要 import 各子命令模块来装配 parser，子命令
再回头 import `__init__` 就成了循环。共用的东西沉到一个谁都能 import 的小模块，方向
就还是单向的。

当前工作区（纲领 P-15）：命令不带工作区路径，从 cwd 往上找 `workspace.yaml`（`AI4SCI_WORKSPACE`
可指定），找不到退 2 并说清怎么办。协调 agent 的工作目录就是工作区，所以它敲的命令一个路径都不带。
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

from backends import BackendNotFound, get_backend
from compute import ComputeNotFound, get_compute
from framework.contracts.capability import Ports
from framework.run import layout, workspace
from framework.run.workspace import Workspace

EXIT_OK = 0
EXIT_INVALID = 1
EXIT_USAGE = 2


def setup_logging() -> None:
    """内环每轮一条结构化 info 走 stderr；stdout 只留给给协调层读的结论。"""
    logging.basicConfig(level=logging.INFO, stream=sys.stderr,
                        format="%(asctime)s %(name)s %(message)s")


def current_workspace() -> Workspace | int:
    try:
        return workspace.find()
    except workspace.WorkspaceNotFound as exc:
        print(str(exc), file=sys.stderr)
        return EXIT_USAGE


def open_run_dir(ws: Workspace, run_id: str) -> Path | int:
    """`<工作区>/runs/<run_id>`；没有 checkpoint 就是"run 不存在"，退 2。"""
    run_dir = ws.runs / run_id
    if not layout.checkpoint(run_dir).is_file():
        print(f"run 不存在或没有 checkpoint：{run_dir}", file=sys.stderr)
        return EXIT_USAGE
    return run_dir


def resolve_ports(backend: str | None, compute: str | None) -> Ports | int:
    """按名字取端口，None 表示这个能力不要它。名字对不上退 2，绝不静默回退到默认后端（纲领 §5）。"""
    try:
        return Ports(
            runner=None if backend is None else get_backend(backend),
            compute=None if compute is None else get_compute(compute),
        )
    except (BackendNotFound, ComputeNotFound) as exc:
        print(str(exc), file=sys.stderr)
        return EXIT_USAGE
