"""写分析初稿：分析阶段里现有的一颗能力——读一次或几次实验的账本、笔记、diff 与结果，
执行层写三节固定的 analysis.md。

一个能力一个子包，互不 import（`capabilities/__init__.py`）。对外只露描述符与统一入口；
怎么组 prompt、怎么判产物形状是 `analyze.py` 自己的事。
"""

from __future__ import annotations

from pathlib import Path

from framework.capabilities.analysis.analyze import analyze
from framework.contracts.capability import Capability, Inputs, Ports

__all__ = ["DESCRIPTOR", "run"]

DESCRIPTOR = Capability(
    name="analysis",
    stage="分析",
    title="分析初稿",
    does=(
        "起一个执行层会话，只给它 --from 点名的每次实验的账本全部行、实验笔记全文、"
        "每轮的 results.json 清单，以及 work/ 里基线到 best 的代码 diff，"
        "让它写一份三节固定的 analysis.md：结论、数据表（| 来源 | 指标 | 值 |，"
        "来源写成 experiment/<n>/baseline 或 experiment/<n>/iter_N，只许从 results.json 抄）、"
        "证伪与未决。会话结束后框架核形状：三节齐、数据表至少一行能解析。"
    ),
    does_not=(
        "不核对数字对不对（那是验证阶段「核对数字」的事）、不画图、不写综述。"
        "它是初稿，不是分析这个阶段的全部：以后加进来的对比、作图、复盘都是这个阶段里另外的能力。"
        "执行层只许写 analysis.md，越界判失败。"
    ),
    brings=(
        "一次或几次跑过至少一轮的实验产出（--from experiment/<n>）：scoring.yaml、ledger.tsv、"
        "notebook.md、iters/iter_N/results.json、work/（git 仓）。"
    ),
    leaves="analysis.md；执行层会话的日志在 executor/。",
    stops=(
        "一次成稿就退出。会话越界、三节缺一、数据表一行都解析不出：判失败、报告原因，"
        "协调层看了决定重跑（新开一次产出）还是找人。"
    ),
    needs_executor=True,
)


def run(output_dir: Path, inputs: Inputs, ports: Ports) -> str:
    return analyze(output_dir, inputs, ports)
