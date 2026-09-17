"""实验内环：唯一有循环的能力（纲领 workflow.md §2）。

一个能力一个子包，跑完即退、互不 import（见 `capabilities/__init__.py`）。对外露的是
描述符 `DESCRIPTOR`、统一入口 `run`（`ai4sci cap experiment` 走它）、内环自己的两个动作
`run_loop` / `resume_loop`（`ai4sci cap experiment [--resume]` 走它们，resume 有三方对账
能表达的事），以及三种"停下来"的表达。内部怎么分模块（loop / judge / gate / failures /
prompt.md）是这个能力自己的事，别的层不该知道。
"""

from __future__ import annotations

from pathlib import Path

from framework.capabilities.experiment.loop import (
    InflightPending,
    ResumeMismatch,
    StopReason,
    resume_loop,
    run_loop,
)
from framework.contracts.capability import Artifact, Capability, CapabilityFailed, Param, Ports
from framework.run.lifecycle import extend_run

__all__ = ["DESCRIPTOR", "InflightPending", "ResumeMismatch", "StopReason", "resume_loop",
           "run", "run_loop"]

DESCRIPTOR = Capability(
    name="experiment",
    level="run",
    summary="实验内环：执行层每轮改 code/，harness 独立跑分，统计门棘轮，账本与 git 对账",
    stage="实验",
    title="一轮一轮改",
    what="每轮改一次代码，裁判脚本独立跑分，成绩好过噪声门槛才留下，否则退回上一版。到了轮数、花费或连续没进步的上限就停。",
    inputs=(
        Artifact("manifest", "manifest.yaml", "任务包 manifest 的快照：指标、方向、预算、统计门"),
        Artifact("work", "work/", "任务包拷贝，独立 git 仓，分支 tip 是 best"),
    ),
    outputs=(
        Artifact("ledger", "experiment/ledger.tsv", "账本：每轮一行，与 git 对账"),
        Artifact("notebook", "experiment/notebook.md", "实验笔记：每轮自述、改动、裁决"),
        Artifact("runs", "experiment/runs/", "每轮快照 run_N/ 与 harness 的 results.json"),
        Artifact("checkpoint", "checkpoint.json", "best 与停止原因"),
    ),
    params=(
        Param("max_iters", "int", None,
              "本次增量最多跑几轮；上限仍是 manifest 的 budget.max_iterations"),
        Param("resume", "bool", False,
              "上次被杀在半路：先做 checkpoint × 账本 × git 三方对账，收尸后接着跑"),
        Param("patience", "int", None, "续命：连续不改进几轮才停（改快照里的预算，清停止标记）"),
        Param("max_iterations", "int", None, "续命：总轮数上限"),
        Param("max_cost_usd", "float", None, "续命：总花费上限"),
        Param("reason", "str", "", "续命的原因，记进 journal.md"),
    ),
    needs_executor=True,
    needs_compute=True,
    criteria=(
        "每个 keep 行的差值大于统计门 max(accept_sigma × σ, min_delta)",
        "账本每行的 commit 在 git 里找得到，keep 行在分支上、其余在 refs/attempts/ 下",
        "harness 目录 hash 不变；越界改动判 readonly_violated 并回滚",
    ),
)


def run(
    run_dir: Path, ports: Ports, *, max_iters: int | None = None, resume: bool = False,
    patience: int | None = None, max_iterations: int | None = None,
    max_cost_usd: float | None = None, reason: str = "",
) -> str:
    """统一入口。给了预算参数先续命（`lifecycle.extend_run`：改预算、清停止标记、journal 记一行），
    `resume` 走三方对账的 `resume_loop`，否则 `run_loop`。"""
    assert ports.runner is not None and ports.compute is not None, "实验能力要执行层与算力两个端口"
    if patience is not None or max_iterations is not None or max_cost_usd is not None:
        extend_run(run_dir, patience=patience, max_iterations=max_iterations,
                   max_cost_usd=max_cost_usd, reason=reason)
    elif reason:
        raise CapabilityFailed(
            "--reason 只在续命时有意义：配 --patience / --max-iterations / --max-cost-usd")
    go = resume_loop if resume else run_loop
    try:
        stop = go(run_dir, ports.runner, ports.compute, max_iters)
    except (ResumeMismatch, InflightPending) as exc:
        # 通用驱动只认能力契约里的异常；内环自己的两种"现状不许往下跑"原话照转
        raise CapabilityFailed(str(exc)) from exc
    return f"stop {stop.reason}\titer={stop.iter}\tbest={stop.best_metric}"
