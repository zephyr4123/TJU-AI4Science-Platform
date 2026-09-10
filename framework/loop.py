"""实验内环：唯一有循环的地方（纲领 workflow.md §2）。

四个角色分开是这个模块的全部要点：执行层只改 `code/` 并交出 diff；runner（本模块）
拷快照、起独立进程跑 harness、比较、留或回滚、记账；git 当状态载体；账本活过 reset。
本模块零模型调用——`runner` 与 `compute` 都是注入进来的端口，换剧本后端就能全速跑测试。

分工：状态与建 run 在 `runstate.py`，六类失败与取证在 `failures.py`，对 work/ 的 git
操作在 `gitwork.py`，账本在 `ledger.py`，给执行层的提示在 `prompting.py`。
"""

from __future__ import annotations

import json
import math
import shutil
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from backends import Runner, RunResult
from compute import Compute, Job
from framework import failures, gitwork, ledger, notebook, packs, prompting
from framework.runstate import (
    LOGGER,
    RunContext,
    TaskInvalid,
    default_runs_root,
    executor_timeout_s,
    extend_run,
    load_context,
    new_run,
    read_checkpoint,
    write_checkpoint,
)

# 转出 runstate 的入口：协调层与 CLI 只认 framework.loop 这一个门面
__all__ = ["StopReason", "ResumeMismatch", "InflightPending", "TaskInvalid", "run_loop",
           "resume_loop", "new_run", "extend_run", "load_context", "read_checkpoint",
           "default_runs_root"]

UNRECOVERABLE_REPEATS = 3  # 同类失败连续这么多次判不可修复（纲领 §2）
LAUNCH_CMD = ["bash", "harness/launcher.sh"]
CODE_PREFIX = "code/"
INFLIGHT_NAME = "inflight.json"
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
    # 账本领先 checkpoint 一行是一个已知的崩溃窗口（_append_row 落盘之后、write_checkpoint
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
        # 账本里已经有这一轮：被杀发生在 _settle 的尾巴上，harness 早跑完了，不用收尸
        return _resettle(ctx, state, settled)
    if iter_n != state["last_iter"] + 1:
        raise ResumeMismatch(
            f"in-flight 标记的轮次 {iter_n} 与 checkpoint 对不上"
            f"（期望 {state['last_iter'] + 1}，账本最后一轮 {rows[-1].iter if rows else 0}）"
        )
    job_path = ctx.experiment / "runs" / f"run_{iter_n}" / "job.json"
    # 成本、执行层耗时、墙钟都可能压根没量过，未知一律 NaN，不写 0（P-7）
    elapsed = math.nan
    if job_path.is_file():
        job = Job.from_json(job_path.read_text(encoding="utf-8"))
        status = compute.wait(job, timeout_s=job.timeout_s)
        elapsed = status.elapsed_s
        LOGGER.info("resume_reap run_dir=%s iter=%d exit_code=%s", ctx.run_dir, iter_n,
                    status.exit_code)
    head = gitwork.head(ctx.work)
    commit = head if head != state["best_commit"] else ledger.MISSING
    if commit != ledger.MISSING:
        gitwork.keep_attempt(ctx.work, iter_n, head)
    gitwork.revert_to(ctx.work, state["best_commit"])
    _append_row(ctx, state["best_commit"], iter_n, commit=commit, metric=None, elapsed_s=elapsed,
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
    result = runner.run(
        prompt=_build_prompt(ctx, state, rows, iter_n), cwd=ctx.work,
        timeout_s=executor_timeout_s(), allowed_paths=[ctx.work / "code"],
    )
    _stash_executor_logs(ctx, iter_n)
    verdict, commit, metric, elapsed = _judge(ctx, iter_n, result, compute)
    return _settle(ctx, state, iter_n, verdict, commit, metric, elapsed, result)


def _stash_executor_logs(ctx: RunContext, iter_n: int) -> None:
    """把适配器写在 work/.ai4sci/ 下的事件流搬到 experiment/executor/iter-N/。

    为什么要搬：revert-to-best 用 git clean -x 连 ignored 文件一起清，取证日志留在 work/
    里会在下一轮开头被抹掉（真跑时就丢过一次）。日志是账本之外唯一能回答"执行层那一轮
    到底干了什么"的证据（P-3、P-9），必须和快照一样按轮留档。
    """
    src = ctx.work / ".ai4sci"
    if not src.is_dir():
        return
    dst = ctx.experiment / "executor" / f"iter-{iter_n}"
    dst.mkdir(parents=True, exist_ok=True)
    for path in sorted(src.iterdir()):
        shutil.move(str(path), str(dst / path.name))
    src.rmdir()


def _judge(
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
        # 快照看得见改动、git 却提交不出东西：任务包自己的 .gitignore 把它们全挡住了。
        # 这不是执行层越界，但这一轮没有可留可回滚的东西，按"没改"处理并把原因告诉它。
        return failures.gitignored_verdict(), ledger.MISSING, None, math.nan

    run_n = ctx.experiment / "runs" / f"run_{iter_n}"
    before = failures.readonly_hashes(ctx.work)
    compute.put(ctx.work, run_n)
    job = compute.submit(run_n, LAUNCH_CMD, {"AI4SCI_SEED": str(ctx.seed)},
                         timeout_s=ctx.wall_clock_s * packs.BUDGET_OVERRUN_RATIO)
    # 句柄立刻落盘：submit 与 wait 之间被杀时，续跑靠它接回或收尸（A-5）
    (run_n / "job.json").write_text(job.to_json(), encoding="utf-8")
    status = compute.wait(job)
    compute.get(run_n, run_n)  # local 是 no-op；端口的调用点必须真实存在（P-8）

    metric, problems = failures.read_results(run_n / "results.json", ctx.metric_name)
    verdict = failures.classify_run(
        tampered=failures.tampered(before, run_n), timed_out=status.timed_out,
        exit_code=status.exit_code, stderr_tail=failures.stderr_tail(Path(status.stderr_path)),
        results_problems=problems, metric=metric,
    )
    return verdict, commit, metric, status.elapsed_s


def _settle(
    ctx: RunContext, state: dict[str, Any], iter_n: int, verdict: failures.Verdict | None,
    commit: str, metric: float | None, elapsed_s: float, result: RunResult,
) -> dict[str, Any]:
    """裁决落地：keep 让分支前进，其余一律留档 + 回到 best；记账、写 checkpoint。"""
    # parent 要在结算之前存下来：keep 会把 best_commit 推到本轮的 commit，
    # 那时再读就变成"自己是自己的 parent"，账本的 keep 链也就对不起账了（H2）。
    parent = state["best_commit"]
    if verdict is None:
        assert metric is not None, "没有判为失败就必须有指标"
        status, note = _compare(ctx, state["best_metric"], metric)
    else:
        status, note = verdict.status, verdict.note

    if status == "keep":
        state = {**state, "best_metric": metric, "best_iter": iter_n, "best_commit": commit}
    else:
        if commit != ledger.MISSING:
            # 被弃的 commit 先留档再销毁：账本每一行都要能在 git 里找到（P-3）
            gitwork.keep_attempt(ctx.work, iter_n, commit)
        gitwork.revert_to(ctx.work, state["best_commit"])

    _append_row(ctx, parent, iter_n, commit=commit, metric=metric, elapsed_s=elapsed_s,
                status=status, note=note, cost_usd=result.cost_usd, executor_s=result.duration_s)
    # 笔记在账本之后、checkpoint 之前写：它是记忆不是账，丢一条不影响对账，
    # 但必须在下一轮开跑前落盘
    notebook.append(
        ctx.experiment / notebook.NOTEBOOK_NAME, iter_n=iter_n, status=status,
        metric="-" if metric is None else f"{metric:.6g}", note=note,
        report=_executor_report(result),
        diffstat=gitwork.diff_stat(ctx.work, parent, commit) if commit != ledger.MISSING else "",
    )
    state = {**state, "last_iter": iter_n}
    write_checkpoint(ctx.run_dir, state)
    _clear_inflight(ctx)
    LOGGER.info("iter=%d run_dir=%s status=%s metric=%s best=%s cost=%s", iter_n, ctx.run_dir,
                status, metric, state["best_metric"], result.cost_usd)
    return state


def _gate(ctx: RunContext) -> float:
    """统计门的高度：`max(accept_sigma×σ, min_delta)`。

    σ 会退化：run_0 的几次重复完全一致时 σ=0，`accept_sigma×σ` 也就是 0，那时任何
    一点点差值都算"改进"，统计门形同虚设。`budget.min_delta` 是这种情况下的兜底最小
    改进量，两者取大的那个——门只会被抬高，不会被放低（M4）。
    """
    return max(ctx.accept_sigma * ctx.sigma, ctx.min_delta)


def _compare(ctx: RunContext, best_metric: float, metric: float) -> tuple[str, str]:
    """统计门：差值超过门才算改进，门内一律判持平不留（纲领 §2）。"""
    if ctx.direction == "minimize":
        delta = best_metric - metric
    elif ctx.direction == "maximize":
        delta = metric - best_metric
    else:
        # load_context 已经断言过一次；这里不拿 else 当 maximize 兜底：方向写错时
        # 悄悄按反方向比，会把变差的改动当改进留下来（P-7）
        raise ValueError(f"未知的 direction {ctx.direction!r}，只认 minimize / maximize")
    gate = _gate(ctx)
    if delta > gate:
        return "keep", f"改进 delta={delta:.6g} > gate={gate:.6g}"
    if delta > 0:
        return "discard", f"within noise: delta={delta:.6g} <= gate={gate:.6g}"
    return "discard", f"变差或持平 delta={delta:.6g}"


def _append_row(
    ctx: RunContext, parent: str, iter_n: int, *, commit: str, metric: float | None,
    elapsed_s: float | None, status: str, note: str, cost_usd: float | None,
    executor_s: float | None,
) -> None:
    ledger.append(ctx.ledger_path, ledger.LedgerRow(
        iter=iter_n, commit=commit, parent=parent, metric=metric,
        direction=ctx.direction, elapsed_s=elapsed_s, seed=ctx.seed, status=status,
        sigma=ctx.sigma, harness_sha=failures.harness_sha(ctx.work), note=note,
        cost_usd=cost_usd, executor_s=executor_s))


# ── 停止条件：全部从账本与 checkpoint 现算，不另维护计数器（重启后结论一致）──
def _stop_reason(ctx: RunContext, state: dict[str, Any], limit: int) -> StopReason | None:
    rows = ledger.read(ctx.ledger_path)
    done, best = state["last_iter"], state["best_metric"]
    if done >= ctx.max_iterations:
        return StopReason("max_iterations", done, best)
    recent = rows[-UNRECOVERABLE_REPEATS:]
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
    (ctx.experiment / "stop.json").write_text(
        json.dumps(asdict(stop), ensure_ascii=False, indent=2), encoding="utf-8")
    write_checkpoint(ctx.run_dir, {**state, "stop_reason": stop.reason})
    LOGGER.info("stop run_dir=%s reason=%s iter=%d best=%s", ctx.run_dir, stop.reason,
                stop.iter, stop.best_metric)
    return stop


# ── 小工具 ──────────────────────────────────────────────────────────────
def _build_prompt(
    ctx: RunContext, state: dict[str, Any], rows: list[ledger.LedgerRow], iter_n: int
) -> str:
    hint = failures.HINTS.get(rows[-1].status, "") if rows else ""
    return prompting.build_prompt({
        "iter": iter_n, "question": ctx.question, "metric_name": ctx.metric_name,
        "direction": ctx.direction, "direction_zh": prompting.DIRECTION_ZH[ctx.direction],
        "best_metric": f"{state['best_metric']:.6g}", "best_iter": state["best_iter"],
        "gate": f"{_gate(ctx):.6g}", "accept_sigma": f"{ctx.accept_sigma:g}",
        "sigma": f"{ctx.sigma:.6g}", "wall_clock_s": f"{ctx.wall_clock_s:g}",
        "ledger_tail": prompting.summarize_ledger(rows),
        "last_round": prompting.last_round_note(rows, hint),
        "notebook": notebook.read(ctx.experiment / notebook.NOTEBOOK_NAME),
    }, ctx.domain_extra)


def _executor_report(result: RunResult) -> str:
    """执行层这一轮的自述 = stream-json 最终 result 事件的文本；没有就空串，不编。"""
    final = next((e for e in reversed(result.events) if e.get("type") == "result"), None)
    text = (final or {}).get("result")
    return text.strip() if isinstance(text, str) else ""


def _cancel_inflight_job(ctx: RunContext, compute: Compute) -> None:
    """把本轮已经 submit 出去的 harness 杀掉；还没 submit 就没有句柄，什么都不用做。"""
    inflight = _read_inflight(ctx)
    if inflight is None:
        return
    job_path = ctx.experiment / "runs" / f"run_{int(inflight['iter'])}" / "job.json"
    if not job_path.is_file():
        return
    job = Job.from_json(job_path.read_text(encoding="utf-8"))
    LOGGER.info("cancel_inflight run_dir=%s iter=%s pgid=%d", ctx.run_dir, inflight["iter"],
                job.pgid)
    compute.cancel(job)


def _write_inflight(ctx: RunContext, iter_n: int) -> None:
    (ctx.experiment / INFLIGHT_NAME).write_text(
        json.dumps({"iter": iter_n, "started_at": time.time()}), encoding="utf-8")


def _read_inflight(ctx: RunContext) -> dict[str, Any] | None:
    path = ctx.experiment / INFLIGHT_NAME
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else None


def _clear_inflight(ctx: RunContext) -> None:
    (ctx.experiment / INFLIGHT_NAME).unlink(missing_ok=True)
