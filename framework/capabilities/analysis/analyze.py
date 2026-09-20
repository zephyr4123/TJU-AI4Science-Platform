"""分析能力：把几次实验的账本、笔记、diff 与结果清单交给执行层，收回一份形状合约的 analysis.md。

零模型调用：这里只负责收集输入、组 prompt、起一次执行层会话、校验产物**形状**。
数字对不对不在这里判——分析能力不判自己产物对不对（P-2），回溯是验证能力的事。
所以产物合约只有两条：三节齐全、数据表至少一行能解析（`experiment.analysis`）。

输入全部从 `--from` 点名的实验产出目录读（一次或几次实验，纲领 P-19 的多对多）。账本给全部行而不是
尾部：内环每轮只需要最近几轮，分析要看全貌，两者的 P-9 边界不同。
"""

from __future__ import annotations

import logging
import math
from pathlib import Path

from backends import RunResult
from framework import skills
from framework.contracts.capability import CapabilityFailed, Inputs, Ports
from framework.executor import prompting, session
from framework.experiment import artifacts, gitwork, layout, ledger, notebook
from framework.experiment.analysis import parse_claims, validate_analysis
from framework.experiment.checkpoint import read_checkpoint
from framework.experiment.context import (
    DIRECTION_ZH,
    load_scoring,
    read_domain,
    read_domain_extra,
    read_question,
)
from framework.experiment.pack import primary_metric
from framework.experiment.results import read_metrics

LOGGER = logging.getLogger("ai4sci.analysis")
DOC_NAME = "analysis.md"
LOG_DIRNAME = "executor"
PROMPT_TEMPLATE = Path(__file__).resolve().parent / "prompt.md"
DIFF_MAX_CHARS = 20_000  # 基线到 best 的 diff 超过这个长度就截断：分析看的是改法，不是每一行


def analyze(output_dir: Path, inputs: Inputs, ports: Ports) -> str:
    output_dir = Path(output_dir).resolve()
    assert ports.runner is not None, "分析能力要执行层端口"
    experiment_ids = [i for i in inputs.ids if i.startswith("experiment/")]
    runs = list(zip(inputs.of_stage("experiment"), experiment_ids, strict=True))
    if not runs:
        raise CapabilityFailed("分析要读实验的产出：--from experiment/<n>（可以几个）")
    for run_dir, oid in runs:
        if not ledger.read(layout.ledger(run_dir)):
            raise CapabilityFailed(f"{oid} 还没有跑过任何一轮，没有可分析的账本")
    prompt = prompting.build_prompt(PROMPT_TEMPLATE, _prompt_values(runs),
                                    read_domain_extra(runs[0][0]),
                                    skills.for_executor(read_domain(runs[0][0])))
    result = session.run_session(
        ports.runner, prompt, cwd=output_dir, allowed_paths=[output_dir],
        log_dir=output_dir / LOG_DIRNAME,
    )
    claims = _check_outcome(output_dir, result)
    LOGGER.info("analysis_done out=%s claims=%d cost_usd=%s duration_s=%.1f",
                output_dir, len(claims), result.cost_usd, result.duration_s)
    cost = "nan" if math.isnan(result.cost_usd) else f"{result.cost_usd:.4f}"
    return f"analysis ok\tclaims={len(claims)}\tcost_usd={cost}\tpath={DOC_NAME}"


def _check_outcome(output_dir: Path, result: RunResult) -> list:
    """事后判定，顺序固定：先判越界，再判会话死没死，最后判产物形状。文件一律留着当证据。"""
    outside = [f for f in result.changed_files
               if f != DOC_NAME and not f.startswith(f"{LOG_DIRNAME}/")]
    if outside:
        raise CapabilityFailed(f"执行层改了 {DOC_NAME} 之外的文件：{', '.join(sorted(outside))}")
    if result.timed_out or result.exit_code != 0:
        tail = result.stdout_tail.strip().splitlines()
        why = "超时" if result.timed_out else f"退出码 {result.exit_code}"
        raise CapabilityFailed(f"执行层会话没走完（{why}）：{tail[-1] if tail else '无输出'}")
    doc = output_dir / DOC_NAME
    if not doc.is_file():
        raise CapabilityFailed(f"执行层没有写出 {DOC_NAME}")
    text = doc.read_text(encoding="utf-8")
    problems = validate_analysis(text)
    if problems:
        raise CapabilityFailed("analysis.md 不合约：" + "；".join(problems))
    claims, _ = parse_claims(text)
    return claims


def _prompt_values(runs: list[tuple[Path, str]]) -> dict[str, object]:
    first_dir, _ = runs[0]
    scoring = load_scoring(first_dir)
    metric = primary_metric(scoring)
    return {
        "question": read_question(first_dir),
        "metric_name": metric["name"], "direction": metric["direction"],
        "direction_zh": DIRECTION_ZH[metric["direction"]],
        "experiments": "\n\n".join(_experiment_block(d, oid, metric["name"]) for d, oid in runs),
    }


def _experiment_block(run_dir: Path, oid: str, metric_name: str) -> str:
    rows = ledger.read(layout.ledger(run_dir))
    state = read_checkpoint(run_dir)
    work = layout.work(run_dir)
    listing, baseline = _results_listing(run_dir, oid, metric_name)
    base_commit = gitwork.root_commit(work)
    best_commit = state["best_commit"]
    diff = (gitwork.diff_full(work, base_commit, best_commit, DIFF_MAX_CHARS)
            if base_commit and best_commit != base_commit else "（best 就是基线，没有代码差异）")
    return "\n".join([
        f"## 实验 `{oid}`",
        "",
        f"- 基线（{oid}/baseline）：**{baseline}**",
        f"- 当前最好：**{_fmt(state['best_metric'])}**（第 {state['best_iter']} 轮）；"
        f"共跑 {len(rows)} 轮，留下 {sum(r.status == 'keep' for r in rows)} 轮",
        "",
        "### 账本（旧 → 新，一行一轮：轮次 / 裁决 / 指标 / 备注）",
        "",
        "\n".join(_ledger_line(r) for r in rows),
        "",
        "### 实验笔记（每轮的假设、改动、裁决）",
        "",
        notebook.read(layout.notebook(run_dir)) or "（没有笔记）",
        "",
        "### 基线到 best 的代码差异",
        "",
        "```diff",
        diff or "（没有代码差异）",
        "```",
        "",
        "### 结果清单（数据表只许从这里抄，原样抄，不四舍五入）",
        "",
        listing,
    ])


def _results_listing(run_dir: Path, oid: str, metric_name: str) -> tuple[str, str]:
    """每一轮的全部指标一行一条，值用 repr 原样给；返回（清单, 基线主指标）。
    来源写成 `<实验 id>/<轮>`。"""
    lines: list[str] = []
    baseline = "未知"
    for name, path in artifacts.run_results(run_dir).items():
        metrics, problems = read_metrics(path)
        source = f"{oid}/{name}"
        if metrics is None:
            lines.append(f"- {source}：无结果（{'；'.join(problems)}）")
            continue
        lines.append(f"- {source}：" + "，".join(f"{k} = {v!r}" for k, v in metrics.items()))
        if name == layout.BASELINE_KEY and metric_name in metrics:
            baseline = repr(metrics[metric_name])
    return "\n".join(lines) or "（没有任何 results.json）", baseline


def _ledger_line(row: ledger.LedgerRow) -> str:
    metric = "-" if row.metric is None else repr(row.metric)
    return f"- 第 {row.iter} 轮：{row.status}，{metric}，{row.note or '-'}"


def _fmt(value: float | None) -> str:
    return "未知" if value is None else repr(float(value))
