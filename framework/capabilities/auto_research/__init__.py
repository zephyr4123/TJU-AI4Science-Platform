"""auto-research：实验间的那颗能力——开一个 run，然后一轮一轮改代码，统计门棘轮（workflow.md §2）。

一个能力一个子包，跑完即退、互不 import（见 `capabilities/__init__.py`）。对外露的是描述符
`DESCRIPTOR`、统一入口 `run`（`ai4sci cap auto-research` 走它）、内环自己的两个动作 `run_loop` /
`resume_loop`，以及三种"停下来"的表达。内部怎么分模块（loop / judge / gate / failures / prompt.md）
是这个能力自己的事，别的层不该知道。

task 级：它动的是工作区——run 不在就从任务包建一个（`run/lifecycle.new_run`：钥匙、契约、预检、
拷 work/、建环境、git init、记基线），在就接着跑。原来「开一次实验」是单独一条命令（start），
2026-09-18 并进来（外层 #96）：开 run 只是内环开工前的准备，没有人开了 run 不跑。

照流：`--workflow <名>` 只在开 run 时认（工作区 `flows/` 里的实例，P-15），快照进 run；这颗能力
跑成之后自己把步序记到那条流上（run 级能力由 `cli/cap.py` 统一记，task 级的它知道 run 在哪、
只能自己记）。
"""

from __future__ import annotations

import os
from datetime import UTC, datetime
from pathlib import Path

from framework.capabilities.auto_research.loop import (
    InflightPending,
    ResumeMismatch,
    StopReason,
    resume_loop,
    run_loop,
)
from framework.contracts.capability import Capability, CapabilityFailed, Param, Ports
from framework.run import flow_state, jobs
from framework.run.lifecycle import EnvBuildError, NotPublished, TaskInvalid, extend_run, new_run
from framework.run.workspace import Workspace

__all__ = ["DESCRIPTOR", "InflightPending", "ResumeMismatch", "StopReason", "resume_loop",
           "run", "run_loop"]

NAME = "auto-research"
DESCRIPTOR = Capability(
    name=NAME,
    level="task",
    stage="实验",
    title="auto-research",
    does=(
        "先开一个 run：把任务包搬进 runs/<run_id>/work/、按 lock 建独立环境、"
        "work/ 起一个 git 仓，基线成绩记进 checkpoint.json（run 不在才建，在就接着跑）。"
        "然后一轮一轮改：每轮起一个新的执行层会话，只给它账本、实验笔记与 work/ 的代码，"
        "让它改一版 code/ 并自述改了什么；框架把这一版交给算力独立跑 harness 打分，"
        "拿到 results.json 后过统计门——比 best 好、"
        "且差值超过 max(accept_sigma × σ, min_delta) 才算改进。改进就 keep：commit 进分支、"
        "分支 tip 前移成新的 best；没改进就 discard：把这次尝试留档到 refs/attempts/ 下、"
        "work/ 硬回退到 best。账本 experiment/ledger.tsv 每轮一行（commit、指标、σ、耗时、"
        "花费、裁决），实验笔记 experiment/notebook.md 每轮一段，下一轮整本进提示。"
    ),
    does_not=(
        "不碰 harness/（目录 hash 每轮核对，越界改动判 readonly_violated 并回滚）、"
        "不改 manifest 快照里的指标与预算（续命除外）、不写分析、"
        "不判结果可不可信——它只负责让分支 tip 永远是目前最好的那一版。"
    ),
    brings=(
        "发布过、跑过基线的任务包：harness/（封好的裁判）、code/（基线代码）、"
        "run_0/（基线成绩与 σ）、manifest.yaml（指标、方向、budget：max_iterations、patience、"
        "max_cost_usd、inner_k、统计门）、env/。接着跑时带 --run-id；被杀在半路带 --resume；"
        "已停的 run 要续命带新的预算与 --reason。"
    ),
    leaves=(
        "runs/<run_id>/：manifest.yaml 快照、work/（独立 git 仓，分支 tip 是 best，"
        "refs/attempts/* 是被弃的尝试）、checkpoint.json（last_iter、best_iter、best_metric、"
        "best_commit、stop_reason）、experiment/ledger.tsv、experiment/notebook.md、"
        "experiment/runs/run_N/（每轮的代码快照与 results.json）、journal.md（协调层的本子）。"
    ),
    stops=(
        "到了 budget.max_iterations，或连续 patience 轮没改进，或累计花费过了 max_cost_usd，"
        "或执行层连续几轮不可修复地失败——停止原因写进 checkpoint 与 experiment/stop.json。"
        "给了 --max-iters 就只跑这么多轮再退出（run 不算停，下次接着跑）。"
        "开 run 那一步就拒的情况：需求没发布、任务包不合契约、预检说没有改进空间、"
        "环境建不出来——都停在门口，不留半截 run。"
    ),
    params=(
        Param("run_id", "str", "", "run 的名字；缺省 <工作区名>-<UTC 时间戳>。已有的 run 就接着跑"),
        Param("workflow", "str", "",
              "开 run 时照工作区里的哪条流（show flows 里的名字）：快照进 run，之后记走到哪一间"),
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
)


def run(
    workspace: Workspace, ports: Ports, *, run_id: str = "", workflow: str = "",
    max_iters: int | None = None, resume: bool = False, patience: int | None = None,
    max_iterations: int | None = None, max_cost_usd: float | None = None, reason: str = "",
) -> str:
    """统一入口。run 不在就建（可照流）；在就按参数续命（`lifecycle.extend_run`）、三方对账续跑
    （`resume_loop`）或直接接着跑（`run_loop`）。"""
    assert ports.runner is not None and ports.compute is not None, (
        "auto-research 要执行层与算力两个端口")
    run_id = run_id or f"{workspace.id}-{datetime.now(UTC):%Y%m%dT%H%M%SZ}"
    run_dir = workspace.runs / run_id
    extending = patience is not None or max_iterations is not None or max_cost_usd is not None
    if not run_dir.exists():
        if resume or extending or reason:
            raise CapabilityFailed(
                f"run {run_id!r} 还没开过：--resume 与续命参数只对已有的 run 有意义")
        run_dir = _open(workspace, run_id, workflow)
    elif workflow:
        raise CapabilityFailed(
            f"run {run_id!r} 已经开过了，照哪条流在开 run 时就定了；要换流就另开一个 run")
    if extending:
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
    # 照着流的 run：记它走到了实验这一间；没照流就不记
    flow_state.record_press(run_dir, NAME, DESCRIPTOR.stage)
    return (f"stop {stop.reason}\titer={stop.iter}\tbest={stop.best_metric}\trun={run_id}"
            f"\tnext=ai4sci cap analysis {run_id}")


def _open(workspace: Workspace, run_id: str, workflow: str) -> Path:
    """建 run；`workflow` 给了先核对名字，快照进 run。任何一道门没过都不留半截 run（P-7）。"""
    workflow_path = _flow_file(workspace, workflow) if workflow else None
    try:
        # 在对话里调用的：记下是哪段对话开的（适配器起会话时给的环境变量，与 --detach 记作业同源）
        run_dir = new_run(workspace.task, workspace.runs, run_id,
                          chat_id=os.environ.get(jobs.CHAT_ID_ENV))
    except (NotPublished, TaskInvalid, EnvBuildError, FileExistsError) as exc:
        raise CapabilityFailed(str(exc)) from exc
    if workflow_path is not None:
        flow_state.attach(run_dir, workflow_path, cap=NAME, stage=DESCRIPTOR.stage)
    return run_dir


def _flow_file(workspace: Workspace, name: str) -> Path:
    path = workspace.flows / f"{name}.yaml"
    if not path.is_file():
        available = ", ".join(sorted(p.stem for p in workspace.flows.glob("*.yaml"))) or "-"
        raise CapabilityFailed(
            f"工作区里没有叫 {name!r} 的流（flows/ 下有：{available}）；"
            f"库里有的先取过来：ai4sci flow take {name}")
    return path
