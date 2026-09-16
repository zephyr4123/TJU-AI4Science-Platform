"""实验内环的主循环：唯一有循环的地方（纲领 workflow.md §2）。

四个角色分开是这个能力的全部要点：执行层只改 `code/` 并交出 diff；runner（本能力）
拷快照、起独立进程跑 harness、比较、留或回滚、记账；git 当状态载体；账本活过 reset。
零模型调用——`runner` 与 `compute` 都是注入进来的端口，换剧本后端就能全速跑测试。

本模块只剩"一轮怎么走、什么时候停"，以及被杀在半路时怎么对账收尸：
跑 harness 与结算在 `judge.py`，统计门在 `gate.py`，失败分类与取证在 `failures.py`，
组 prompt 与起会话在 `framework/executor/`，磁盘状态在 `framework/run/`。
能力之间互不 import（`capabilities/__init__.py`）。
"""

from __future__ import annotations

import json
import logging
import math
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from backends import Runner
from compute import Compute
from framework.capabilities.experiment import failures, gate
from framework.capabilities.experiment.judge import append_row, judge_run, read_job, settle
from framework.executor import prompting, session
from framework.memory import ledger, notebook
from framework.run import gitwork, layout
from framework.run.checkpoint import read_checkpoint, write_checkpoint
from framework.run.context import RunContext, load_context

LOGGER = logging.getLogger("ai4sci.experiment")

UNRECOVERABLE_REPEATS = 3  # 同类失败连续这么多次判不可修复（纲领 §2）
# 给执行层的提示模板：它是这个能力的资产，跟能力一起走（executor 只负责组装）
PROMPT_TEMPLATE = Path(__file__).resolve().parent / "prompt.md"
# 本次 `--max-iters` 的配额用完。它不是这个 run 的结局，所以不写 stop.json，
# 也不往 checkpoint 里落 stop_reason——下一次 `loop run` 还接着跑。
BATCH_EXHAUSTED = "batch_exhausted"


class ResumeMismatch(RuntimeError):
    """checkpoint、账本、git 三方对不上。续跑绝不猜，直接停（P-7）。"""


class InflightPending(RuntimeError):
    """run 里还留着没走完的一轮。收尸是 `resume` 的活，`run` 不许从中间接着跑（P-7）。"""


@dataclass
class StopReason:
    reason: str
    iter: int
    best_metric: float | None


# ── 主循环 ──────────────────────────────────────────────────────────────
def run_loop(
    run_dir: Path, runner: Runner, compute: Compute, max_iters: int | None = None
) -> StopReason:
    """跑到停止条件为止；返回停止原因。

    `max_iters` 是**本次增量**而不是这个 run 的总额：上限取
    `min(manifest.max_iterations, 已跑轮数 + max_iters)`。只有 manifest 触顶（以及
    不可修复 / patience / 成本这些真正的终局）才写 `experiment/stop.json` 与
    `checkpoint.stop_reason`；本次配额用完只返回 `batch_exhausted`，什么都不写——
    小批量地跑不该把 run 锁死，要不要继续是协调层的决定（P-10）。
    """
    run_dir = Path(run_dir).resolve()
    ctx = load_context(run_dir)
    state = read_checkpoint(run_dir)
    inflight = _read_inflight(ctx)
    if inflight is not None:
        # 有 in-flight 标记就说明上一次被杀在半路：直接往下跑会把那一轮的账漏掉（P-7）
        raise InflightPending(
            f"第 {inflight['iter']} 轮没走完，请跑 ai4sci loop resume {state['run_id']}"
        )
    if state.get("stop_reason"):
        # 已经停过的 run 不自己续命：要不要继续是协调层的决定（P-10）
        return StopReason(state["stop_reason"], state["last_iter"], state["best_metric"])
    limit = (ctx.max_iterations if max_iters is None
             else min(ctx.max_iterations, state["last_iter"] + max_iters))
    while True:
        stop = _stop_reason(ctx, state, limit)
        if stop is not None:
            if stop.reason == BATCH_EXHAUSTED:
                LOGGER.info("batch_exhausted run_dir=%s iter=%d limit=%d", ctx.run_dir,
                            stop.iter, limit)
                return stop
            return _finish(ctx, state, stop)
        try:
            state = _run_iteration(ctx, state, state["last_iter"] + 1, runner, compute)
        except KeyboardInterrupt:
            # 异常原样往上抛（不吞异常）；但在飞的 harness 是本进程 submit 出去的，
            # 不先杀就会留一组进程在后台继续烧算力，续跑时还得跟它抢同一个快照目录。
            _cancel_inflight_job(ctx, compute)
            raise


def resume_loop(
    run_dir: Path, runner: Runner, compute: Compute, max_iters: int | None = None
) -> StopReason:
    """三方对账 → 给 in-flight 的那一轮收尸 → 接着跑。对不上就抛，绝不猜（P-7）。"""
    run_dir = Path(run_dir).resolve()
    ctx = load_context(run_dir)
    state = read_checkpoint(run_dir)
    rows = ledger.read(ctx.ledger_path)
    inflight = _read_inflight(ctx)

    last_row_iter = rows[-1].iter if rows else 0
    ahead = last_row_iter - state["last_iter"]
    # 账本领先 checkpoint 一行是一个已知的崩溃窗口（append_row 落盘之后、write_checkpoint
    # 之前被杀）：认它，但要求那一轮的 in-flight 标记还在。别的对不上一律停。
    known_window = (ahead == 1 and inflight is not None
                    and int(inflight["iter"]) == last_row_iter)
    if ahead != 0 and not known_window:
        raise ResumeMismatch(
            f"账本最后一轮 {last_row_iter} 与 checkpoint.last_iter {state['last_iter']} 对不上"
            f"（期望相等；或账本领先一行且有第 {last_row_iter} 轮的 in-flight 标记）"
        )
    best = state["best_commit"]
    if gitwork.rev_parse(ctx.work, best) is None:
        raise ResumeMismatch(f"checkpoint 的 best_commit {best} 在 git 里找不到")
    if not gitwork.is_ancestor(ctx.work, best):
        raise ResumeMismatch(f"best_commit {best} 不在当前分支上")
    head = gitwork.head(ctx.work)
    # HEAD 领先 best 只有一种正当解释：那一轮提交完就被杀了，标记还在。没标记就是对不上。
    if head != best and inflight is None:
        raise ResumeMismatch(f"HEAD {head} 不是 best_commit {best}，又没有 in-flight 标记")

    if inflight is not None:
        state = _reap_interrupted(ctx, state, inflight, compute)
    return run_loop(run_dir, runner, compute, max_iters)


def _reap_interrupted(
    ctx: RunContext, state: dict[str, Any], inflight: dict[str, Any], compute: Compute
) -> dict[str, Any]:
    """被杀在半路的那一轮：先看它是不是其实已经结算过，再决定收尸还是补 checkpoint。"""
    iter_n = int(inflight["iter"])
    rows = ledger.read(ctx.ledger_path)
    settled = rows[-1] if rows and rows[-1].iter == iter_n else None
    if settled is not None:
        # 账本里已经有这一轮：被杀发生在 settle 的尾巴上，harness 早跑完了，不用收尸
        return _resettle(ctx, state, settled)
    if iter_n != state["last_iter"] + 1:
        raise ResumeMismatch(
            f"in-flight 标记的轮次 {iter_n} 与 checkpoint 对不上"
            f"（期望 {state['last_iter'] + 1}，账本最后一轮 {rows[-1].iter if rows else 0}）"
        )
    job = read_job(ctx, iter_n)
    # 成本、执行层耗时、墙钟都可能压根没量过，未知一律 NaN，不写 0（P-7）
    elapsed = math.nan
    if job is not None:
        status = compute.wait(job, timeout_s=job.timeout_s)
        elapsed = status.elapsed_s
        LOGGER.info("resume_reap run_dir=%s iter=%d exit_code=%s", ctx.run_dir, iter_n,
                    status.exit_code)
    head = gitwork.head(ctx.work)
    commit = head if head != state["best_commit"] else ledger.MISSING
    if commit != ledger.MISSING:
        gitwork.keep_attempt(ctx.work, iter_n, head)
    gitwork.revert_to(ctx.work, state["best_commit"])
    append_row(ctx, state["best_commit"], iter_n, commit=commit, metric=None, elapsed_s=elapsed,
               status="interrupted", note="被中断，已回到 best", cost_usd=math.nan,
               executor_s=math.nan)
    state = {**state, "last_iter": iter_n}
    write_checkpoint(ctx.run_dir, state)
    _clear_inflight(ctx)
    return state


def _resettle(
    ctx: RunContext, state: dict[str, Any], row: ledger.LedgerRow
) -> dict[str, Any]:
    """账本里已经有 in-flight 那一轮时的两个崩溃窗口，以账本为准把 checkpoint 补齐。"""
    if row.iter == state["last_iter"]:
        # 窗口一：结算全做完了，只剩 inflight.json 没删就被杀。清掉标记接着跑。
        LOGGER.info("resume_stale_marker run_dir=%s iter=%d", ctx.run_dir, row.iter)
        _clear_inflight(ctx)
        return state
    # 窗口二：账本领先 checkpoint 一行（append_row 之后、write_checkpoint 之前被杀）
    head = gitwork.head(ctx.work)
    if row.status == "keep":
        if head != row.commit:
            raise ResumeMismatch(
                f"账本第 {row.iter} 行是 keep，期望 HEAD 是它的 commit {row.commit}，实际 {head}"
            )
        state = {**state, "best_metric": row.metric, "best_iter": row.iter,
                 "best_commit": row.commit}
    elif head != state["best_commit"]:
        raise ResumeMismatch(
            f"账本第 {row.iter} 行是 {row.status}，期望已回到 best {state['best_commit']}，"
            f"实际 HEAD 是 {head}"
        )
    LOGGER.info("resume_ledger_ahead run_dir=%s iter=%d status=%s", ctx.run_dir, row.iter,
                row.status)
    state = {**state, "last_iter": row.iter}
    write_checkpoint(ctx.run_dir, state)
    _clear_inflight(ctx)
    return state


# ── 一轮 ────────────────────────────────────────────────────────────────
def _run_iteration(
    ctx: RunContext, state: dict[str, Any], iter_n: int, runner: Runner, compute: Compute
) -> dict[str, Any]:
    best_commit = state["best_commit"]
    if not gitwork.is_clean(ctx.work) or gitwork.head(ctx.work) != best_commit:
        # revert-to-best：下一轮的起点永远是分支 tip，不是上一轮的失败候选
        LOGGER.info("revert_to_best run_dir=%s iter=%d best=%s", ctx.run_dir, iter_n,
                    best_commit[:12])
        gitwork.revert_to(ctx.work, best_commit)
    # 标记先立后跑：不管被杀在执行层、submit 还是 wait，续跑都知道"第 N 轮没走完"（A-5）
    _write_inflight(ctx, iter_n)

    rows = ledger.read(ctx.ledger_path)
    result = session.run_executor(
        ctx, runner, iter_n, PROMPT_TEMPLATE, _prompt_values(ctx, state, rows, iter_n)
    )
    verdict, commit, metric, elapsed = judge_run(ctx, iter_n, result, compute)
    state = settle(ctx, state, iter_n, verdict, commit, metric, elapsed, result)
    # 清标记是这一轮的最后一步：settle 写完 checkpoint 才算走完，早清一步就等于
    # 在还没落盘时告诉续跑"这轮没事"（顺序：账本 → 笔记 → checkpoint → 清标记）
    _clear_inflight(ctx)
    return state


# ── 停止条件：全部从账本与 checkpoint 现算，不另维护计数器（重启后结论一致）──
def _stop_reason(ctx: RunContext, state: dict[str, Any], limit: int) -> StopReason | None:
    rows = ledger.read(ctx.ledger_path)
    done, best = state["last_iter"], state["best_metric"]
    if done >= ctx.max_iterations:
        return StopReason("max_iterations", done, best)
    # 续命过的 run 只数续命之后的轮次：之前的失败协调层已经看过并决定继续（lifecycle.extend_run）
    since = state.get("resumed_after_iter", 0)
    recent = [r for r in rows if r.iter > since][-UNRECOVERABLE_REPEATS:]
    fails = [r.status for r in recent if r.status in failures.FAILURE_STATUSES]
    if len(fails) == UNRECOVERABLE_REPEATS and len(set(fails)) == 1:
        return StopReason(f"unrecoverable:{fails[0]}", done, best)
    stale = 0
    for row in reversed(rows):  # 连续多少轮没让 best 前进
        if row.status == "keep":
            break
        stale += 1
    if stale >= ctx.patience:
        return StopReason("patience", done, best)
    if ctx.max_cost_usd is not None and ledger.total_cost(ctx.ledger_path) >= ctx.max_cost_usd:
        return StopReason("max_cost_usd", done, best)
    # 放在最后：真正的终局（不可修复 / patience / 成本）该被记进 stop.json，
    # 本次配额用完只是这一批跑完了，不是这个 run 的结论
    if done >= limit:
        return StopReason(BATCH_EXHAUSTED, done, best)
    return None


def _finish(ctx: RunContext, state: dict[str, Any], stop: StopReason) -> StopReason:
    layout.stop(ctx.run_dir).write_text(
        json.dumps(asdict(stop), ensure_ascii=False, indent=2), encoding="utf-8")
    write_checkpoint(ctx.run_dir, {**state, "stop_reason": stop.reason})
    LOGGER.info("stop run_dir=%s reason=%s iter=%d best=%s", ctx.run_dir, stop.reason,
                stop.iter, stop.best_metric)
    return stop


# ── 小工具 ──────────────────────────────────────────────────────────────
def _prompt_values(
    ctx: RunContext, state: dict[str, Any], rows: list[ledger.LedgerRow], iter_n: int
) -> dict[str, object]:
    """填给 prompt.md 的占位符；模板缺一个就抛，不会静默留下 `$xxx`。"""
    hint = failures.HINTS.get(rows[-1].status, "") if rows else ""
    return {
        "iter": iter_n, "question": ctx.question, "metric_name": ctx.metric_name,
        "direction": ctx.direction, "direction_zh": prompting.DIRECTION_ZH[ctx.direction],
        "best_metric": f"{state['best_metric']:.6g}", "best_iter": state["best_iter"],
        "gate": f"{gate.gate(ctx):.6g}", "accept_sigma": f"{ctx.accept_sigma:g}",
        "sigma": f"{ctx.sigma:.6g}", "wall_clock_s": f"{ctx.wall_clock_s:g}",
        "ledger_tail": prompting.summarize_ledger(rows),
        "last_round": prompting.last_round_note(rows, hint),
        "notebook": notebook.read(layout.notebook(ctx.run_dir)),
    }


def _cancel_inflight_job(ctx: RunContext, compute: Compute) -> None:
    """把本轮已经 submit 出去的 harness 杀掉；还没 submit 就没有句柄，什么都不用做。"""
    inflight = _read_inflight(ctx)
    if inflight is None:
        return
    job = read_job(ctx, int(inflight["iter"]))
    if job is None:
        return
    LOGGER.info("cancel_inflight run_dir=%s iter=%s pgid=%d", ctx.run_dir, inflight["iter"],
                job.pgid)
    compute.cancel(job)


def _write_inflight(ctx: RunContext, iter_n: int) -> None:
    layout.inflight(ctx.run_dir).write_text(
        json.dumps({"iter": iter_n, "started_at": time.time()}), encoding="utf-8")


def _read_inflight(ctx: RunContext) -> dict[str, Any] | None:
    path = layout.inflight(ctx.run_dir)
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else None


def _clear_inflight(ctx: RunContext) -> None:
    layout.inflight(ctx.run_dir).unlink(missing_ok=True)
