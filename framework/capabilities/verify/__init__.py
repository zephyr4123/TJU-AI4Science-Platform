"""核对数字：验证间里现有的一颗能力——零模型，对分析初稿做数字回溯与账本对账，写
`verify/report.json`。

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
from framework.contracts.capability import Capability, CapabilityFailed, Param, Ports
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
    stage="验证",
    title="核对数字",
    does=(
        "零模型。读 analysis/analysis.md，把数据表每一行 (run, 指标, 值)"
        " 回溯到那个 run 的 results.json——相对误差在容差内才算找到；"
        "正文里每个带小数点或指数的数都得出现在数据表里；"
        "再把 experiment/ledger.tsv 与 work/ 的 git 对账：每行 commit 在仓里找得到、"
        "keep 行沿分支链接得上。每项检查记 passed 与 details，合成 verify/report.json，"
        "status 是 PASS 或 FAIL。"
    ),
    does_not=(
        "不判结论对不对、不重跑任何实验、不读代码：它只回答「分析里的数是不是从结果文件抄的、"
        "账本与代码历史对不对得上」。不替人验收——验收是人确认的。"
    ),
    brings=(
        "analysis/analysis.md、experiment/runs/run_N/results.json、experiment/ledger.tsv、"
        "work/（git 仓）。"
    ),
    leaves=(
        "verify/report.json（PASS 与 FAIL 都写）；重跑时旧的改名成 verify_v1/ 留档。"
    ),
    stops=(
        "报告写完就退出。FAIL 时退非零、结论行说哪项没过（fail-closed：验证不过就停，P-7）；"
        "analysis.md 不在就直接判失败。"
    ),
    params=(
        Param("tolerance", "float", DEFAULT_TOLERANCE, "数字回溯的相对容差，缺省 0.01（1%）"),
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
