"""分析能力：零模型的部分（收集输入、组 prompt、判产物形状）用剧本执行层测全。

执行层写什么由剧本决定，所以能一条条摆出来：合约的、缺一节的、越界的、死掉的、
什么都没写的。数字对不对不在这里测——那是验证能力的事（P-2）。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from framework.capabilities import analysis
from framework.contracts.capability import CapabilityFailed, Inputs, Ports
from framework.workspace import outputs
from tests.fixtures import packs_factory as pf
from tests.fixtures import runs_factory as rf
from tests.fixtures.scripted_backend import ScriptedRunner
from tests.test_experiment_loop import start_run


@pytest.fixture(scope="module")
def made(tmp_path_factory) -> tuple[Path, pf.Pack]:
    return rf.make_run(tmp_path_factory.mktemp("analysis"))


def _out(pack: pf.Pack) -> tuple[Path, Inputs]:
    """一次新的分析产出目录 + 读 experiment/1 的输入。"""
    directory, _ = outputs.open_output(pack.workspace, "analysis", title="t", by="analysis",
                                       inputs=["experiment/1"], params={}, flow=None, step=None,
                                       requirement=1, chat_id=None)
    run_dir = pack.workspace.root / "experiment" / "1"
    return directory, Inputs(pack.workspace.root, (run_dir,), ("experiment/1",))


def _runner(*moves) -> ScriptedRunner:
    return ScriptedRunner(list(moves))


def test_analysis_writes_the_doc_and_reports_claims(made):
    run_dir, pack = made
    out, inputs = _out(pack)
    runner = _runner({"analysis.md": rf.good_analysis(run_dir)})
    line = analysis.run(out, inputs, Ports(runner=runner))
    assert line.startswith("analysis ok\tclaims=4\tcost_usd=0.0100\tpath=analysis.md")
    assert (out / "analysis.md").is_file()
    # 执行层日志从产出目录下的 .ai4sci 搬进了 executor/，跟产物一起留档
    assert list((out / "executor").iterdir())
    assert not (out / ".ai4sci").exists()


def test_prompt_carries_full_ledger_notebook_diff_and_results_per_experiment(made):
    run_dir, pack = made
    out, inputs = _out(pack)
    runner = _runner({"analysis.md": rf.good_analysis(run_dir)})
    analysis.run(out, inputs, Ports(runner=runner))
    prompt = runner.prompts[0]
    baseline = repr(rf.metrics_of(run_dir)["baseline"]["val_mse"])
    for token in ("## 实验 `experiment/1`", "第 1 轮", "第 2 轮", "第 3 轮", "within noise",
                  rf.REPORTS[1], "diff --git", "experiment/1/baseline：", "experiment/1/iter_3：",
                  baseline, "keep", "共跑 3 轮，留下 2 轮", "在固定预算下把 val_mse 压到最低"):
        assert token in prompt, token


def test_missing_section_fails_and_keeps_the_file(made):
    run_dir, pack = made
    out, inputs = _out(pack)
    broken = rf.good_analysis(run_dir).replace("## 数据", "## 数字")
    with pytest.raises(CapabilityFailed, match="缺少小节 ## 数据"):
        analysis.run(out, inputs, Ports(runner=_runner({"analysis.md": broken})))
    assert (out / "analysis.md").read_text(encoding="utf-8") == broken


def test_writing_outside_the_doc_fails(made):
    run_dir, pack = made
    out, inputs = _out(pack)

    def move(cwd: Path) -> None:
        (cwd / "analysis.md").write_text(rf.good_analysis(run_dir), encoding="utf-8")
        (cwd / "notes.md").write_text("执行层偷偷加了一个文件\n", encoding="utf-8")
    with pytest.raises(CapabilityFailed, match="notes.md"):
        analysis.run(out, inputs, Ports(runner=_runner(move)))


def test_dead_session_fails(made):
    run_dir, pack = made
    out, inputs = _out(pack)
    runner = ScriptedRunner([{"analysis.md": rf.good_analysis(run_dir)}], die_at=(1,))
    with pytest.raises(CapabilityFailed, match="没走完"):
        analysis.run(out, inputs, Ports(runner=runner))


def test_no_doc_written_fails(made):
    _, pack = made
    out, inputs = _out(pack)
    with pytest.raises(CapabilityFailed, match="没有写出 analysis.md"):
        analysis.run(out, inputs, Ports(runner=_runner(lambda cwd: None)))


def test_experiment_without_ledger_fails_and_inputs_are_required(tmp_path):
    fresh, pack = start_run(tmp_path)
    out, _ = outputs.open_output(pack.workspace, "analysis", title="t", by="analysis",
                                 inputs=[], params={}, flow=None, step=None, requirement=1,
                                 chat_id=None)
    with pytest.raises(CapabilityFailed, match="--from experiment/<n>"):
        analysis.run(out, Inputs(pack.workspace.root), Ports(runner=_runner({})))
    with pytest.raises(CapabilityFailed, match="没有可分析的账本"):
        analysis.run(out, Inputs(pack.workspace.root, (fresh,), ("experiment/1",)),
                     Ports(runner=_runner({})))


def test_runner_port_is_required(made):
    _, pack = made
    out, inputs = _out(pack)
    with pytest.raises(AssertionError, match="执行层端口"):
        analysis.run(out, inputs, Ports())
