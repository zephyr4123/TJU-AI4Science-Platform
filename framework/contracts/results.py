"""`results.json` 的读取与校验：harness 产物这一侧的契约。

在契约层而不是跟着失败分类走：读产物是"这份文件合不合约"，判这一轮算什么是能力的事
（`capabilities/experiment/failures.py`）。分开之后，别的能力（分析、验证）要读同一份
产物时不必去 import 实验内环。

`schemas/results.schema.json` 是唯一的判据来源，与 `packs.py` 校验 run_0 时用的是同一份。
"""

from __future__ import annotations

import json
from pathlib import Path

import jsonschema

from framework.contracts.packs import SCHEMA_DIR

SCHEMA_PATH = SCHEMA_DIR / "results.schema.json"


def read_results(path: Path, metric_name: str) -> tuple[float | None, list[str]]:
    """读 harness 的产物，返回（主指标, 问题清单）。

    NaN 照收不误：Python 的 json 默认解析 NaN，而 NaN 要走 nan_metric 这一类，
    在这里当成"文件不合法"会把病因说错，下一轮给执行层的修复提示也就跟着错。

    `status` 是 harness 自己对这一趟的定性，不是 ok 就当成"没有可用结果"（问题清单里带上
    它自报的值）：指标算出来了但 harness 说这趟不算数时，采信指标就是采信一个作废的成绩。
    """
    path = Path(path)
    if not path.is_file():
        return None, [f"results.json 缺失：{path}"]
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except ValueError as exc:
        return None, [f"results.json 解析失败：{' '.join(str(exc).split())}"]
    schema = json.loads((SCHEMA_PATH).read_text(encoding="utf-8"))
    problems = [
        f"results.json 不合 schema：{' '.join(str(e.message).split())}"
        for e in jsonschema.Draft202012Validator(schema).iter_errors(doc)
    ]
    status = doc.get("status") if isinstance(doc, dict) else None
    if status is not None and status != "ok":
        problems.append(f"harness 自报 status={status!r}，不是 ok")
    value = doc.get("metrics", {}).get(metric_name) if isinstance(doc, dict) else None
    if value is not None and not isinstance(value, (int, float)):
        return None, [*problems, f"主指标 {metric_name} 不是数字：{value!r}"]
    if value is None and not problems:
        problems.append(f"results.json 里没有主指标 {metric_name}")
    return value, problems
