"""分析能力：读一个 run 的账本、笔记、diff 与结果，执行层写一份可回溯的 analysis.md。

一个能力一个子包，互不 import（`capabilities/__init__.py`）。对外只露描述符与统一入口；
怎么组 prompt、怎么判产物形状是 `analyze.py` 自己的事。
"""

from __future__ import annotations

from pathlib import Path

from framework.capabilities.analysis.analyze import analyze
from framework.contracts.capability import Artifact, Capability, Ports

__all__ = ["DESCRIPTOR", "run"]

DESCRIPTOR = Capability(
    name="analysis",
    level="run",
    summary="实验分析：执行层读账本、笔记、best diff 与结果清单，写三节固定、数字可回溯的分析",
    stage="分析",
    title="写分析",
    what="读账本和每一轮的结果，写一份分析：结论、数据表、证伪与未决三节。",
    inputs=(
        Artifact("manifest", "manifest.yaml", "研究问题、主指标与方向"),
        Artifact("ledger", "experiment/ledger.tsv", "账本全部行"),
        Artifact("notebook", "experiment/notebook.md", "实验笔记全文"),
        Artifact("runs", "experiment/runs/", "每轮的 results.json：数据表只许从这里抄"),
        Artifact("work", "work/", "基线到 best 的代码 diff"),
    ),
    outputs=(
        Artifact("analysis", "analysis/analysis.md",
                 "三节固定：结论 / 数据（| run | 指标 | 值 |）/ 证伪与未决"),
    ),
    needs_executor=True,
    criteria=(
        "三节齐全，数据表至少一行能解析（分析能力自己校验形状）",
        "数据表每个值在对应 run 的 results.json 里能找到，正文里的小数都在表里（验证能力回溯）",
        "执行层只写 analysis/，越界判失败",
    ),
)


def run(run_dir: Path, ports: Ports) -> str:
    return analyze(run_dir, ports)
