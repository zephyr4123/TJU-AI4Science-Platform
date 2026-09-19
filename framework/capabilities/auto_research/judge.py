"""一轮的裁决与结算：跑 harness 判这一轮算什么，然后让它落地。

拆成两半是这个模块的要点：`judge_run` 只产出结论（判决、commit、指标、墙钟），
`settle` 只负责把结论写进 git、账本、笔记与 checkpoint。前者能被单独喂输入考，
后者是唯一改磁盘状态的地方。

在 capabilities/auto_research/ 内部：它用 gate 比分数、用 failures 分类，被 loop 调用；
它不 import loop——in-flight 标记的读写留在 loop 那边，`settle` 只做到写完 checkpoint
为止，清标记由调用方紧接着做（顺序仍是账本 → 笔记 → checkpoint → 清标记）。
"""

from __future__ import annotations

import logging
import math
from pathlib import Path
from typing import Any

from backends import RunResult
from compute import Compute, Job
from framework.capabilities.auto_research import failures, gate
from framework.executor.session import executor_report
from framework.experiment import env, gitwork, layout, ledger, notebook
from framework.experiment.checkpoint import write_checkpoint
from framework.experiment.context import RunContext
from framework.experiment.pack import BUDGET_OVERRUN_RATIO
from framework.experiment.results import read_results

LOGGER = logging.getLogger("ai4sci.experiment")

LAUNCH_CMD = ["bash", "harness/launcher.sh"]
CODE_PREFIX = "code/"


def judge_run(
    ctx: RunContext, iter_n: int, result: RunResult, compute: Compute
) -> tuple[failures.Verdict | None, str, float | None, float]:
    """事后 diff → 提交 → 快照跑 harness → 分类。返回（判决, commit, 主指标, 墙钟）。

    harness 根本没跑起来的几条路径，墙钟一律填 NaN：那不是"跑了 0 秒"，是没量过（P-7）。
    """
    if result.timed_out or result.exit_code != 0:
        # 会话没走完就没有可采信的改动：半截的编辑一律丢弃，记一轮执行层失败（真跑第 10 轮
        # 被 kill -9 时这里曾把整个内环炸掉，现在是可记账的一轮）
        return (failures.executor_failed_verdict(result.exit_code, result.timed_out),
                ledger.MISSING, None, math.nan)
    outside = [p for p in result.changed_files if not p.startswith(CODE_PREFIX)]
    if outside:  # 第一道门是 CLI 权限，真正的门是这里（纲领 §5）
        return failures.readonly_verdict(outside), ledger.MISSING, None, math.nan
    if not result.changed_files:
        return failures.noop_verdict(), ledger.MISSING, None, math.nan

    commit = gitwork.commit_paths(ctx.work, ["code"], f"iter {iter_n}: 执行层改动")
    if commit is None:
        # 快照看得见改动、git 却提交不出东西：包自己的 .gitignore 把它们全挡住了。
        # 这不是执行层越界，但这一轮没有可留可回滚的东西，按"没改"处理并把原因告诉它。
        return failures.gitignored_verdict(), ledger.MISSING, None, math.nan

    run_n = layout.iter_run(ctx.run_dir, iter_n)
    before = failures.readonly_hashes(ctx.work)
    compute.put(ctx.work, run_n)
    # harness 只经 $AI4SCI_PYTHON 起解释器（任务跑在这次实验自己的 venv 里），预算与内部重复次数也由
    # 这里保证给出：launcher 不该再把它们写成常数
    job = compute.submit(run_n, LAUNCH_CMD,
                         {env.SEED_ENV: str(ctx.seed),
                          **env.harness_env(ctx.python, ctx.wall_clock_s, ctx.inner_k)},
                         timeout_s=ctx.wall_clock_s * BUDGET_OVERRUN_RATIO)
    # 句柄立刻落盘：submit 与 wait 之间被杀时，续跑靠它接回或收尸（A-5）
    (run_n / "job.json").write_text(job.to_json(), encoding="utf-8")
    status = compute.wait(job)
    compute.get(run_n, run_n)  # local 是 no-op；端口的调用点必须真实存在（P-8）

    metric, problems = read_results(run_n / "results.json", ctx.metric_name)
    verdict = failures.classify_run(
        tampered=failures.tampered(before, run_n), timed_out=status.timed_out,
        exit_code=status.exit_code, stderr_tail=failures.stderr_tail(Path(status.stderr_path)),
        results_problems=problems, metric=metric,
    )
    return verdict, commit, metric, status.elapsed_s


def settle(
    ctx: RunContext, state: dict[str, Any], iter_n: int, verdict: failures.Verdict | None,
    commit: str, metric: float | None, elapsed_s: float, result: RunResult,
) -> dict[str, Any]:
    """裁决落地：keep 让分支前进，其余一律留档 + 回到 best；记账、写 checkpoint。"""
    # parent 要在结算之前存下来：keep 会把 best_commit 推到本轮的 commit，
    # 那时再读就变成"自己是自己的 parent"，账本的 keep 链也就对不起账了（H2）。
    parent = state["best_commit"]
    if verdict is None:
        assert metric is not None, "没有判为失败就必须有指标"
        status, note = gate.compare(ctx, state["best_metric"], metric)
    else:
        status, note = verdict.status, verdict.note

    if status == "keep":
        state = {**state, "best_metric": metric, "best_iter": iter_n, "best_commit": commit}
    else:
        if commit != ledger.MISSING:
            # 被弃的 commit 先留档再销毁：账本每一行都要能在 git 里找到（P-3）
            gitwork.keep_attempt(ctx.work, iter_n, commit)
        gitwork.revert_to(ctx.work, state["best_commit"])

    append_row(ctx, parent, iter_n, commit=commit, metric=metric, elapsed_s=elapsed_s,
               status=status, note=note, cost_usd=result.cost_usd, executor_s=result.duration_s)
    # 笔记在账本之后、checkpoint 之前写：它是记忆不是账，丢一条不影响对账，
    # 但必须在下一轮开跑前落盘
    notebook.append(
        layout.notebook(ctx.run_dir), iter_n=iter_n, status=status,
        metric="-" if metric is None else f"{metric:.6g}", note=note,
        report=executor_report(result),
        diffstat=gitwork.diff_stat(ctx.work, parent, commit) if commit != ledger.MISSING else "",
    )
    state = {**state, "last_iter": iter_n}
    write_checkpoint(ctx.run_dir, state)
    LOGGER.info("iter=%d run_dir=%s status=%s metric=%s best=%s cost=%s", iter_n, ctx.run_dir,
                status, metric, state["best_metric"], result.cost_usd)
    return state


def append_row(
    ctx: RunContext, parent: str, iter_n: int, *, commit: str, metric: float | None,
    elapsed_s: float | None, status: str, note: str, cost_usd: float | None,
    executor_s: float | None,
) -> None:
    """账本一行。收尸那一轮（loop._reap_interrupted）走的也是这里，只有这一个写入点。"""
    ledger.append(ctx.ledger_path, ledger.LedgerRow(
        iter=iter_n, commit=commit, parent=parent, metric=metric,
        direction=ctx.direction, elapsed_s=elapsed_s, seed=ctx.seed, status=status,
        sigma=ctx.sigma, harness_sha=failures.harness_sha(ctx.work), note=note,
        cost_usd=cost_usd, executor_s=executor_s))


def read_job(ctx: RunContext, iter_n: int) -> Job | None:
    """读回第 N 轮落盘的 harness 句柄；没落盘就是还没 submit 出去（返回 None）。"""
    path = layout.iter_run(ctx.run_dir, iter_n) / "job.json"
    if not path.is_file():
        return None
    return Job.from_json(path.read_text(encoding="utf-8"))
