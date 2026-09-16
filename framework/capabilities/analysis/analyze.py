"""分析能力：把一个 run 的账本、笔记、diff 与结果清单交给执行层，收回一份形状合约的 analysis.md。

零模型调用：这里只负责收集输入、组 prompt、起一次执行层会话、校验产物**形状**。
数字对不对不在这里判——分析能力不当自己产物的裁判（P-2），回溯是验证能力的事。
所以产物合约只有两条：三节齐全、数据表至少一行能解析（`contracts.analysis`）。

输入全部从 run 目录读，不回头看任务包（纲领磁盘布局）。账本给全部行而不是尾部：
内环每轮只需要最近几轮，分析要看全貌，两者的 P-9 边界不同。
"""

from __future__ import annotations

import logging
import math
from pathlib import Path

from backends import RunResult
from framework.contracts.analysis import parse_claims, validate_analysis
from framework.contracts.capability import CapabilityFailed, Ports
from framework.contracts.results import read_metrics
from framework.executor import prompting, session
from framework.memory import ledger, notebook
from framework.run import artifacts, gitwork, layout
from framework.run.checkpoint import read_checkpoint
from framework.run.context import load_manifest, primary_metric, read_domain_extra
from framework.run.lifecycle import rotate_capability_dir

LOGGER = logging.getLogger("ai4sci.analysis")
NAME = "analysis"
PROMPT_TEMPLATE = Path(__file__).resolve().parent / "prompt.md"
DIFF_MAX_CHARS = 20_000  # 基线到 best 的 diff 超过这个长度就截断：分析看的是改法，不是每一行


def analyze(run_dir: Path, ports: Ports) -> str:
    run_dir = Path(run_dir).resolve()
    assert ports.runner is not None, "分析能力要执行层端口"
    rows = ledger.read(layout.ledger(run_dir))
    if not rows:
        raise CapabilityFailed("还没有跑过实验，没有可分析的账本")
    archived = rotate_capability_dir(run_dir, NAME)
    out_dir = layout.capability_dir(run_dir, NAME)
    out_dir.mkdir()
    prompt = prompting.build_prompt(PROMPT_TEMPLATE, _prompt_values(run_dir, rows),
                                    read_domain_extra(run_dir))
    result = session.run_session(
        ports.runner, prompt, cwd=run_dir, allowed_paths=[out_dir],
        log_dir=out_dir / "executor",
    )
    claims = _check_outcome(run_dir, result)
    LOGGER.info("analysis_done run_dir=%s claims=%d cost_usd=%s duration_s=%.1f archived=%s",
                run_dir, len(claims), result.cost_usd, result.duration_s,
                archived.name if archived else "-")
    cost = "nan" if math.isnan(result.cost_usd) else f"{result.cost_usd:.4f}"
    doc_rel = layout.analysis_doc(run_dir).relative_to(run_dir)
    return f"analysis ok\tclaims={len(claims)}\tcost_usd={cost}\tpath={doc_rel}"


def _check_outcome(run_dir: Path, result: RunResult) -> list:
    """事后判定，顺序固定：先判越界，再判会话死没死，最后判产物形状。文件一律留着当证据。"""
    outside = [f for f in result.changed_files if not f.startswith(f"{NAME}/")]
    if outside:
        raise CapabilityFailed(f"执行层改了 {NAME}/ 之外的文件：{', '.join(sorted(outside))}")
    if result.timed_out or result.exit_code != 0:
        tail = result.stdout_tail.strip().splitlines()
        why = "超时" if result.timed_out else f"退出码 {result.exit_code}"
        raise CapabilityFailed(f"执行层会话没走完（{why}）：{tail[-1] if tail else '无输出'}")
    doc = layout.analysis_doc(run_dir)
    if not doc.is_file():
        raise CapabilityFailed(f"执行层没有写出 {doc.relative_to(run_dir)}")
    text = doc.read_text(encoding="utf-8")
    problems = validate_analysis(text)
    if problems:
        raise CapabilityFailed("analysis.md 不合约：" + "；".join(problems))
    claims, _ = parse_claims(text)
    return claims


def _prompt_values(run_dir: Path, rows: list[ledger.LedgerRow]) -> dict[str, object]:
    manifest = load_manifest(run_dir)
    metric = primary_metric(manifest)
    state = read_checkpoint(run_dir)
    work = layout.work(run_dir)
    listing, baseline = _results_listing(run_dir, metric["name"])
    base_commit = gitwork.root_commit(work)
    best_commit = state["best_commit"]
    diff = (gitwork.diff_full(work, base_commit, best_commit, DIFF_MAX_CHARS)
            if base_commit and best_commit != base_commit else "（best 就是基线，没有代码差异）")
    return {
        "run_id": state["run_id"], "question": manifest["question"],
        "metric_name": metric["name"], "direction": metric["direction"],
        "direction_zh": prompting.DIRECTION_ZH[metric["direction"]],
        "baseline_metric": baseline, "best_metric": _fmt(state["best_metric"]),
        "best_iter": state["best_iter"], "total_iters": len(rows),
        "keep_count": sum(r.status == "keep" for r in rows),
        "ledger_table": "\n".join(_ledger_line(r) for r in rows),
        "notebook": notebook.read(layout.notebook(run_dir)) or "（没有笔记）",
        "best_diff": diff or "（没有代码差异）", "results_listing": listing,
    }


def _results_listing(run_dir: Path, metric_name: str) -> tuple[str, str]:
    """每个 run 的全部指标一行一条，值用 repr 原样给；返回（清单, 基线主指标）。"""
    lines: list[str] = []
    baseline = "未知"
    for name, path in artifacts.run_results(run_dir).items():
        metrics, problems = read_metrics(path)
        if metrics is None:
            lines.append(f"- {name}：无结果（{'；'.join(problems)}）")
            continue
        lines.append(f"- {name}：" + "，".join(f"{k} = {v!r}" for k, v in metrics.items()))
        if name == "run_0" and metric_name in metrics:
            baseline = repr(metrics[metric_name])
    return "\n".join(lines) or "（没有任何 results.json）", baseline


def _ledger_line(row: ledger.LedgerRow) -> str:
    metric = "-" if row.metric is None else repr(row.metric)
    return f"- 第 {row.iter} 轮：{row.status}，{metric}，{row.note or '-'}"


def _fmt(value: float | None) -> str:
    return "未知" if value is None else repr(float(value))
