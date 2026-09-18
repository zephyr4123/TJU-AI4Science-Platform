"""auto-research 这颗能力：run 不在就建（三道门在门口就停）、在就接着跑；照流的 run 跑成后记到
实验那个阶段。

内环本身的行为在 test_experiment_loop.py；这里只测命令层：开 run、参数的门、便条。"""

from __future__ import annotations

import pytest
import yaml

from compute.local import LocalCompute
from framework import paths
from framework.capabilities import auto_research
from framework.contracts.capability import CapabilityFailed, Ports
from framework.run import flow_state
from framework.run.checkpoint import read_checkpoint
from tests.fixtures.packs_factory import make_pack
from tests.fixtures.scripted_backend import ScriptedRunner
from tests.test_experiment_loop import make_loop_pack, train_for_mse


def ports(*rounds: float) -> Ports:
    return Ports(runner=ScriptedRunner([train_for_mse(v) for v in rounds]), compute=LocalCompute())


def test_opens_a_run_then_loops_and_points_at_analysis(tmp_path, monkeypatch):
    pack = make_loop_pack(tmp_path)
    monkeypatch.setenv("AI4SCI_DOMAINS_ROOT", str(pack.domains_root))
    line = auto_research.run(pack.workspace, ports(0.015), run_id="r1", max_iters=1)
    assert line.startswith("stop batch_exhausted\titer=1\t")
    assert line.endswith("\trun=r1\tnext=ai4sci cap analysis r1")
    state = read_checkpoint(pack.workspace.runs / "r1")
    assert state["run_id"] == "r1" and state["last_iter"] == 1 and state["chat_id"] is None
    # 第二次同名：不是拒绝，是接着跑（run 已经在了）
    line = auto_research.run(pack.workspace, ports(0.001), run_id="r1", max_iters=1)
    assert "iter=2" in line
    assert read_checkpoint(pack.workspace.runs / "r1")["last_iter"] == 2


def test_resume_and_extension_need_an_existing_run(tmp_path, monkeypatch):
    pack = make_loop_pack(tmp_path)
    monkeypatch.setenv("AI4SCI_DOMAINS_ROOT", str(pack.domains_root))
    with pytest.raises(CapabilityFailed, match="还没开过"):
        auto_research.run(pack.workspace, ports(), run_id="r9", resume=True)
    with pytest.raises(CapabilityFailed, match="还没开过"):
        auto_research.run(pack.workspace, ports(), run_id="r9", patience=5, reason="再试")
    assert not (pack.workspace.runs / "r9").exists()
    auto_research.run(pack.workspace, ports(0.015), run_id="r1", max_iters=1)
    with pytest.raises(CapabilityFailed, match="--reason 只在续命时有意义"):
        auto_research.run(pack.workspace, ports(), run_id="r1", reason="没配预算")
    with pytest.raises(CapabilityFailed, match="已经开过了"):
        auto_research.run(pack.workspace, ports(), run_id="r1", workflow="research")


def test_records_which_chat_opened_the_run(tmp_path, monkeypatch):
    pack = make_loop_pack(tmp_path)
    monkeypatch.setenv("AI4SCI_DOMAINS_ROOT", str(pack.domains_root))
    monkeypatch.setenv("AI4SCI_CHAT_ID", "chat-7")
    auto_research.run(pack.workspace, ports(0.015), run_id="r1", max_iters=1)
    assert read_checkpoint(pack.workspace.runs / "r1")["chat_id"] == "chat-7"


def test_refuses_unpublished_pack_at_the_door(tmp_path, monkeypatch):
    pack = make_pack(tmp_path, published=False)
    monkeypatch.setenv("AI4SCI_DOMAINS_ROOT", str(pack.domains_root))
    with pytest.raises(CapabilityFailed, match="还没发布"):
        auto_research.run(pack.workspace, ports(), run_id="r1")
    assert not (pack.workspace.runs / "r1").exists()


def test_workflow_must_be_an_instance_in_the_workspace(tmp_path, monkeypatch):
    pack = make_loop_pack(tmp_path)
    monkeypatch.setenv("AI4SCI_DOMAINS_ROOT", str(pack.domains_root))
    # 库里有也不行，得先 flow take
    with pytest.raises(CapabilityFailed, match="flow take research"):
        auto_research.run(pack.workspace, ports(), run_id="r2", workflow="research")
    assert not (pack.workspace.runs / "r2").exists()


def test_following_a_flow_records_the_experiment_room(tmp_path, monkeypatch):
    pack = make_loop_pack(tmp_path)
    monkeypatch.setenv("AI4SCI_DOMAINS_ROOT", str(pack.domains_root))
    pack.workspace.flows.mkdir(exist_ok=True)
    source = paths.workflows_root() / "research.yaml"
    (pack.workspace.flows / "research.yaml").write_text(source.read_text(encoding="utf-8"),
                                                        encoding="utf-8")
    auto_research.run(pack.workspace, ports(0.015), run_id="r1", workflow="research", max_iters=1)
    run_dir = pack.workspace.runs / "r1"
    note = flow_state.status(run_dir, pack.workspace.jobs)
    stages = yaml.safe_load(source.read_text(encoding="utf-8"))["stages"]
    # 实验是第 5 项（假设、◆发布、设计、◆核对、实验）：跑成后便条停在它上面，下一项是分析阶段
    assert note["step"] == 5 and stages[4] == {"实验": {"auto-research": {"max_iters": 3}}}
    assert note["next"] == {"kind": "stage", "stage": "分析", "caps": []}
    assert note["waiting"] == "assistant"
