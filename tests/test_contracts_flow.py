"""流通不通：对表的算术。真描述符那条线要通，缺桥、缺文件、重复、倒回任务包都要被抓出来。"""

from __future__ import annotations

from framework.capabilities import discover
from framework.contracts.capability import Artifact, Capability
from framework.contracts.flow import check_flow


def caps(*names: str) -> list[Capability]:
    found = discover()
    return [found[n].DESCRIPTOR for n in names]


def test_the_whole_line_is_connected():
    assert check_flow(caps("design", "baseline", "experiment", "analysis", "verify")) == []


def test_task_segment_alone_is_fine_and_run_segment_needs_the_bridge():
    assert check_flow(caps("design", "baseline")) == []
    problems = check_flow(caps("experiment"))
    assert len(problems) == 1 and "过桥" in problems[0] and "harness/" in problems[0]


def test_skipping_baseline_breaks_the_bridge_only_on_run0():
    problems = check_flow(caps("design", "experiment", "analysis", "verify"))
    assert problems == ["第 2 步 experiment 之前要过桥（run new），桥要 ['run_0/'] 前面没人产出"]


def test_each_missing_input_is_named_once():
    problems = check_flow(caps("design", "baseline", "verify"))
    assert [p for p in problems if "analysis/analysis.md" in p] == [
        "第 3 步 verify 要 analysis/analysis.md，前面没人产出"]
    assert any("experiment/ledger.tsv" in p for p in problems)


def test_duplicate_capability_in_one_run_is_rejected():
    problems = check_flow(caps("design", "baseline", "experiment", "analysis", "analysis"))
    assert problems == ["第 5 步 analysis 重复：同一个 run 里同一个能力只能出现一次"
                        "（产物路径固定，会互相覆盖）"]


def test_task_level_after_run_level_is_rejected():
    problems = check_flow(caps("design", "baseline", "experiment", "design"))
    assert problems == ["第 4 步 design 是 task 级能力，run 段之后不能回到任务包"]


def test_empty_flow_is_a_problem():
    assert check_flow([]) == ["流是空的：至少摆一个能力"]


def test_synthetic_capabilities_connect_by_path_not_by_name():
    a = Capability("a", "run", "s", (), (Artifact("o", "a/out.json", "d"),))
    b = Capability("b", "run", "s", (Artifact("i", "a/out.json", "d"),),
                   (Artifact("o", "b/", "d"),))
    bridge = [Capability("t", "task", "s", (), tuple(Artifact(p, p, "d") for p in
                                                    ("harness/", "code/", "run_0/")))]
    assert check_flow(bridge + [a, b]) == []
    assert check_flow(bridge + [b, a]) == ["第 2 步 b 要 a/out.json，前面没人产出"]
