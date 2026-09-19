"""有账本、有 best、有三轮 results.json 的实验产出夹具，以及一份与它的 results.json 一致的分析产出。

分析能力、验证能力与 CLI 的测试都要"一次跑过实验的产出"，剧本内环三轮就够：
keep（过门）、discard（门内）、keep。分析文本从磁盘上的 results.json 现生成，
不手抄数字——手抄一个浮点尾数就会把"验证能对上"测成"验证太宽"。
"""

from __future__ import annotations

from pathlib import Path

from compute.local import LocalCompute
from framework.capabilities.auto_research import run_loop
from framework.experiment import artifacts
from framework.experiment.results import read_metrics
from framework.workspace import outputs
from tests.fixtures import packs_factory as pf
from tests.fixtures.scripted_backend import ScriptedRunner
from tests.test_experiment_loop import start_run, train_for_mse

ROUNDS = (0.015, 0.012, 0.001)  # 基线 0.030、门 0.01：keep、discard（门内）、keep
REPORTS = ("假设：加一层。改动：train.py。预期：降。",
           "假设：调学习率。改动：train.py。预期：微降。",
           "假设：加宽。改动：train.py。预期：大降。")


def make_run(tmp_path: Path) -> tuple[Path, pf.Pack]:
    """跑三轮的 experiment/1（meta 记成 ok），连同它读的设计产出。"""
    run_dir, pack = start_run(tmp_path)
    runner = ScriptedRunner([train_for_mse(v) for v in ROUNDS])
    runner.reports = list(REPORTS)
    stop = run_loop(run_dir, runner, LocalCompute(), max_iters=len(ROUNDS))
    assert stop.reason == "batch_exhausted", stop
    _, meta = outputs.find_output(pack.workspace, "experiment/1")
    outputs.close_output(run_dir, meta, ok=True, line=f"stop {stop.reason}")
    return run_dir, pack


def metrics_of(run_dir: Path) -> dict[str, dict[str, float]]:
    found = {}
    for name, path in artifacts.run_results(run_dir).items():
        metrics, problems = read_metrics(path)
        assert metrics is not None, problems
        found[name] = metrics
    return found


def good_analysis(run_dir: Path, metric: str = "val_mse", oid: str = "experiment/1") -> str:
    """三节齐全、数据表从 results.json 原样抄、正文只引用表里的值。"""
    metrics = metrics_of(run_dir)
    rows = "\n".join(f"| {oid}/{name} | {metric} | {m[metric]!r} |" for name, m in metrics.items())
    base, best = metrics["baseline"][metric], metrics["iter_3"][metric]
    return (
        f"# {oid} 的分析\n\n"
        "## 结论\n\n"
        f"best 是 {oid}/iter_3 的 {best!r}，基线 {oid}/baseline 是 {base!r}，降了 96.7%，"
        "共 3 轮，留下 2 轮。\n\n"
        "## 数据\n\n"
        "| 来源 | 指标 | 值 |\n|---|---|---|\n" + rows + "\n\n"
        "## 证伪与未决\n\n"
        "第 2 轮在统计门内（within noise），不能说调学习率有效。\n"
    )


def write_analysis(pack: pf.Pack, text: str, *,
                   inputs: tuple[str, ...] = ("experiment/1",)) -> Path:
    """一次分析产出 analysis/1/：meta 记读了哪次实验，正文是 text。返回目录。"""
    directory, meta = outputs.open_output(
        pack.workspace, "analysis", title="写分析初稿", by="analysis", inputs=list(inputs),
        params={}, flow=None, step=None, requirement=1, chat_id=None)
    (directory / "analysis.md").write_text(text, encoding="utf-8")
    outputs.close_output(directory, meta, ok=True, line="analysis ok")
    return directory
