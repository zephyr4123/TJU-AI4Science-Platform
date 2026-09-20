"""auto-research：实验阶段的那个能力——读设计的产出开一次实验，然后一轮一轮改代码，统计门棘轮
（workflow.md §2）。

一个能力一个子包，跑完即退、互不 import（见 `capabilities/__init__.py`）。对外露的是描述符
`DESCRIPTOR`、统一入口 `run`（`ai4sci cap auto-research` 走它）、内环自己的两个动作 `run_loop` /
`resume_loop`，以及三种"停下来"的表达。内部怎么分模块（open / loop / judge / gate / failures /
prompt.md）是这个能力自己的事，别的层不该知道。

纯函数（P-19）：`--from design/<n>` 是它读的那包（scoring.yaml、harness、code、env、baseline），
产出是 `experiment/<n>/`。它是 continuable 的：一批一批跑（`--max-iters`）、被杀在半路续跑
（`--resume`）、停了加预算都是接着同一次产出干（`--continue experiment/<n>`），不另开目录——
那些是同一次实验的后续，不是新实验。
"""

from __future__ import annotations

import os
from pathlib import Path

from framework.capabilities.auto_research.loop import (
    InflightPending,
    ResumeMismatch,
    StopReason,
    resume_loop,
    run_loop,
)
from framework.capabilities.auto_research.open import (
    EnvBuildError,
    PackInvalid,
    extend_experiment,
    open_experiment,
)
from framework.contracts import requirement
from framework.contracts.capability import Capability, CapabilityFailed, Inputs, Param, Ports
from framework.experiment import layout
from framework.workspace.jobs import CHAT_ID_ENV

__all__ = ["DESCRIPTOR", "InflightPending", "ResumeMismatch", "StopReason", "resume_loop",
           "run", "run_loop"]

NAME = "auto-research"
DESCRIPTOR = Capability(
    name=NAME,
    stage="实验",
    title="AutoResearch",
    brief="在封好的评分脚本上自动迭代代码，逐轮记账",
    does=(
        "第一次调用先开实验：把设计阶段的产出复制进 work/、按 lock 建独立环境、"
        "work/ 起一个 git 仓，"
        "基线成绩记进 checkpoint.json；scoring.yaml 与需求各快照一份。"
        "然后一轮一轮改：每轮起一个新的执行层会话，只给它账本、实验笔记与 work/ 的代码，"
        "让它改一版 code/ 并自述改了什么；框架把这一版交给算力独立跑 harness 打分，"
        "拿到 results.json 后过统计门——比 best 好、"
        "且差值超过 max(accept_sigma × σ, min_delta) 才算改进。改进就 keep：commit 进分支、"
        "分支 tip 前移成新的 best；没改进就 discard：这次尝试留档、work/ 硬回退到 best。"
        "账本 ledger.tsv 每轮一行（commit、指标、σ、耗时、花费、裁决），"
        "实验笔记 notebook.md 每轮一段，下一轮整本进提示。"
    ),
    does_not=(
        "不修改 harness/（每轮核对，改了就回滚并判失败）、"
        "不改 scoring 快照里的指标与预算（加预算续跑除外）、不写分析、"
        "不判结果可不可信——它只负责让分支 tip 永远是目前最好的那一版。"
    ),
    brings=(
        "设计阶段跑过基线的那次产出：harness/（封好的评分脚本）、code/（基线代码）、"
        "baseline/（基线成绩与 σ）、scoring.yaml（指标、方向、budget：max_iterations、patience、"
        "max_cost_usd、inner_k、统计门）、env/。接着跑就接着上一次的实验产出；"
        "被杀在半路先对账再续；已停的要加预算续跑，带原因。"
    ),
    leaves=(
        "experiment/<n>/：scoring.yaml 与 requirement.md 快照、work/（独立 git 仓，"
        "分支 tip 是 best，被弃的尝试留档在仓里）、checkpoint.json（last_iter、best_iter、"
        "best_metric、best_commit、stop_reason）、ledger.tsv、notebook.md、"
        "iters/iter_N/（每轮的代码快照与 results.json）、journal.md（协调层的记录）。"
    ),
    stops=(
        "到了 budget.max_iterations，或连续 patience 轮没改进，或累计花费过了 max_cost_usd，"
        "或执行层连续几轮不可修复地失败——停止原因写进 checkpoint 与 stop.json。"
        "给了本次轮数就只跑这么多轮再退出（实验不算停，下次接着跑）。"
        "开实验那一步就拒的情况：设计那次产出不合约、预检说没有改进空间、环境建不出来——"
        "前置检查失败就不开，不留半截。"
    ),
    params=(
        Param("max_iters", "int", None,
              "本次增量最多跑几轮；上限仍是 scoring 的 budget.max_iterations", "本次轮数"),
        Param("resume", "bool", False,
              "上次被杀在半路：先做 checkpoint × 账本 × git 三方对账，收拾好接着跑", "续跑",
              in_flow=False),
        Param("patience", "int", None, "加预算：连续不改进几轮才停（改快照里的预算，清停止标记）",
              "耐心轮数"),
        Param("max_iterations", "int", None, "加预算：总轮数上限", "总轮数上限"),
        Param("max_cost_usd", "float", None, "加预算：总花费上限（美元）", "花费上限"),
        Param("reason", "str", "", "加预算的原因，记进 journal.md", "加预算的原因", in_flow=False),
    ),
    needs_executor=True,
    needs_compute=True,
    continuable=True,
)


def run(
    output_dir: Path, inputs: Inputs, ports: Ports, *, max_iters: int | None = None,
    resume: bool = False, patience: int | None = None, max_iterations: int | None = None,
    max_cost_usd: float | None = None, reason: str = "",
) -> str:
    """统一入口。产出目录还没铺就开实验（读 --from 的设计那包）；铺过（--continue）就按参数加预算
    （`extend_experiment`）、三方对账续跑（`resume_loop`）或直接接着跑（`run_loop`）。"""
    assert ports.runner is not None and ports.compute is not None, (
        "auto-research 要执行层与算力两个端口")
    output_dir = Path(output_dir).resolve()
    opened = layout.checkpoint(output_dir).is_file()
    extending = patience is not None or max_iterations is not None or max_cost_usd is not None
    if not opened:
        if resume or extending or reason:
            raise CapabilityFailed(
                "--resume 与加预算参数只对已经开过的实验有意义：带 --continue experiment/<n>")
        pack = inputs.one_of("design", "开实验")
        try:
            open_experiment(output_dir, pack, requirement.path(inputs.workspace),
                            output_id=f"experiment/{output_dir.name}", compute=ports.compute,
                            compute_label=ports.compute_label,
                            chat_id=os.environ.get(CHAT_ID_ENV))
        except (PackInvalid, EnvBuildError) as exc:
            raise CapabilityFailed(str(exc)) from exc
    if extending:
        extend_experiment(output_dir, patience=patience, max_iterations=max_iterations,
                          max_cost_usd=max_cost_usd, reason=reason)
    elif reason:
        raise CapabilityFailed(
            "--reason 只在加预算时有意义：配 --patience / --max-iterations / --max-cost-usd")
    go = resume_loop if resume else run_loop
    try:
        stop = go(output_dir, ports.runner, ports.compute, max_iters)
    except (ResumeMismatch, InflightPending) as exc:
        # 通用驱动只认能力契约里的异常；内环自己的两种"现状不许往下跑"原话照转
        raise CapabilityFailed(str(exc)) from exc
    oid = f"experiment/{output_dir.name}"
    return (f"stop {stop.reason}\titer={stop.iter}\tbest={stop.best_metric}\toutput={oid}"
            f"\tnext=ai4sci cap analysis --from {oid}")
