"""一次实验里已经落盘的 harness 结果有哪些：名字 → results.json 路径。

分析要把它们列成清单给执行层抄，验证要拿它们回溯数据表——两个能力互不 import，
共用的索引放在实验族的共享层。`baseline` 是设计那包的基线（在 work/ 里），`iter_N`
是内环每轮的快照；只列文件存在的，合不合约由 `experiment.results.read_metrics` 判。
"""

from __future__ import annotations

import re
from pathlib import Path

from framework.experiment import layout

RESULTS_NAME = "results.json"
_ITER_DIR_RE = re.compile(r"^iter_(\d+)$")


def run_results(run_dir: Path) -> dict[str, Path]:
    """按轮次排序：baseline 在前，然后 iter_1、iter_2 …"""
    run_dir = Path(run_dir)
    found: dict[int, Path] = {}
    baseline = layout.baseline(layout.work(run_dir)) / RESULTS_NAME
    if baseline.is_file():
        found[0] = baseline
    iters_root = run_dir / layout.ITERS_DIRNAME
    if iters_root.is_dir():
        for child in iters_root.iterdir():
            match = _ITER_DIR_RE.match(child.name)
            if match and (child / RESULTS_NAME).is_file():
                found[int(match.group(1))] = child / RESULTS_NAME
    return {(layout.BASELINE_KEY if n == 0 else layout.iter_key(n)): found[n]
            for n in sorted(found)}
