"""子命令之间共用的那点东西：退出码、runs 根、日志、`--runs-root`。

为什么不放在 `__init__.py`：`__init__` 要 import 四个子命令模块来装配 parser，子命令
再回头 import `__init__` 就成了循环。共用的东西沉到一个谁都能 import 的小模块，方向
就还是单向的。
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from framework.run.context import default_runs_root

EXIT_OK = 0
EXIT_INVALID = 1
EXIT_USAGE = 2


def setup_logging() -> None:
    """内环每轮一条结构化 info 走 stderr；stdout 只留给给协调层读的结论。"""
    logging.basicConfig(level=logging.INFO, stream=sys.stderr,
                        format="%(asctime)s %(name)s %(message)s")


def runs_root(args: argparse.Namespace) -> Path:
    return Path(args.runs_root) if getattr(args, "runs_root", None) else default_runs_root()


def add_runs_root(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--runs-root", default=None,
                        help="runs 根目录，缺省读环境变量 AI4SCI_RUNS_ROOT，再缺省 <仓根>/runs")
