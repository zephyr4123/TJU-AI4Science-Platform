"""`ai4sci` 命令行：协调层驱动框架的唯一入口（workflow.md §5）。

平台在命令行上就六类东西：`cap` 能力（agent 调用，读产出、产出目录）、`requirement confirm` /
`sign` 人的确认（确认需求、给产出签字）、`show` 查询（只读）、`flow take` 取流程、`output new`
建产出、`job stop` 停作业与 `env resolve` 算环境清单、`compute` 接机器（P-23）、`skill` 工具包
（清单、读一个、起它的脚本；两层 agent 都能用，P-22）、`project` / `workspace` / `chat` / `serve`
入口。
每类一个模块，本文件只做两件事：把它们的 parser 装配起来、导出 `main`。
四层里的最上面一层，可以 import 下面任何一层；反过来没有任何一层认识 CLI。

每条子命令只干一件事、跑完就退，用退出码表态，不常驻、不等人（P-10）；
唯一例外是 `serve`，它是网页的门，常驻：

    0  通过
    1  没通过（问题一行一条打到 stderr）
    2  用法错误：目录不存在、发现阶段的拓扑冲突
"""

from __future__ import annotations

import argparse
import sys

from framework.cli import (
    agent,
    cap,
    chat,
    check,
    compute,
    env,
    flow,
    job,
    output,
    project,
    requirement,
    serve,
    show,
    sign,
    skill,
    workspace,
)

__all__ = ["build_parser", "main"]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="ai4sci", description="TJU AI for Science 平台 CLI")
    groups = parser.add_subparsers(dest="group", required=True)
    # 加一条子命令 = 加一个模块 + 这里加一行：没有注册表，diff 里一眼能看到（P-8）
    cap.add_parser(groups)
    requirement.add_parser(groups)
    sign.add_parser(groups)
    show.add_parser(groups)
    flow.add_parser(groups)
    output.add_parser(groups)
    job.add_parser(groups)
    env.add_parser(groups)
    compute.add_parser(groups)
    agent.add_parser(groups)
    check.add_parser(groups)
    skill.add_parser(groups)
    project.add_parser(groups)
    workspace.add_parser(groups)
    chat.add_parser(groups)
    serve.add_parser(groups)
    return parser


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    args = build_parser().parse_args(argv)
    args.argv = argv  # 原样的命令行：`cap ... --detach` 要把同一条命令起成作业
    return int(args.func(args))
