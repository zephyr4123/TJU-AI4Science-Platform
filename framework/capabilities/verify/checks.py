"""验证能力的检查项：每项一个函数，输入是分析与实验的产出，输出一份 `Check`。

零模型、确定性（纲领 workflow.md §3 的零 LLM 判据）。每项只回答一个问题，
细节一行一条写给协调层看；不在这里决定"整体过不过"，那是把全部 Check 合起来的事。

数字回溯的尺子：|声称 − 实际| ≤ tolerance × |实际|；实际是 0 时声称也必须是 0。
整数与百分比不查——前者是计数，后者是相对变化，没有绝对来源（`experiment.analysis` 的边界）。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from framework.experiment import artifacts, layout, ledger
from framework.experiment.analysis import Claim, parse_claims, prose_numbers
from framework.experiment.results import read_metrics


@dataclass
class Check:
    name: str
    passed: bool
    details: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        return {"name": self.name, "passed": self.passed, "details": list(self.details)}


def analysis_present(doc: Path) -> Check:
    if doc.is_file() and doc.read_text(encoding="utf-8").strip():
        return Check("analysis_present", True, [doc.name])
    return Check("analysis_present", False, [f"{doc.name} 不存在或为空"])


def numbers_traceable(experiments: dict[str, Path], text: str, tolerance: float) -> Check:
    """数据表每一行 (来源, 指标, 值) 都能在那次实验那一轮的 results.json 里找到。"""
    claims, problems = parse_claims(text)
    details = list(problems)
    sources = _load_sources(experiments)
    for claim in claims:
        actual = sources.get(claim.source, {}).get(claim.metric)
        if actual is None:
            details.append(f"第 {claim.line_no} 行：{claim.source} 没有指标 {claim.metric} 的结果")
        elif not _close(claim.value, actual, tolerance):
            details.append(f"第 {claim.line_no} 行：{claim.source} 的 {claim.metric} 声称 "
                           f"{claim.value!r}，实际 {actual!r}，超出 {tolerance:.0%} 容差")
    if not claims and not details:
        details.append("数据表一行都没有")
    passed = bool(claims) and not details
    if passed:
        details.append(f"核对 {len(claims)} 个值，全部在 {tolerance:.0%} 容差内")
    return Check("numbers_traceable", passed, details)


def prose_numbers_in_table(text: str, tolerance: float) -> Check:
    """正文里带小数点或指数的数，必须与数据表里某个值在容差内相等：不许在表外编数字。"""
    claims, _ = parse_claims(text)
    values = [c.value for c in claims]
    details = [
        f"第 {n.line_no} 行：{n.token} 不在数据表里"
        for n in prose_numbers(text)
        if not any(_close(n.value, v, tolerance) for v in values)
    ]
    if not details:
        details.append(f"正文 {len(prose_numbers(text))} 个小数都在数据表里")
        return Check("prose_numbers_in_table", True, details)
    return Check("prose_numbers_in_table", False, details)


def ledger_reconciled(oid: str, run_dir: Path) -> Check:
    """账本 × git 对账：分析引用的账本本身得是真的。复用内环那把尺子。"""
    problems = ledger.reconcile(layout.ledger(run_dir), layout.work(run_dir))
    if problems:
        return Check(f"ledger_reconciled:{oid}", False, problems)
    return Check(f"ledger_reconciled:{oid}", True, [f"{oid} 账本每行 commit 与 git 对得上"])


def _load_sources(experiments: dict[str, Path]) -> dict[str, dict[str, float]]:
    """来源（<实验 id>/<轮>）→ 指标 → 实际值；不合约的 results.json 不进来，
    回溯到它就是"没有结果"。"""
    sources: dict[str, dict[str, float]] = {}
    for oid, run_dir in experiments.items():
        for name, path in artifacts.run_results(run_dir).items():
            metrics, _ = read_metrics(path)
            if metrics is not None:
                sources[f"{oid}/{name}"] = metrics
    return sources


def _close(claimed: float, actual: float, tolerance: float) -> bool:
    if actual == 0:
        return claimed == 0
    return abs(claimed - actual) <= tolerance * abs(actual)


__all__ = ["Check", "Claim", "analysis_present", "ledger_reconciled", "numbers_traceable",
           "prose_numbers_in_table"]
