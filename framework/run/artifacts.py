"""一个 run 里已经落盘的 harness 结果有哪些：run 名 → results.json 路径。

分析要把它们列成清单给执行层抄，验证要拿它们回溯数据表——两个能力互不 import，
共用的索引放在 run 层。`run_0` 是任务包基线（在 work/ 里），`run_N` 是内环每轮的快照；
只列文件存在的，合不合约由 `contracts.results.read_metrics` 判。
"""

from __future__ import annotations

import re
from pathlib import Path

from framework.run import layout

RESULTS_NAME = "results.json"
_RUN_DIR_RE = re.compile(r"^run_(\d+)$")


def run_results(run_dir: Path) -> dict[str, Path]:
    """按 run 序号排序：run_0（基线）在前，然后 run_1、run_2 …"""
    run_dir = Path(run_dir)
    found: dict[int, Path] = {}
    baseline = layout.work(run_dir) / "run_0" / RESULTS_NAME
    if baseline.is_file():
        found[0] = baseline
    runs_root = layout.experiment(run_dir) / "runs"
    if runs_root.is_dir():
        for child in runs_root.iterdir():
            match = _RUN_DIR_RE.match(child.name)
            if match and (child / RESULTS_NAME).is_file():
                found[int(match.group(1))] = child / RESULTS_NAME
    return {f"run_{n}": found[n] for n in sorted(found)}
