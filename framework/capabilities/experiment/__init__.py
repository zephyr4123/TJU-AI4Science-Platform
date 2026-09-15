"""实验内环：唯一有循环的能力（纲领 workflow.md §2）。

一个能力一个子包，跑完即退、互不 import（见 `capabilities/__init__.py`）。对外露的是
描述符 `DESCRIPTOR`、统一入口 `run`（`ai4sci cap experiment` 走它）、内环自己的两个动作
`run_loop` / `resume_loop`（`ai4sci loop run|resume` 走它们，resume 有三方对账，不是一个参数
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

__all__ = ["DESCRIPTOR", "InflightPending", "ResumeMismatch", "StopReason", "resume_loop",
           "run", "run_loop"]

DESCRIPTOR = Capability(
    name="experiment",
    level="run",
    summary="实验内环：执行层每轮改 code/，harness 独立跑分，统计门棘轮，账本与 git 对账",
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
    ),
    needs_executor=True,
    needs_compute=True,
    criteria=(
        "每个 keep 行的差值大于统计门 max(accept_sigma × σ, min_delta)",
        "账本每行的 commit 在 git 里找得到，keep 行在分支上、其余在 refs/attempts/ 下",
        "harness 目录 hash 不变；越界改动判 readonly_violated 并回滚",
    ),
)


def run(run_dir: Path, ports: Ports, *, max_iters: int | None = None) -> str:
    """统一入口：等价于 `ai4sci loop run`。续跑走 `resume_loop`，不在这里。"""
    assert ports.runner is not None and ports.compute is not None, "实验能力要执行层与算力两个端口"
    try:
        stop = run_loop(run_dir, ports.runner, ports.compute, max_iters)
    except (ResumeMismatch, InflightPending) as exc:
        # 通用驱动只认能力契约里的异常；内环自己的两种"现状不许往下跑"原话照转
        raise CapabilityFailed(str(exc)) from exc
    return f"stop {stop.reason}\titer={stop.iter}\tbest={stop.best_metric}"
