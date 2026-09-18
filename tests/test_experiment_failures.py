"""六类失败分类的单测：优先级、边界、取证读法。

`classify_run` 是纯函数，输入摆得出来就该逐条钉死——内环那边跑真 harness 的用例
（test_experiment_loop.py）只能证明"整条链连得上"，证明不了优先级的顺序对不对。

最后一条是内环用例：harness 自己动 data/，必须判 readonly_violated 并回滚。
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import pytest

from compute.local import LocalCompute
from framework.capabilities.auto_research import failures, run_loop
from framework.contracts.results import read_results
from framework.memory import ledger
from framework.run import gitwork
from framework.run.checkpoint import read_checkpoint
from framework.run.lifecycle import new_run
from tests.fixtures import packs_factory as pf
from tests.fixtures.scripted_backend import ScriptedRunner
from tests.test_experiment_loop import make_loop_pack, train_for_mse

TRACEBACK = 'Traceback (most recent call last):\n  File "code/train.py", line 1\nValueError: 崩了\n'
IMPORT_ERROR = ("Traceback (most recent call last):\n"
                "ModuleNotFoundError: No module named 'torch'\n")


def classify(**kw):
    """默认是一趟干净的成功，用关键字逐条替换成要考的那一种。"""
    base = dict(tampered=[], timed_out=False, exit_code=0, stderr_tail="",
                results_problems=[], metric=0.5)
    return failures.classify_run(**{**base, **kw})


# ── 优先级：从上到下，第一条命中即返回 ────────────────────────────────
def test_readonly_beats_everything_else():
    verdict = classify(tampered=["data/val.json"], timed_out=True, exit_code=1,
                       stderr_tail=TRACEBACK, results_problems=["缺文件"], metric=math.nan)
    assert verdict.status == failures.READONLY_VIOLATED and "data/val.json" in verdict.note


def test_timeout_beats_the_rest():
    verdict = classify(timed_out=True, exit_code=-9, stderr_tail=TRACEBACK,
                       results_problems=["缺文件"], metric=None)
    assert verdict.status == failures.TIMEOUT


def test_missing_dependency_beats_crash():
    verdict = classify(exit_code=1, stderr_tail=IMPORT_ERROR, results_problems=["缺文件"],
                       metric=None)
    assert verdict.status == failures.MISSING_DEPENDENCY and "1" in verdict.note


def test_traceback_is_a_crash():
    verdict = classify(exit_code=1, stderr_tail=TRACEBACK, results_problems=["缺文件"],
                       metric=None)
    assert verdict.status == failures.CRASH and "崩了" in verdict.note


def test_syntax_error_without_traceback_header_is_still_a_crash():
    """主脚本语法错时 CPython 不打 traceback 头，只打 SyntaxError:，同样是崩溃不是假成功。"""
    stderr = '  File "code/train.py", line 3\n    def (:\n        ^\nSyntaxError: invalid syntax\n'
    verdict = classify(exit_code=1, stderr_tail=stderr, results_problems=["缺文件"], metric=None)
    assert verdict.status == failures.CRASH and "SyntaxError" in verdict.note


def test_nonzero_without_traceback_is_no_results_not_crash():
    """真任务包的 evaluate 拒收产物时是 SystemExit 加一句话：这是假成功，不是崩溃。"""
    verdict = classify(exit_code=2, stderr_tail="evaluate: 文件缺失：predictions.json\n",
                       results_problems=["results.json 缺失：/tmp/run_1/results.json"],
                       metric=None)
    assert verdict.status == failures.NO_RESULTS and "缺失" in verdict.note


def test_unknown_exit_code_is_not_a_pass():
    """续跑读回的 job 拿不到退出码：未知不是成功，产物齐了也只能按崩溃收。"""
    verdict = classify(exit_code=None)
    assert verdict.status == failures.CRASH and "未知" in verdict.note


def test_status_not_ok_is_no_results():
    verdict = classify(results_problems=["harness 自报 status='failed'，不是 ok"])
    assert verdict.status == failures.NO_RESULTS and "failed" in verdict.note


def test_missing_primary_metric_is_no_results():
    assert classify(metric=None).status == failures.NO_RESULTS


def test_nan_metric_is_its_own_class():
    assert classify(metric=math.nan).status == failures.NAN_METRIC
    assert classify(metric=math.inf).status == failures.NAN_METRIC


def test_a_clean_run_has_no_verdict():
    assert classify() is None


def test_every_failure_class_has_a_fix_hint():
    for status in failures.FAILURE_STATUSES:
        assert failures.HINTS[status], f"{status} 缺一句修复提示"


# ── read_results：产物怎么读 ──────────────────────────────────────────
def _results(tmp_path: Path, doc: object) -> Path:
    path = tmp_path / "results.json"
    path.write_text(json.dumps(doc), encoding="utf-8")
    return path


def ok_doc(**kw) -> dict:
    return {"metrics": {"val_mse": 0.5}, "elapsed_s": 1.0, "seed": 42, "status": "ok", **kw}


def test_read_results_takes_nan_through_so_it_can_be_classified(tmp_path):
    """NaN 不算"文件不合法"：它要走 nan_metric，在这里判成 no_results 会把病因说错。"""
    path = _results(tmp_path, ok_doc(metrics={"val_mse": float("nan")}))
    metric, problems = read_results(path, "val_mse")
    assert math.isnan(metric) and problems == []
    assert classify(metric=metric).status == failures.NAN_METRIC


def test_read_results_reports_a_missing_primary_metric(tmp_path):
    path = _results(tmp_path, ok_doc(metrics={"train_mse": 0.5}))
    metric, problems = read_results(path, "val_mse")
    assert metric is None and any("val_mse" in p for p in problems)


def test_read_results_reports_schema_violations(tmp_path):
    path = _results(tmp_path, {"metrics": {"val_mse": 0.5}, "elapsed_s": 1.0, "seed": 42})
    metric, problems = read_results(path, "val_mse")
    assert metric == 0.5 and any("schema" in p for p in problems)
    assert classify(metric=metric, results_problems=problems).status == failures.NO_RESULTS


def test_read_results_reports_harness_self_reported_status(tmp_path):
    path = _results(tmp_path, ok_doc(status="failed"))
    metric, problems = read_results(path, "val_mse")
    assert metric == 0.5, "指标照读，但它作废了"
    assert any("status='failed'" in p for p in problems)


def test_read_results_missing_file_and_broken_json(tmp_path):
    metric, problems = read_results(tmp_path / "没有.json", "val_mse")
    assert metric is None and any("缺失" in p for p in problems)
    broken = tmp_path / "results.json"
    broken.write_text("{不是 json", encoding="utf-8")
    metric, problems = read_results(broken, "val_mse")
    assert metric is None and any("解析失败" in p for p in problems)


def test_read_results_rejects_a_non_numeric_metric(tmp_path):
    path = _results(tmp_path, ok_doc(metrics={"val_mse": "0.5"}))
    metric, problems = read_results(path, "val_mse")
    assert metric is None and any("不是数字" in p for p in problems)


# ── 内环用例：harness 自己动 data/ ────────────────────────────────────
TAMPERING_LAUNCHER = """#!/usr/bin/env bash
set -euo pipefail
TASK_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$TASK_DIR"
rm -f predictions.json results.json
echo '{"y_true": [0.0]}' > data/val.json
"$AI4SCI_PYTHON" code/train.py
"$AI4SCI_PYTHON" harness/evaluate.py
"""


def test_harness_touching_data_is_readonly_violated_and_rolls_back(tmp_path):
    """成绩再好也不算：只读区被动过，这一轮整个作废并回到 best。"""
    pack = make_loop_pack(tmp_path)
    (pack.task_dir / "data").mkdir()
    (pack.task_dir / "data" / "val.json").write_text('{"y_true": [1.0]}', encoding="utf-8")
    (pack.task_dir / "harness" / "launcher.sh").write_text(TAMPERING_LAUNCHER, encoding="utf-8")
    pf.refresh_sums(pack.task_dir)
    run_dir = new_run(pack.task_dir, tmp_path / "runs", "r-tampered",
                           domains_root=pack.domains_root)
    work = run_dir / "work"
    before = (work / "data" / "val.json").read_text(encoding="utf-8")

    run_loop(run_dir, ScriptedRunner([train_for_mse(0.001)]), LocalCompute(), max_iters=1)
    row = ledger.read(run_dir / "experiment" / "ledger.tsv")[0]
    state = read_checkpoint(run_dir)
    assert row.status == "readonly_violated" and "data/val.json" in row.note
    # 账本会留下它跑出来的那个数（那是证据：它动了真值之后自称多少分），但裁决是
    # readonly_violated，这个数不进 best，也不参与统计门
    assert row.metric == pytest.approx(0.001)
    assert (work / "data" / "val.json").read_text(encoding="utf-8") == before
    assert gitwork.head(work) == state["best_commit"] == row.parent
    assert state["best_metric"] == pytest.approx(0.030), "best 不许被这一轮带走"
    assert gitwork.rev_parse(work, row.commit) in set(gitwork.attempt_refs(work).values())
