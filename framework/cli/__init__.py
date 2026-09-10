"""`ai4sci` 命令行：协调层驱动框架的唯一入口（workflow.md §5）。

每条子命令一个模块，本文件只做两件事：把它们的 parser 装配起来、导出 `main`。
四层里的最上面一层，可以 import 下面任何一层；反过来没有任何一层认识 CLI。

每条子命令只干一件事、跑完就退，用退出码表态，不常驻、不等人（P-10）：

    0  通过
    1  没通过（问题一行一条打到 stderr）
    2  用法错误：目录不存在、发现阶段的拓扑冲突
"""

from __future__ import annotations

import argparse

from framework.cli import loop, run, status, task

__all__ = ["build_parser", "main"]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="ai4sci", description="TJU AI for Science 平台 CLI")
    groups = parser.add_subparsers(dest="group", required=True)
    # 加一条子命令 = 加一个模块 + 这里加一行：没有注册表，diff 里一眼能看到（P-8）
    task.add_parser(groups)
    run.add_parser(groups)
    loop.add_parser(groups)
    status.add_parser(groups)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return int(args.func(args))
