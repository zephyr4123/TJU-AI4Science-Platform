"""验证能力：零模型，对分析产物做数字回溯与账本对账，写 `verify/report.json`。

一个能力一个子包，互不 import。它读分析能力的产物但不 import 分析能力：两边共用的只有
`contracts.analysis`（数据表解析）与 `run.artifacts`（结果索引）。

判决语义：报告永远写出来（PASS 与 FAIL 都要留档），FAIL 再 raise `CapabilityFailed`——
协调层看到的退出码就是"过没过"，报告是细节（P-7 fail-closed：验证不过就停）。
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from pathlib import Path

from framework.capabilities.verify import checks
from framework.contracts.capability import Artifact, Capability, CapabilityFailed, Param, Ports
from framework.contracts.report import validate_report
from framework.run import layout
from framework.run.lifecycle import rotate_capability_dir

__all__ = ["DESCRIPTOR", "run"]

LOGGER = logging.getLogger("ai4sci.verify")
NAME = "verify"
DEFAULT_TOLERANCE = 0.01  # spec A-10：1% 容差

DESCRIPTOR = Capability(
    name="verify",
    level="run",
    summary="验证：零模型，分析里的每个数回溯到 results.json，账本与 git 对账，出 PASS / FAIL 报告",
    stage="验证",
    title="验证",
    what="把分析里的每个数回溯到某一轮的结果文件，账本和代码历史对账，出 PASS 或 FAIL。",
    inputs=(
        Artifact("analysis", "analysis/analysis.md", "分析能力的产物"),
        Artifact("runs", "experiment/runs/", "每轮的 results.json：数字的来源"),
        Artifact("ledger", "experiment/ledger.tsv", "账本，与 work/ 的 git 对账"),
        Artifact("work", "work/", "独立 git 仓"),
    ),
    outputs=(
        Artifact("report", "verify/report.json",
                 "status PASS / FAIL，每项检查的 passed 与 details"),
    ),
    params=(
        Param("tolerance", "float", DEFAULT_TOLERANCE, "数字回溯的相对容差，缺省 0.01（1%）"),
    ),
    criteria=(
        "analysis/analysis.md 存在",
        "数据表每行 (run, 指标, 值) 在那个 run 的 results.json 里能找到，相对误差在容差内",
        "正文里带小数点或指数的数都在数据表里",
        "账本每行 commit 在 git 里找得到，keep 链接得上",
    ),
)


def run(run_dir: Path, ports: Ports, *, tolerance: float = DEFAULT_TOLERANCE) -> str:
    run_dir = Path(run_dir).resolve()
    assert 0 <= tolerance < 1, f"tolerance 要在 [0, 1) 之间，得到 {tolerance!r}"
    archived = rotate_capability_dir(run_dir, NAME)
    results = _run_checks(run_dir, tolerance)
    status = "PASS" if all(c.passed for c in results) else "FAIL"
    _write_report(run_dir, status, results)
    failed = [c for c in results if not c.passed]
    report_rel = layout.verify_report(run_dir).relative_to(run_dir)
    LOGGER.info("verify_done run_dir=%s status=%s failed=%s archived=%s", run_dir, status,
                [c.name for c in failed], archived.name if archived else "-")
    if failed:
        first = failed[0]
        raise CapabilityFailed(
            f"verify FAIL {len(failed)}/{len(results)}：{first.name}："
            f"{'；'.join(first.details[:3])}（全部细节见 {report_rel}）")
    return f"verify PASS\tchecks={len(results)}\tpath={report_rel}"


def _run_checks(run_dir: Path, tolerance: float) -> list[checks.Check]:
    present = checks.analysis_present(run_dir)
    if not present.passed:
        # 没有分析就没有可回溯的东西，别再对着空文件报一串"表不存在"
        return [present]
    text = layout.analysis_doc(run_dir).read_text(encoding="utf-8")
    return [
        present,
        checks.numbers_traceable(run_dir, text, tolerance),
        checks.prose_numbers_in_table(text, tolerance),
        checks.ledger_reconciled(run_dir),
    ]


def _write_report(run_dir: Path, status: str, results: list[checks.Check]) -> None:
    doc = {
        "status": status,
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "analysis": str(layout.analysis_doc(run_dir).relative_to(run_dir)),
        "checks": [c.to_dict() for c in results],
    }
    problems = validate_report(doc)
    assert not problems, f"验证能力自己写的报告不合 schema：{problems}"
    path = layout.verify_report(run_dir)
    path.parent.mkdir()
    path.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")
