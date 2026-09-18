"""开一次实验：能力 start 是 new_run 的薄壳——三道门在门口就停，成功时 run 目录与结论行对得上。"""

from __future__ import annotations

import pytest

from framework.capabilities import start
from framework.contracts.capability import CapabilityFailed, Ports
from framework.contracts.flow import check_flow
from framework.run.checkpoint import read_checkpoint
from tests.fixtures.packs_factory import make_pack


def test_start_builds_a_run_and_points_at_experiment(tmp_path, monkeypatch):
    pack = make_pack(tmp_path)
    monkeypatch.setenv("AI4SCI_DOMAINS_ROOT", str(pack.domains_root))
    line = start.run(pack.workspace, Ports(), run_id="r1")
    assert line.startswith("ok r1\t") and line.endswith("next=ai4sci cap experiment r1")
    state = read_checkpoint(pack.workspace.runs / "r1")
    assert state["run_id"] == "r1" and state["last_iter"] == 0
    with pytest.raises(CapabilityFailed, match="不覆盖"):
        start.run(pack.workspace, Ports(), run_id="r1")
    # --workflow 只认工作区里的实例：库里有也不行，得先取
    with pytest.raises(CapabilityFailed, match="flow take quick-look"):
        start.run(pack.workspace, Ports(), run_id="r2", workflow="quick-look")
    assert not (pack.workspace.runs / "r2").exists()


def test_start_refuses_unpublished_pack(tmp_path, monkeypatch):
    pack = make_pack(tmp_path, published=False)
    monkeypatch.setenv("AI4SCI_DOMAINS_ROOT", str(pack.domains_root))
    with pytest.raises(CapabilityFailed, match="还没发布"):
        start.run(pack.workspace, Ports(), run_id="r1")
    assert not (pack.workspace.runs / "r1").exists()


def test_start_is_the_bridge_in_a_flow():
    from framework.capabilities import analysis, baseline, design, experiment, verify

    steps = [m.DESCRIPTOR for m in (design, baseline, start, experiment, analysis, verify)]
    assert check_flow(steps) == []
    assert check_flow([design.DESCRIPTOR, start.DESCRIPTOR]) == [
        "第 2 步 start 之前要过桥（start），桥要 ['run_0/'] 前面没人产出"]
    assert check_flow([start.DESCRIPTOR, design.DESCRIPTOR]) == [
        "第 1 步 start 之前要过桥（start），桥要 ['harness/', 'code/', 'run_0/'] 前面没人产出",
        "第 2 步 design 是 task 级能力，run 段之后不能回到任务包"]
