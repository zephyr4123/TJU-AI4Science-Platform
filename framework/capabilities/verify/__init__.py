"""核对数字：验证阶段里现有的一个能力——零模型，对分析初稿做数字回溯与账本对账，写 `report.json`。

一个能力一个子包，互不 import。它读分析能力与实验能力的产物但不 import 它们：三边共用的只有
`experiment.analysis`（数据表解析）与 `experiment.artifacts`（结果索引）。

判决语义：报告永远写出来（PASS 与 FAIL 都要留档），FAIL 再 raise `CapabilityFailed`——
协调层看到的退出码就是"过没过"，报告是细节（P-7 fail-closed：验证不过就停）。
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from pathlib import Path

from framework.capabilities.verify import checks
from framework.contracts.capability import Capability, CapabilityFailed, Inputs, Param, Ports
from framework.experiment.report import validate_report

__all__ = ["DESCRIPTOR", "run"]

LOGGER = logging.getLogger("ai4sci.verify")
NAME = "verify"
REPORT_NAME = "report.json"
ANALYSIS_DOC = "analysis.md"
DEFAULT_TOLERANCE = 0.01  # spec A-10：1% 容差

DESCRIPTOR = Capability(
    name="verify",
    stage="验证",
    title="数字核对",
    brief="把分析里的每个数回溯到结果文件，账本对 git 历史",
    does=(
        "不经模型。读点名的分析产出里的 analysis.md，把数据表每一行 (来源, 指标, 值)"
        " 回溯到那次实验那一轮的 results.json——相对误差在容差内才算找到；"
        "正文里每个带小数点或指数的数都得出现在数据表里；"
        "再把每次实验的 ledger.tsv 与 work/ 的 git 对账：每行 commit 在仓里找得到、"
        "keep 行沿分支链接得上。每项检查记 passed 与 details，合成 report.json，"
        "status 是 PASS 或 FAIL。"
    ),
    does_not=(
        "不判结论对不对、不重跑任何实验、不读代码：它只回答「分析里的数是不是从结果文件抄的、"
        "账本与代码历史对不对得上」。不替人验收——验收是人确认。"
    ),
    brings=(
        "一次分析产出与它分析的那几次实验产出（分析读了谁就带谁）："
        "analysis.md、iters/iter_N/results.json、ledger.tsv、work/（git 仓）。"
    ),
    leaves="report.json（PASS 与 FAIL 都写）。",
    stops=(
        "报告写完就退出。FAIL 时退非零、结论行说哪项没过（验证不过就停，不放行）；"
        "analysis.md 不在就直接判失败。"
    ),
    params=(
        Param("tolerance", "float", DEFAULT_TOLERANCE, "数字回溯的相对容差：相对误差在它之内算找到",
              "容差"),
    ),
)


def run(output_dir: Path, inputs: Inputs, ports: Ports, *,
        tolerance: float = DEFAULT_TOLERANCE) -> str:
    output_dir = Path(output_dir).resolve()
    assert 0 <= tolerance < 1, f"tolerance 要在 [0, 1) 之间，得到 {tolerance!r}"
    analysis_dir = inputs.one_of("analysis", "验证")
    experiments = dict(zip([i for i in inputs.ids if i.startswith("experiment/")],
                           inputs.of_stage("experiment"), strict=True))
    if not experiments:
        raise CapabilityFailed("验证要带上分析读过的那几次实验：--from experiment/<n>")
    results = _run_checks(analysis_dir, experiments, tolerance)
    status = "PASS" if all(c.passed for c in results) else "FAIL"
    _write_report(output_dir, status, results, inputs)
    failed = [c for c in results if not c.passed]
    LOGGER.info("verify_done out=%s status=%s failed=%s", output_dir, status,
                [c.name for c in failed])
    if failed:
        first = failed[0]
        raise CapabilityFailed(
            f"verify FAIL {len(failed)}/{len(results)}：{first.name}："
            f"{'；'.join(first.details[:3])}（全部细节见 {REPORT_NAME}）")
    return f"verify PASS\tchecks={len(results)}\tpath={REPORT_NAME}"


def _run_checks(analysis_dir: Path, experiments: dict[str, Path],
                tolerance: float) -> list[checks.Check]:
    doc = analysis_dir / ANALYSIS_DOC
    present = checks.analysis_present(doc)
    if not present.passed:
        # 没有分析就没有可回溯的东西，别再对着空文件报一串"表不存在"
        return [present]
    text = doc.read_text(encoding="utf-8")
    out = [present, checks.numbers_traceable(experiments, text, tolerance),
           checks.prose_numbers_in_table(text, tolerance)]
    out += [checks.ledger_reconciled(oid, run_dir) for oid, run_dir in experiments.items()]
    return out


def _write_report(output_dir: Path, status: str, results: list[checks.Check],
                  inputs: Inputs) -> None:
    doc = {
        "status": status,
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "analysis": next(i for i in inputs.ids if i.startswith("analysis/")),
        "checks": [c.to_dict() for c in results],
    }
    problems = validate_report(doc)
    assert not problems, f"验证能力自己写的报告不合 schema：{problems}"
    (output_dir / REPORT_NAME).write_text(json.dumps(doc, ensure_ascii=False, indent=2),
                                          encoding="utf-8")
