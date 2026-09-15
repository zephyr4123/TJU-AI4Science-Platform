"""分析能力：零模型的部分（收集输入、组 prompt、判产物形状）用剧本执行层测全。

执行层写什么由剧本决定，所以能一条条摆出来：合约的、缺一节的、越界的、死掉的、
什么都没写的。数字对不对不在这里测——那是验证能力的事（P-2）。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from framework.capabilities import analysis
from framework.contracts.capability import CapabilityFailed, Ports
from framework.run import layout
from tests.fixtures import runs_factory as rf
from tests.fixtures.scripted_backend import ScriptedRunner
from tests.test_experiment_loop import start_run


@pytest.fixture(scope="module")
def run_dir(tmp_path_factory) -> Path:
    return rf.make_run(tmp_path_factory.mktemp("analysis"))


def _runner(*moves) -> ScriptedRunner:
    return ScriptedRunner(list(moves))


def test_analysis_writes_the_doc_and_reports_claims(run_dir):
    runner = _runner({"analysis/analysis.md": rf.good_analysis(run_dir)})
    line = analysis.run(run_dir, Ports(runner=runner))
    assert line.startswith("analysis ok\tclaims=4\tcost_usd=0.0100\tpath=analysis/analysis.md")
    assert layout.analysis_doc(run_dir).is_file()
    # 执行层日志从 run 目录下的 .ai4sci 搬进了能力目录，跟产物一起留档
    assert list((run_dir / "analysis" / "executor").iterdir())
    assert not (run_dir / ".ai4sci").exists()


def test_prompt_carries_full_ledger_notebook_diff_and_results(run_dir):
    runner = _runner({"analysis/analysis.md": rf.good_analysis(run_dir)})
    analysis.run(run_dir, Ports(runner=runner))
    prompt = runner.prompts[0]
    baseline = repr(rf.metrics_of(run_dir)["run_0"]["val_mse"])
    for token in ("第 1 轮", "第 2 轮", "第 3 轮", "within noise", rf.REPORTS[1],
                  "diff --git", "run_0：", "run_3：", baseline, "keep", "共跑 3 轮，留下 2 轮"):
        assert token in prompt, token


def test_rerun_rotates_the_previous_dir(run_dir):
    runner = _runner({"analysis/analysis.md": rf.good_analysis(run_dir)})
    analysis.run(run_dir, Ports(runner=runner))
    versions = sorted(p.name for p in run_dir.iterdir() if p.name.startswith("analysis_v"))
    assert versions and (run_dir / versions[-1] / "analysis.md").is_file()
    assert layout.analysis_doc(run_dir).is_file()


def test_missing_section_fails_and_keeps_the_file(run_dir):
    broken = rf.good_analysis(run_dir).replace("## 数据", "## 数字")
    with pytest.raises(CapabilityFailed, match="缺少小节 ## 数据"):
        analysis.run(run_dir, Ports(runner=_runner({"analysis/analysis.md": broken})))
    assert layout.analysis_doc(run_dir).read_text(encoding="utf-8") == broken


def test_writing_outside_analysis_dir_fails(run_dir):
    def move(cwd: Path) -> None:
        (cwd / "analysis").mkdir(exist_ok=True)
        (cwd / "analysis" / "analysis.md").write_text(rf.good_analysis(run_dir), encoding="utf-8")
        with (cwd / "experiment" / "notebook.md").open("a", encoding="utf-8") as fh:
            fh.write("\n执行层偷偷加了一行\n")
    with pytest.raises(CapabilityFailed, match="experiment/notebook.md"):
        analysis.run(run_dir, Ports(runner=_runner(move)))


def test_dead_session_fails(run_dir):
    runner = ScriptedRunner([{"analysis/analysis.md": rf.good_analysis(run_dir)}], die_at=(1,))
    with pytest.raises(CapabilityFailed, match="没走完"):
        analysis.run(run_dir, Ports(runner=runner))


def test_no_doc_written_fails(run_dir):
    with pytest.raises(CapabilityFailed, match="没有写出 analysis/analysis.md"):
        analysis.run(run_dir, Ports(runner=_runner(lambda cwd: None)))


def test_run_without_ledger_fails(tmp_path):
    fresh, _ = start_run(tmp_path)
    with pytest.raises(CapabilityFailed, match="没有可分析的账本"):
        analysis.run(fresh, Ports(runner=_runner({})))


def test_runner_port_is_required(run_dir):
    with pytest.raises(AssertionError, match="执行层端口"):
        analysis.run(run_dir, Ports())
