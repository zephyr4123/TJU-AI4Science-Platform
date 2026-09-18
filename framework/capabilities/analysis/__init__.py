"""写分析初稿：分析阶段里现有的一颗能力——读一个 run 的账本、笔记、diff 与结果，执行层写三节固定的
analysis.md。

一个能力一个子包，互不 import（`capabilities/__init__.py`）。对外只露描述符与统一入口；
怎么组 prompt、怎么判产物形状是 `analyze.py` 自己的事。
"""

from __future__ import annotations

from pathlib import Path

from framework.capabilities.analysis.analyze import analyze
from framework.contracts.capability import Capability, Ports

__all__ = ["DESCRIPTOR", "run"]

DESCRIPTOR = Capability(
    name="analysis",
    level="run",
    stage="分析",
    title="写分析初稿",
    does=(
        "起一个执行层会话，只给它这个 run 的 manifest 快照、账本全部行、实验笔记全文、"
        "每轮的 results.json 清单，以及 work/ 里基线到 best 的代码 diff，"
        "让它写一份三节固定的 analysis/analysis.md：结论、数据表（| run | 指标 | 值 |，"
        "只许从 results.json 抄）、证伪与未决。会话结束后框架核形状：三节齐、"
        "数据表至少一行能解析。"
    ),
    does_not=(
        "不核对数字对不对（那是验证阶段「核对数字」的事）、不画图、不写综述、不比较别的 run。"
        "它是初稿，不是分析这个阶段的全部：以后加进来的对比、作图、复盘都是这个阶段里另外的能力。"
        "执行层只许写 analysis/，越界判失败。"
    ),
    brings=(
        "一个跑过至少一轮的 run：manifest.yaml、experiment/ledger.tsv、"
        "experiment/notebook.md、experiment/runs/run_N/results.json、work/（git 仓）。"
    ),
    leaves=(
        "analysis/analysis.md；重跑时旧的改名成 analysis_v1/ 留档，不覆盖。"
    ),
    stops=(
        "一次成稿就退出。会话越界、三节缺一、数据表一行都解析不出：判失败、报告原因，"
        "协调层看了决定重跑还是找人。"
    ),
    needs_executor=True,
)


def run(run_dir: Path, ports: Ports) -> str:
    return analyze(run_dir, ports)
