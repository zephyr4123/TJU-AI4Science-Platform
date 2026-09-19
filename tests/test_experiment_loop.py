"""实验内环的验收测试（A-4 到 A-9）。

全部用 tmp_path 造的夹具设计产出与剧本执行层，删掉仓里的 workspaces/ 与 domains/ 照过（P-5）。
剧本覆盖九种执行层行为：真改进、假改进、改坏、假成功、动 harness、崩溃、超时、
缺依赖、什么都不改——内环是确定性代码，它的正确性不该由模型的发挥来证明。

夹具 harness 用的就是 `packs_factory.LAUNCHER_SH`（`set -euo pipefail`），与真任务同款：
launcher 一严格，"假成功"和"跑崩了"在退出码上就长得一模一样，两者的分界只能靠 stderr
里有没有 traceback——这正是 failures.classify_run 要守住的边界，测试不该用一个宽松的
launcher 把它绕开。
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import pytest
import yaml

from compute import Job
from compute._procs import group_alive
from compute.local import LocalCompute
from framework.capabilities.auto_research import (
    InflightPending,
    ResumeMismatch,
    StopReason,
    gate,
    resume_loop,
    run_loop,
)
from framework.capabilities.auto_research.open import (
    PackInvalid,
    extend_experiment,
    open_experiment,
)
from framework.experiment import gitwork, ledger
from framework.experiment.checkpoint import read_checkpoint, write_checkpoint
from framework.experiment.context import load_context
from framework.workspace import outputs
from tests.fixtures import packs_factory as pf
from tests.fixtures.scripted_backend import ScriptedRunner, ScriptExhausted, write_train

FAKE_SUCCESS = {"code/train.py": 'print("val_mse 0.0001")\n'}
# 崩溃用例要真的打出 traceback：语法错误在编译期就被拒，解释器只打 SyntaxError 不打
# traceback 头，那是"没有产物"那一类，不是崩溃（见 failures.py 的边界说明）。
CRASH_TRAIN = {"code/train.py": 'raise ValueError("训练崩了")\n'}
MISSING_DEP = {"code/train.py": "import ai4sci_definitely_not_installed\n"}
INFINITE_LOOP = {"code/train.py": "while True:\n    pass\n"}
SLEEPY_TRAIN = {"code/train.py": "import time\n\ntime.sleep(60)\n"}
NAN_TRAIN = {"code/train.py": (
    "import json\n"
    "from pathlib import Path\n"
    "TASK_DIR = Path(__file__).resolve().parent.parent\n"
    "(TASK_DIR / 'predictions.json').write_text(json.dumps({'y_pred': [float('nan')]}))\n"
)}
IGNORED_BLOB = {"code/blob.bin": "01020304\n"}
NOOP: dict[str, str] = {}

# maximize 夹具的 harness：同一次评测再给一个"越大越好"的 score = 1 - mse。
SCORE_EVALUATE_PY = '''"""夹具 harness（maximize 版）：主指标是越大越好的 score。"""
import json
import sys
from pathlib import Path

TASK_DIR = Path(__file__).resolve().parent.parent
preds = TASK_DIR / "predictions.json"
if not preds.is_file():
    print("evaluate: 文件缺失：predictions.json", file=sys.stderr)
    raise SystemExit(2)
values = json.loads(preds.read_text(encoding="utf-8"))["y_pred"]
mse = sum(v * v for v in values) / len(values)
(TASK_DIR / "results.json").write_text(
    json.dumps({"metrics": {"val_mse": mse, "score": 1 - mse}, "elapsed_s": 0.1,
                "seed": 42, "status": "ok"}),
    encoding="utf-8",
)
print(f"val_mse={mse} score={1 - mse}")
'''

SEEDS = (42, 43, 44)
VALUES = (0.030, 0.025, 0.020)  # σ=0.005，统计门 2σ=0.01


def tamper_harness(cwd: Path) -> None:
    """动 harness：只读区被改，这一轮必须判 readonly_violated 并回滚。"""
    path = cwd / "harness" / "evaluate.py"
    path.write_text(path.read_text(encoding="utf-8") + "\n# 偷偷加一行\n", encoding="utf-8")


def train_for_mse(target: float) -> dict[str, str]:
    """让 harness 正好算出 target：单元素预测时 mse = v²。"""
    return write_train([math.sqrt(target)])


def loop_budget(**budget: object) -> dict[str, object]:
    return {"wall_clock_s": 2.0, "max_iterations": 30, "repeat_k": 3,
            "accept_sigma": 2.0, "patience": 99, **budget}


def make_loop_pack(tmp_path: Path, **budget: object) -> pf.Pack:
    """基线 0.030、σ=0.005、统计门 2σ=0.01 的夹具包（minimize）。"""
    scoring = pf.default_scoring()
    scoring["budget"] = loop_budget(**budget)
    return pf.make_pack(tmp_path, scoring=scoring, seeds=SEEDS, values=VALUES, elapsed_s=1.0)


def make_maximize_pack(tmp_path: Path, **budget: object) -> pf.Pack:
    """同一套数，主指标换成越大越好的 score = 1 - mse：基线 0.970，σ 与门不变。"""
    scoring = pf.default_scoring()
    scoring["metrics"] = [{"name": "val_mse", "direction": "minimize"},
                          {"name": "score", "direction": "maximize", "primary": True}]
    scoring["budget"] = loop_budget(**budget)
    pack = pf.make_pack(tmp_path, scoring=scoring, seeds=SEEDS, values=VALUES, elapsed_s=1.0)
    (pack.pack / "harness" / "evaluate.py").write_text(SCORE_EVALUATE_PY, encoding="utf-8")
    pf.refresh_sums(pack.pack)
    _write_score_baseline(pack.pack)
    return pack


def _write_score_baseline(pack_dir: Path) -> None:
    """baseline 里两个指标都要有，σ 也要两条——不然 validate_pack 直接把包判死。"""
    run0 = pack_dir / "baseline"

    def doc(value: float, seed: int) -> dict[str, object]:
        return {"metrics": {"val_mse": value, "score": 1 - value}, "elapsed_s": 1.0,
                "seed": seed, "status": "ok"}

    (run0 / "results.json").write_text(json.dumps(doc(VALUES[0], SEEDS[0])), encoding="utf-8")
    for seed, value in zip(SEEDS, VALUES, strict=True):
        (run0 / "repeats" / f"results-{seed}.json").write_text(
            json.dumps(doc(value, seed)), encoding="utf-8")
    mean = sum(VALUES) / len(VALUES)
    sigma = (sum((v - mean) ** 2 for v in VALUES) / (len(VALUES) - 1)) ** 0.5
    (run0 / "sigma.json").write_text(json.dumps({
        "val_mse": {"sigma": sigma, "seeds": list(SEEDS), "values": list(VALUES)},
        "score": {"sigma": sigma, "seeds": list(SEEDS), "values": [1 - v for v in VALUES]},
    }), encoding="utf-8")


def open_run(pack: pf.Pack) -> Path:
    """在工作区里开一次实验产出（experiment/<n>/）并照设计那包铺好。"""
    run_dir, meta = outputs.open_output(
        pack.workspace, "experiment", title="auto-research", by="auto-research",
        inputs=[pack.output_id], params={}, flow=None, step=None, requirement=1, chat_id=None)
    open_experiment(run_dir, pack.pack, pack.workspace.requirement, output_id=meta.id,
                    domains_root=pack.domains_root)
    return run_dir


def start_run(tmp_path: Path, **budget: object) -> tuple[Path, pf.Pack]:
    pack = make_loop_pack(tmp_path, **budget)
    return open_run(pack), pack


def rows_of(run_dir: Path) -> list[ledger.LedgerRow]:
    return ledger.read(run_dir / "ledger.tsv")


def inflight_path(run_dir: Path) -> Path:
    return run_dir / "inflight.json"


def mark_inflight(run_dir: Path, iter_n: int) -> None:
    inflight_path(run_dir).write_text(
        json.dumps({"iter": iter_n, "started_at": 0.0}), encoding="utf-8")


FULL_SCRIPT = [
    train_for_mse(0.018),   # 1 真改进：delta 0.012 > 门 0.01 → keep
    train_for_mse(0.0175),  # 2 假改进：delta 0.0005 在 σ 内 → discard
    train_for_mse(0.5),     # 3 改坏
    FAKE_SUCCESS,           # 4 只 print 不写产物 → no_results
    train_for_mse(0.006),   # 5 又一次真改进 → keep
    NOOP,                   # 6 什么都不改
    CRASH_TRAIN,            # 7 崩溃
    MISSING_DEP,            # 8 缺依赖
    INFINITE_LOOP,          # 9 超时
    tamper_harness,         # 10 动 harness
    NAN_TRAIN,              # 11 指标 NaN
    train_for_mse(0.0055),  # 12 假改进
    train_for_mse(0.004),   # 13 假改进
    NOOP,                   # 14
    CRASH_TRAIN,            # 15
    train_for_mse(0.9),     # 16 改坏
    MISSING_DEP,            # 17
    NAN_TRAIN,              # 18
    FAKE_SUCCESS,           # 19
    train_for_mse(0.003),   # 20
    tamper_harness,         # 21
    train_for_mse(0.002),   # 22
]


@pytest.fixture(scope="module")
def full_run(tmp_path_factory) -> tuple[Path, list[ledger.LedgerRow], StopReason]:
    """跑满 22 轮的那一次，A-4 / A-8 / A-9 与六类失败的用例共用（跑一次要十几秒）。"""
    tmp_path = tmp_path_factory.mktemp("full")
    run_dir, _ = start_run(tmp_path, max_iterations=22)
    runner = ScriptedRunner(list(FULL_SCRIPT))
    stop = run_loop(run_dir, runner, LocalCompute(), max_iters=22)
    return run_dir, rows_of(run_dir), stop


# ── A-4：账本 × git 对账 ────────────────────────────────────────────────
def test_a4_ledger_reconciles_with_git(full_run):
    run_dir, rows, stop = full_run
    work = run_dir / "work"
    assert len(rows) == 22 and stop.reason == "max_iterations"
    assert ledger.reconcile(run_dir / "ledger.tsv", work) == []
    attempts = set(gitwork.attempt_refs(work).values())
    for row in rows:
        if row.commit == ledger.MISSING:
            continue
        sha = gitwork.rev_parse(work, row.commit)
        assert sha is not None, f"iter {row.iter} 的 commit 在 git 里找不到"
        if row.status == "keep":
            assert gitwork.is_ancestor(work, sha), f"keep 行 {row.iter} 不在分支上"
        else:
            assert sha in attempts, f"被弃的 {row.status} 行 {row.iter} 没进 refs/attempts/"


def test_a4_keep_rows_chain_by_parent(full_run):
    """keep 行首尾相接：第一条的 parent 是基线，之后每条的 parent 是上一条 keep 的 commit。"""
    run_dir, rows, _ = full_run
    expected = gitwork.root_commit(run_dir / "work")
    keeps = [r for r in rows if r.status == "keep"]
    assert len(keeps) >= 2, "剧本里至少有两次真改进"
    for row in keeps:
        assert row.parent == expected, f"iter {row.iter} 的 parent 断链了"
        expected = row.commit


def test_a4_six_failure_classes_each_appear(full_run):
    _, rows, _ = full_run
    seen = {row.status for row in rows}
    assert {"readonly_violated", "timeout", "missing_dependency", "crash", "no_results",
            "nan_metric"} <= seen
    assert {"keep", "discard", "noop"} <= seen


def test_a4_head_is_best_and_checkpoint_agrees(full_run):
    run_dir, rows, _ = full_run
    state = read_checkpoint(run_dir)
    assert gitwork.head(run_dir / "work") == state["best_commit"]
    keeps = [r for r in rows if r.status == "keep"]
    assert state["best_metric"] == pytest.approx(keeps[-1].metric)
    assert state["best_iter"] == keeps[-1].iter


# ── A-8：统计门 ─────────────────────────────────────────────────────────
def test_a8_keep_rows_beat_the_gate_and_noise_is_discarded(full_run):
    _, rows, _ = full_run
    gate = 2.0 * 0.005
    best = 0.030  # 基线
    noisy = 0
    for row in rows:
        if row.metric is None:
            continue
        delta = best - row.metric  # minimize
        if row.status == "keep":
            assert delta > gate, f"iter {row.iter} 被 keep 但 delta={delta} 没过门 {gate}"
            best = row.metric
        elif 0 < delta <= gate:
            assert "within noise" in row.note, f"iter {row.iter} 的 note 没说清是噪声内"
            noisy += 1
    assert noisy >= 3, "剧本里的假改进没被判成噪声"


@pytest.mark.parametrize("direction", ["minimize", "maximize"])
def test_a8_gate_holds_in_both_directions(tmp_path, direction):
    """同一批预测，两个方向要得出同一串裁决：过门 keep、门内 discard、变差 discard。"""
    pack = (make_loop_pack(tmp_path) if direction == "minimize"
            else make_maximize_pack(tmp_path))
    run_dir = open_run(pack)
    script = [train_for_mse(0.018), train_for_mse(0.0175), train_for_mse(0.5)]
    run_loop(run_dir, ScriptedRunner(script), LocalCompute(), max_iters=3)
    rows = rows_of(run_dir)
    assert [r.status for r in rows] == ["keep", "discard", "discard"]
    assert {r.direction for r in rows} == {direction}
    assert "within noise" in rows[1].note
    assert "变差" in rows[2].note
    best = read_checkpoint(run_dir)["best_metric"]
    assert best == pytest.approx(0.018 if direction == "minimize" else 1 - 0.018)


# ── A-9：预算 ───────────────────────────────────────────────────────────
def test_a9_elapsed_matches_budget_or_is_a_timeout(full_run):
    _, rows, _ = full_run
    budget = 2.0
    timeouts = [r for r in rows if r.status == "timeout"]
    assert timeouts, "剧本里的死循环没被判超时"
    for row in timeouts:
        assert row.elapsed_s >= budget, f"超时行的 elapsed_s {row.elapsed_s} 还没到预算"
    for row in rows:
        if row.status in ("keep", "discard"):
            assert 0 < row.elapsed_s <= budget * 1.5, f"iter {row.iter} 的耗时越界"


def test_rows_without_a_harness_run_have_unknown_elapsed(full_run):
    """noop 与 readonly_violated 这几行 harness 压根没跑：耗时是未知（NaN），不是 0。"""
    _, rows, _ = full_run
    idle = [r for r in rows if r.status in ("noop", "readonly_violated")]
    assert idle, "剧本里有 noop 与动 harness 的轮次"
    for row in idle:
        assert row.elapsed_s is not None and math.isnan(row.elapsed_s), f"iter {row.iter}"


def test_ledger_row_columns_carry_cost_and_sigma(full_run):
    _, rows, _ = full_run
    for row in rows:
        assert row.direction == "minimize"
        assert row.seed == 42
        assert row.sigma == pytest.approx(0.005)
        assert row.harness_sha != ledger.MISSING
        assert row.cost_usd == pytest.approx(0.01)
        assert row.executor_s == pytest.approx(0.5)


# ── A-5：中途被杀后续跑 ─────────────────────────────────────────────────
def test_a5_resume_after_kill_records_interrupted_and_continues(tmp_path):
    run_dir, _ = start_run(tmp_path)
    script = [train_for_mse(0.018), train_for_mse(0.5), NOOP, CRASH_TRAIN, NOOP,
              train_for_mse(0.6), NOOP, CRASH_TRAIN, NOOP, train_for_mse(0.7),
              train_for_mse(0.8), NOOP]
    killed = ScriptedRunner(list(script), raise_at=10)
    with pytest.raises(KeyboardInterrupt):  # 异常原样冒出来，不许被吞
        run_loop(run_dir, killed, LocalCompute(), max_iters=12)

    state = read_checkpoint(run_dir)
    assert state["last_iter"] == 9
    best_before = state["best_metric"]
    assert inflight_path(run_dir).is_file()

    resumed = ScriptedRunner(script[9:])
    stop = resume_loop(run_dir, resumed, LocalCompute(), max_iters=2)
    rows = rows_of(run_dir)
    by_iter = {row.iter: row for row in rows}
    assert by_iter[10].status == "interrupted"
    assert by_iter[11].iter == 11 and by_iter[11].status != "interrupted"
    assert [r.iter for r in rows] == list(range(1, 13))
    assert read_checkpoint(run_dir)["best_metric"] == best_before
    assert stop.reason == "batch_exhausted"
    assert not inflight_path(run_dir).exists()
    assert ledger.reconcile(run_dir / "ledger.tsv", run_dir / "work") == []


def test_a5_resume_reaps_an_in_flight_job(tmp_path):
    """submit 之后被杀：job.json 还在，续跑要先给它收尸再记 interrupted。"""
    run_dir, _ = start_run(tmp_path)
    compute = LocalCompute()
    run_1 = run_dir / "iters" / "iter_1"
    run_1.mkdir(parents=True)
    job = compute.submit(run_1, ["python3", "-c", "pass"], {}, timeout_s=10)
    (run_1 / "job.json").write_text(job.to_json(), encoding="utf-8")
    (run_dir / "inflight.json").write_text(
        json.dumps({"iter": 1, "started_at": job.started_at}), encoding="utf-8")

    stop = resume_loop(run_dir, ScriptedRunner([NOOP]), LocalCompute(), max_iters=1)
    rows = rows_of(run_dir)
    assert rows[0].status == "interrupted" and rows[0].iter == 1
    assert math.isnan(rows[0].cost_usd), "被中断那一轮的成本是未知，不是 0"
    assert rows[1].iter == 2 and stop.reason == "batch_exhausted"


def test_resume_fails_closed_when_ledger_and_checkpoint_disagree(tmp_path):
    run_dir, _ = start_run(tmp_path)
    run_loop(run_dir, ScriptedRunner([train_for_mse(0.018)]), LocalCompute(), max_iters=1)
    state = read_checkpoint(run_dir)
    write_checkpoint(run_dir, {**state, "last_iter": 7, "stop_reason": None})
    with pytest.raises(ResumeMismatch):
        resume_loop(run_dir, ScriptedRunner([NOOP]), LocalCompute())


def test_resume_clears_a_stale_marker_when_the_round_was_already_settled(tmp_path):
    """崩溃窗口一：_settle 全做完了，只剩 inflight.json 没删就被杀——清掉标记接着跑。"""
    run_dir, _ = start_run(tmp_path)
    run_loop(run_dir, ScriptedRunner([train_for_mse(0.018)]), LocalCompute(), max_iters=1)
    settled = read_checkpoint(run_dir)
    mark_inflight(run_dir, 1)

    stop = resume_loop(run_dir, ScriptedRunner([NOOP]), LocalCompute(), max_iters=1)
    rows = rows_of(run_dir)
    assert [r.iter for r in rows] == [1, 2], "已经结算过的那一轮不许被记第二遍"
    assert rows[0].status == "keep" and rows[1].status == "noop"
    state = read_checkpoint(run_dir)
    assert state["best_commit"] == settled["best_commit"] and state["best_iter"] == 1
    assert stop.reason == "batch_exhausted"
    assert not inflight_path(run_dir).exists()


def test_resume_rebuilds_checkpoint_when_the_ledger_is_one_row_ahead(tmp_path):
    """崩溃窗口二：账本记完、checkpoint 还没写就被杀——以账本为准把 best 前移。"""
    run_dir, _ = start_run(tmp_path)
    run_loop(run_dir, ScriptedRunner([train_for_mse(0.018)]), LocalCompute(), max_iters=1)
    settled = read_checkpoint(run_dir)
    baseline = gitwork.root_commit(run_dir / "work")
    write_checkpoint(run_dir, {**settled, "last_iter": 0, "best_iter": 0,
                                    "best_metric": 0.030, "best_commit": baseline})
    mark_inflight(run_dir, 1)

    resume_loop(run_dir, ScriptedRunner([NOOP]), LocalCompute(), max_iters=1)
    rows = rows_of(run_dir)
    assert [r.iter for r in rows] == [1, 2] and rows[0].status == "keep"
    state = read_checkpoint(run_dir)
    assert state["best_iter"] == 1 and state["best_commit"] == settled["best_commit"]
    assert state["best_metric"] == pytest.approx(0.018)
    assert gitwork.head(run_dir / "work") == settled["best_commit"]


def test_resume_fails_closed_when_a_keep_row_and_head_disagree(tmp_path):
    """账本领先一行说是 keep，HEAD 却不是那个 commit：三方对不上，停。"""
    run_dir, _ = start_run(tmp_path)
    run_loop(run_dir, ScriptedRunner([train_for_mse(0.018)]), LocalCompute(), max_iters=1)
    settled = read_checkpoint(run_dir)
    baseline = gitwork.root_commit(run_dir / "work")
    write_checkpoint(run_dir, {**settled, "last_iter": 0, "best_iter": 0,
                                    "best_metric": 0.030, "best_commit": baseline})
    gitwork.revert_to(run_dir / "work", baseline)  # HEAD 退回基线，与 keep 行对不上了
    mark_inflight(run_dir, 1)
    with pytest.raises(ResumeMismatch) as exc:
        resume_loop(run_dir, ScriptedRunner([NOOP]), LocalCompute(), max_iters=1)
    assert "keep" in str(exc.value) and "HEAD" in str(exc.value)


def test_run_refuses_to_start_while_a_round_is_in_flight(tmp_path):
    """有 in-flight 标记时 `loop run` 不许从中间接着跑：那一轮的账会漏掉。"""
    run_dir, _ = start_run(tmp_path)
    mark_inflight(run_dir, 1)
    runner = ScriptedRunner([NOOP])
    with pytest.raises(InflightPending) as exc:
        run_loop(run_dir, runner, LocalCompute(), max_iters=1)
    assert "第 1 轮没走完" in str(exc.value)
    assert "cap auto-research --continue experiment/1 --resume" in str(exc.value)
    assert runner.calls == 0, "还没收尸就不该叫执行层"


def test_keyboard_interrupt_cancels_the_in_flight_job(tmp_path):
    """被 Ctrl-C 打断时先杀在飞的 harness 再把异常抛上去，不留一组进程烧算力。"""
    class _KilledDuringWait(LocalCompute):
        def __init__(self) -> None:
            super().__init__()
            self.cancelled: list[Job] = []

        def wait(self, job: Job, timeout_s: float | None = None):
            raise KeyboardInterrupt  # submit 之后、拿到结果之前被杀

        def cancel(self, job: Job) -> None:
            self.cancelled.append(job)
            super().cancel(job)

    run_dir, _ = start_run(tmp_path)
    compute = _KilledDuringWait()
    with pytest.raises(KeyboardInterrupt):
        run_loop(run_dir, ScriptedRunner([SLEEPY_TRAIN]), compute, max_iters=1)
    job = Job.from_json(
        (run_dir / "iters" / "iter_1" / "job.json").read_text(encoding="utf-8"))
    assert [j.pgid for j in compute.cancelled] == [job.pgid], "在飞的任务没被 cancel"
    assert not group_alive(job.pgid), "被中断的那一轮还留着活着的进程组"


# ── A-6 / A-7：假成功与动 harness ───────────────────────────────────────
def test_a6_fake_success_is_no_results_and_rolls_back(tmp_path):
    """严格 launcher（set -e）下 evaluate 拒收产物会让整条链退非 0，仍须判 no_results。"""
    run_dir, _ = start_run(tmp_path)
    baseline = (run_dir / "work" / "code" / "train.py").read_text(encoding="utf-8")
    stop = run_loop(run_dir, ScriptedRunner([FAKE_SUCCESS]), LocalCompute(), max_iters=1)
    row = rows_of(run_dir)[0]
    state = read_checkpoint(run_dir)
    assert row.status == "no_results" and row.metric is None
    assert (run_dir / "work" / "code" / "train.py").read_text(encoding="utf-8") == baseline
    assert gitwork.head(run_dir / "work") == state["best_commit"]
    assert state["best_metric"] == 0.030 and stop.reason == "batch_exhausted"


def test_a7_touching_harness_is_readonly_violated_and_hash_restored(tmp_path):
    run_dir, _ = start_run(tmp_path)
    work = run_dir / "work"
    before = (work / "harness" / "evaluate.py").read_text(encoding="utf-8")
    run_loop(run_dir, ScriptedRunner([tamper_harness]), LocalCompute(), max_iters=1)
    row = rows_of(run_dir)[0]
    assert row.status == "readonly_violated" and row.commit == ledger.MISSING
    assert (work / "harness" / "evaluate.py").read_text(encoding="utf-8") == before
    assert gitwork.head(work) == read_checkpoint(run_dir)["best_commit"]
    assert _sums_match(work), "回滚后 harness 的 SHA256SUMS 与磁盘对不上"


def test_changes_swallowed_by_gitignore_are_recorded_as_noop(tmp_path):
    """改动全被包里的 .gitignore 挡住：git 里留不下东西，按没改记账并把原因说清楚。"""
    pack = make_loop_pack(tmp_path)
    (pack.pack / ".gitignore").write_text("code/*.bin\n", encoding="utf-8")
    run_dir = open_run(pack)
    runner = ScriptedRunner([IGNORED_BLOB])
    run_loop(run_dir, runner, LocalCompute(), max_iters=1)
    row = rows_of(run_dir)[0]
    assert runner.prompts, "这一轮该叫过执行层"
    assert row.status == "noop" and row.commit == ledger.MISSING
    assert ".gitignore" in row.note
    assert math.isnan(row.elapsed_s), "harness 没跑，耗时是未知不是 0"
    assert gitwork.is_clean(run_dir / "work"), "被忽略的产物没跟着回滚清掉"


def _sums_match(work: Path) -> bool:
    import hashlib

    hdir = work / "harness"
    for line in (hdir / "SHA256SUMS").read_text(encoding="utf-8").splitlines():
        expected, name = line.split(None, 1)
        if hashlib.sha256((hdir / name.strip()).read_bytes()).hexdigest() != expected:
            return False
    return True


# ── 统计门退化：σ=0 与 min_delta ───────────────────────────────────────
def make_flat_pack(tmp_path: Path, **budget: object) -> pf.Pack:
    """基线三次重复完全一致 → σ=0，统计门退化。"""
    scoring = pf.default_scoring()
    scoring["budget"] = loop_budget(**budget)
    return pf.make_pack(tmp_path, scoring=scoring, seeds=SEEDS,
                        values=(0.030, 0.030, 0.030), elapsed_s=1.0)


def test_zero_sigma_without_min_delta_fails_closed(tmp_path):
    """门是 0 在开实验的预检就停（外层 #48），不铺一个开了跑不了的实验；loop 那道检查仍在。"""
    pack = make_flat_pack(tmp_path)
    with pytest.raises(PackInvalid) as exc:
        open_run(pack)
    assert "min_delta" in str(exc.value) and "σ=0" in str(exc.value)
    assert not (pack.workspace.root / "experiment" / "1" / "work").exists(), "门都立不起来就不该铺"


def test_min_delta_is_the_gate_when_sigma_is_zero(tmp_path):
    pack = make_flat_pack(tmp_path, min_delta=0.01)
    run_dir = open_run(pack)
    script = [train_for_mse(0.025), train_for_mse(0.015)]
    run_loop(run_dir, ScriptedRunner(script), LocalCompute(), max_iters=2)
    rows = rows_of(run_dir)
    assert rows[0].status == "discard" and "within noise" in rows[0].note
    assert "gate=0.01" in rows[0].note, "门该是 min_delta，不是退化后的 0"
    assert rows[1].status == "keep"
    assert read_checkpoint(run_dir)["best_metric"] == pytest.approx(0.015)


# ── 停止条件 ────────────────────────────────────────────────────────────
def test_three_same_failures_in_a_row_stop_as_unrecoverable(tmp_path):
    run_dir, _ = start_run(tmp_path)
    runner = ScriptedRunner([CRASH_TRAIN, CRASH_TRAIN, CRASH_TRAIN, train_for_mse(0.001)])
    stop = run_loop(run_dir, runner, LocalCompute(), max_iters=10)
    assert stop.reason == "unrecoverable:crash" and stop.iter == 3
    assert runner.calls == 3, "判不可修复之后不该再叫执行层"
    _assert_stop_json_matches(run_dir, stop)


def test_patience_stops_after_consecutive_no_improvement(tmp_path):
    run_dir, _ = start_run(tmp_path, patience=3)
    runner = ScriptedRunner([train_for_mse(0.5), NOOP, train_for_mse(0.6), train_for_mse(0.7)])
    stop = run_loop(run_dir, runner, LocalCompute(), max_iters=10)
    assert stop.reason == "patience" and stop.iter == 3
    _assert_stop_json_matches(run_dir, stop)


def test_max_cost_stops_the_loop(tmp_path):
    run_dir, _ = start_run(tmp_path, max_cost_usd=0.025)
    runner = ScriptedRunner([NOOP, NOOP, NOOP, NOOP], cost_usd=0.01)
    stop = run_loop(run_dir, runner, LocalCompute(), max_iters=10)
    assert stop.reason == "max_cost_usd" and stop.iter == 3
    _assert_stop_json_matches(run_dir, stop)


def test_max_iterations_from_scoring_caps_the_run(tmp_path):
    run_dir, _ = start_run(tmp_path, max_iterations=2)
    runner = ScriptedRunner([NOOP, NOOP, NOOP])
    stop = run_loop(run_dir, runner, LocalCompute(), max_iters=10)
    assert stop.reason == "max_iterations" and stop.iter == 2
    assert runner.calls == 2


def test_max_iters_is_a_batch_not_a_cap_on_the_run(tmp_path):
    """--max-iters 是本次增量：max_iters=2 跑两次就是 4 轮，中间不写 stop、不锁 run。"""
    run_dir, _ = start_run(tmp_path)
    first = run_loop(run_dir, ScriptedRunner([NOOP, NOOP]), LocalCompute(), max_iters=2)
    assert first.reason == "batch_exhausted" and first.iter == 2
    assert not (run_dir / "stop.json").exists(), "配额用完不是实验的结局"
    assert read_checkpoint(run_dir)["stop_reason"] is None

    second = run_loop(run_dir, ScriptedRunner([NOOP, NOOP]), LocalCompute(), max_iters=2)
    assert second.reason == "batch_exhausted" and second.iter == 4
    assert [r.iter for r in rows_of(run_dir)] == [1, 2, 3, 4]


def test_stopped_run_does_not_restart_itself(tmp_path):
    """scoring 触顶写下的 stop_reason 会锁住这次实验；本次配额用完则不会。"""
    run_dir, _ = start_run(tmp_path, max_iterations=1)
    run_loop(run_dir, ScriptedRunner([NOOP]), LocalCompute())
    assert read_checkpoint(run_dir)["stop_reason"] == "max_iterations"
    again = ScriptedRunner([NOOP])
    stop = run_loop(run_dir, again, LocalCompute())
    assert stop.reason == "max_iterations" and again.calls == 0


def _assert_stop_json_matches(run_dir: Path, stop: StopReason) -> None:
    doc = json.loads((run_dir / "stop.json").read_text(encoding="utf-8"))
    state = read_checkpoint(run_dir)
    assert doc == {"reason": stop.reason, "iter": stop.iter, "best_metric": stop.best_metric}
    assert state["stop_reason"] == stop.reason and state["last_iter"] == stop.iter
    assert state["best_metric"] == stop.best_metric


# ── 开实验与提示 ─────────────────────────────────────────────────────
def test_open_experiment_lays_out_the_disk_and_rejects_broken_packs(tmp_path):
    run_dir, pack = start_run(tmp_path)
    assert (run_dir / "scoring.yaml").is_file()
    assert (run_dir / "prompts" / "requirement.md").is_file()
    assert (run_dir / "journal.md").read_text(encoding="utf-8") == ""
    assert (run_dir / "iters").is_dir() and (run_dir / "meta.yaml").is_file()
    assert not (run_dir / "work" / "meta.yaml").exists(), "框架的账不该跟着拷进 work/"
    assert gitwork.is_clean(run_dir / "work")
    state = read_checkpoint(run_dir)
    assert state["best_metric"] == 0.030 and state["output"] == "experiment/1"
    # 设计那包坏了：契约校验拦下，不铺
    (pack.pack / "scoring.yaml").write_text("format_version: 1\n", encoding="utf-8")
    with pytest.raises(PackInvalid, match="不合约"):
        open_run(pack)


def test_prompt_is_constant_size_and_carries_the_fix_hint(tmp_path):
    run_dir, _ = start_run(tmp_path)
    runner = ScriptedRunner([CRASH_TRAIN, NOOP, NOOP, NOOP, NOOP, NOOP, NOOP])
    run_loop(run_dir, runner, LocalCompute(), max_iters=7)
    assert "只准改 `code/`" in runner.prompts[0] or "只改 `code/`" in runner.prompts[0]
    assert "先照 stderr 摘要修掉报错" in runner.prompts[1], "上一轮的修复提示没喂给执行层"
    tail = runner.prompts[-1].split("## 最近的账本")[1].split("## 上一轮")[0]
    assert tail.count("- 第") == 5, "账本摘要必须是常数大小（最近 5 行）"


def test_domain_prompt_is_appended_when_present(tmp_path):
    pack = make_loop_pack(tmp_path)
    extra = pack.domains_root / "generic" / "prompts"
    extra.mkdir(parents=True)
    (extra / "experiment.md").write_text("本领域：先看数据再动模型。", encoding="utf-8")
    run_dir = open_run(pack)
    runner = ScriptedRunner([NOOP])
    run_loop(run_dir, runner, LocalCompute(), max_iters=1)
    assert "本领域：先看数据再动模型。" in runner.prompts[0]


def test_script_exhausted_is_loud(tmp_path):
    run_dir, _ = start_run(tmp_path)
    with pytest.raises(ScriptExhausted):
        run_loop(run_dir, ScriptedRunner([NOOP]), LocalCompute(), max_iters=3)


def test_executor_logs_are_stashed_per_iteration_and_survive_revert(tmp_path):
    """适配器写在 work/.ai4sci/ 的事件流必须搬到 executor/iter-N/：
    revert-to-best 用 git clean -x，留在 work/ 里的日志下一轮开头就没了（真跑时丢过一次）。"""
    run_dir, _ = start_run(tmp_path)
    run_loop(run_dir, ScriptedRunner([train_for_mse(0.018), FAKE_SUCCESS]), LocalCompute(),
                  max_iters=2)
    stash = run_dir / "executor"
    assert sorted(p.name for p in stash.iterdir()) == ["iter-1", "iter-2"]
    assert list((stash / "iter-2").glob("executor-*.jsonl"))
    assert not (run_dir / "work" / ".ai4sci").exists()


def test_no_results_note_carries_the_harness_reason(tmp_path):
    """harness 拒收产物的原因在 stderr 末行；账本 note 与下一轮提示都要带上它。"""
    run_dir, _ = start_run(tmp_path)
    runner = ScriptedRunner([FAKE_SUCCESS, train_for_mse(0.018)])
    run_loop(run_dir, runner, LocalCompute(), max_iters=2)
    row = rows_of(run_dir)[0]
    assert row.status == "no_results"
    assert "stderr 末行" in row.note and "predictions.json" in row.note
    assert "predictions.json" in runner.prompts[1]


# ── 轮间记忆：实验笔记 ───────────────────────────────────────────────────
def test_notebook_records_each_round_and_feeds_the_next_prompt(tmp_path):
    """执行层的自述 + diff stat + 裁决每轮进笔记；下一轮的 prompt 里整本都在（#28）。"""
    run_dir, _ = start_run(tmp_path)
    runner = ScriptedRunner([train_for_mse(0.018), train_for_mse(0.0175)])
    runner.reports = ["假设：步长太大。改动：LR 减半。预期：更稳。",
                      "假设：再减一点。改动：LR 再减半。预期：略好。"]
    run_loop(run_dir, runner, LocalCompute(), max_iters=2)
    text = (run_dir / "notebook.md").read_text(encoding="utf-8")
    assert "第 1 轮 · keep" in text and "LR 减半" in text and "code/train.py" in text
    assert "第 2 轮 · discard" in text and "within noise" in text
    assert "还没有笔记" in runner.prompts[0]
    assert "LR 减半" in runner.prompts[1] and "不要重复已经试过" in runner.prompts[1]


def test_notebook_survives_revert_to_best(tmp_path):
    """笔记活在棘轮之外：discard 后 work/ 被 reset，笔记一个字不少。"""
    run_dir, _ = start_run(tmp_path)
    run_loop(run_dir, ScriptedRunner([train_for_mse(0.018), FAKE_SUCCESS]), LocalCompute(),
                  max_iters=2)
    text = (run_dir / "notebook.md").read_text(encoding="utf-8")
    assert text.count("### 第 ") == 2 and "no_results" in text


# ── 加预算：协调层给已停的实验加预算 ─────────────────────────────────────
def test_extend_experiment_clears_stop_and_lets_the_loop_continue(tmp_path):
    run_dir, _ = start_run(tmp_path, patience=1)
    stop = run_loop(run_dir, ScriptedRunner([train_for_mse(0.0299)]), LocalCompute())
    assert stop.reason == "patience" and (run_dir / "stop.json").is_file()
    done = extend_experiment(run_dir, patience=5, reason="统计门偏严，再给几轮")
    assert done["cleared"] == "patience" and done["changes"] == ["patience: 1 → 5"]
    assert read_checkpoint(run_dir)["stop_reason"] is None
    assert not (run_dir / "stop.json").exists()
    assert "加预算" in (run_dir / "journal.md").read_text(encoding="utf-8")
    stop = run_loop(run_dir, ScriptedRunner([train_for_mse(0.018)]), LocalCompute(),
                         max_iters=1)
    assert stop.reason == "batch_exhausted" and rows_of(run_dir)[-1].status == "keep"


def test_extend_experiment_rejects_nonpositive_budget(tmp_path):
    run_dir, _ = start_run(tmp_path)
    with pytest.raises(AssertionError):
        extend_experiment(run_dir, patience=0)


# ── 执行层会话没走完：被杀 / 超时 / CLI 崩 ─────────────────────────────
def test_executor_killed_mid_round_is_a_recorded_failure_not_a_crash(tmp_path):
    """真跑第 10 轮 kill -9 执行层时整个内环炸了；现在是可记账的一轮：改动丢弃、回到 best、继续。"""
    run_dir, _ = start_run(tmp_path)
    baseline = (run_dir / "work" / "code" / "train.py").read_text(encoding="utf-8")
    runner = ScriptedRunner([train_for_mse(0.018), train_for_mse(0.018)], die_at=(1,))
    run_loop(run_dir, runner, LocalCompute(), max_iters=2)
    rows = rows_of(run_dir)
    assert rows[0].status == "executor_failed" and rows[0].commit == ledger.MISSING
    assert "退出码 -9" in rows[0].note
    assert rows[0].cost_usd is None or math.isnan(rows[0].cost_usd)
    assert rows[1].status == "keep"
    assert "执行层会话没走完" in runner.prompts[1]
    # 第 1 轮改了一半就被杀：起第 2 轮前必须回到基线，第 2 轮 keep 后才离开基线
    assert (run_dir / "work" / "code" / "train.py").read_text(encoding="utf-8") != baseline


def test_three_executor_failures_in_a_row_are_unrecoverable(tmp_path):
    run_dir, _ = start_run(tmp_path)
    runner = ScriptedRunner([train_for_mse(0.018)] * 4, die_at=(1, 2, 3))
    stop = run_loop(run_dir, runner, LocalCompute())
    assert stop.reason == "unrecoverable:executor_failed" and runner.calls == 3


def test_extend_after_unrecoverable_forgives_the_failures_before_it(tmp_path):
    """真跑：执行层连不上模型三次判不可修复，加预算后内环一起来又数到同样三行、当场再停。"""
    run_dir, _ = start_run(tmp_path)
    runner = ScriptedRunner([train_for_mse(0.018)] * 4, die_at=(1, 2, 3))
    assert run_loop(run_dir, runner, LocalCompute()).reason == "unrecoverable:executor_failed"
    extend_experiment(run_dir, patience=10, reason="外部原因，续跑")
    assert read_checkpoint(run_dir)["resumed_after_iter"] == 3
    stop = run_loop(run_dir, runner, LocalCompute(), max_iters=1)
    assert runner.calls == 4 and stop.reason == "batch_exhausted"
    assert rows_of(run_dir)[-1].status == "keep"


# ── 保证的环境变量与「改动没生效」（外层 #43 #44 #45）────────────────────
ENV_RECORDING_TRAIN = {"code/train.py": (
    "import json\nimport os\nfrom pathlib import Path\n"
    "TASK_DIR = Path(__file__).resolve().parent.parent\n"
    "(TASK_DIR / 'predictions.json').write_text(json.dumps({'y_pred': [0.1]}))\n"
    "(TASK_DIR / 'env-seen.json').write_text(json.dumps("
    "{k: v for k, v in os.environ.items() if k.startswith('AI4SCI_')}))\n"
)}


def test_harness_gets_budget_and_inner_k_from_the_framework(tmp_path):
    run_dir, _ = start_run(tmp_path, inner_k=4)
    run_loop(run_dir, ScriptedRunner([ENV_RECORDING_TRAIN]), LocalCompute(), max_iters=1)
    seen = json.loads((run_dir / "iters" / "iter_1" / "env-seen.json")
                      .read_text(encoding="utf-8"))
    assert seen["AI4SCI_INNER_K"] == "4" and seen["AI4SCI_BUDGET_S"] == "2"
    assert seen["AI4SCI_SEED"] == "42" and seen["AI4SCI_PYTHON"].endswith("/.venv/bin/python")


def test_inner_k_defaults_to_one_and_rejects_zero(tmp_path):
    run_dir, _ = start_run(tmp_path)
    assert load_context(run_dir).inner_k == 1
    scoring = yaml.safe_load((run_dir / "scoring.yaml").read_text(encoding="utf-8"))
    scoring["budget"]["inner_k"] = 0
    (run_dir / "scoring.yaml").write_text(yaml.safe_dump(scoring), encoding="utf-8")
    with pytest.raises(AssertionError, match="inner_k"):
        load_context(run_dir)


def test_identical_metric_is_flagged_as_no_effect_and_hinted_next_round(tmp_path):
    """rahman-1 第 2 轮：换撒点方式后分数与基线一模一样，判 discard 但要说清"改动没生效"。"""
    run_dir, _ = start_run(tmp_path)
    runner = ScriptedRunner([train_for_mse(0.030), train_for_mse(0.018)])
    run_loop(run_dir, runner, LocalCompute(), max_iters=2)
    rows = rows_of(run_dir)
    assert rows[0].status == "discard" and rows[0].note == gate.NO_EFFECT_NOTE
    assert "改动没有影响结果" in runner.prompts[1]
    assert rows[1].status == "keep"
