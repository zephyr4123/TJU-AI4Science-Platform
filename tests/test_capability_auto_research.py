"""auto-research 这个能力的入口（外层 #96、#104）：第一次调用读设计那包开实验，
之后 --continue 接着跑；
续跑、加预算的参数只对已开过的实验有意义。内环本身的行为在 test_experiment_loop.py。"""

from __future__ import annotations

import pytest

from compute.local import LocalCompute
from framework import paths
from framework.capabilities import auto_research
from framework.contracts.capability import CapabilityFailed, Inputs, Ports
from framework.experiment.checkpoint import read_checkpoint
from framework.workspace import outputs
from tests.fixtures import packs_factory as pf
from tests.fixtures.scripted_backend import ScriptedRunner
from tests.test_experiment_loop import make_loop_pack, train_for_mse


def ports(*targets: float) -> Ports:
    return Ports(runner=ScriptedRunner([train_for_mse(t) for t in targets]),
                 compute=LocalCompute())


def new_out(pack: pf.Pack):
    out, _ = outputs.open_output(pack.workspace, "experiment", title="t", by="auto-research",
                                 inputs=[pack.output_id], params={}, flow=None, step=None,
                                 requirement=1, chat_id=None)
    return out, Inputs(pack.workspace.root, (pack.pack,), (pack.output_id,))


def test_opens_the_experiment_then_loops_and_points_at_analysis(tmp_path, monkeypatch):
    pack = make_loop_pack(tmp_path)
    monkeypatch.setattr(paths, "domains_root", lambda: pack.domains_root)
    out, inputs = new_out(pack)
    line = auto_research.run(out, inputs, ports(0.015), max_iters=1)
    assert line.startswith("stop batch_exhausted\titer=1\tbest=0.015\toutput=experiment/1")
    assert line.endswith("next=ai4sci cap analysis --from experiment/1")
    state = read_checkpoint(out)
    assert state["output"] == "experiment/1" and state["last_iter"] == 1
    assert state["chat_id"] is None
    # 接着跑：同一个产出目录，不另开
    line = auto_research.run(out, Inputs(pack.workspace.root), ports(0.001), max_iters=1)
    assert line.startswith("stop batch_exhausted\titer=2\tbest=0.000999")
    assert read_checkpoint(out)["last_iter"] == 2


def test_resume_and_extension_need_an_opened_experiment(tmp_path, monkeypatch):
    pack = make_loop_pack(tmp_path)
    monkeypatch.setattr(paths, "domains_root", lambda: pack.domains_root)
    out, inputs = new_out(pack)
    with pytest.raises(CapabilityFailed, match="只对已经开过的实验有意义"):
        auto_research.run(out, inputs, ports(), resume=True)
    with pytest.raises(CapabilityFailed, match="只对已经开过的实验有意义"):
        auto_research.run(out, inputs, ports(), patience=5, reason="再试")
    assert not (out / "work").exists()
    auto_research.run(out, inputs, ports(0.015), max_iters=1)
    with pytest.raises(CapabilityFailed, match="--reason 只在加预算时有意义"):
        auto_research.run(out, inputs, ports(), reason="没配预算")


def test_records_which_chat_opened_the_experiment(tmp_path, monkeypatch):
    pack = make_loop_pack(tmp_path)
    monkeypatch.setattr(paths, "domains_root", lambda: pack.domains_root)
    monkeypatch.setenv("AI4SCI_CHAT_ID", "chat-7")
    out, inputs = new_out(pack)
    auto_research.run(out, inputs, ports(0.015), max_iters=1)
    assert read_checkpoint(out)["chat_id"] == "chat-7"


def test_needs_exactly_one_design_output(tmp_path, monkeypatch):
    pack = make_loop_pack(tmp_path)
    monkeypatch.setattr(paths, "domains_root", lambda: pack.domains_root)
    out, _ = new_out(pack)
    with pytest.raises(CapabilityFailed, match="要且只要一个「design」"):
        auto_research.run(out, Inputs(pack.workspace.root), ports())
    assert not (out / "work").exists()


def test_broken_pack_is_refused_at_the_door(tmp_path, monkeypatch):
    pack = make_loop_pack(tmp_path)
    monkeypatch.setattr(paths, "domains_root", lambda: pack.domains_root)
    (pack.pack / "scoring.yaml").write_text("format_version: 1\n", encoding="utf-8")
    out, inputs = new_out(pack)
    with pytest.raises(CapabilityFailed, match="不合约"):
        auto_research.run(out, inputs, ports())
    assert not (out / "work").exists()


def test_design_drafting_logs_do_not_ride_into_the_work_tree(tmp_path, monkeypatch):
    """设计那包里执行层的草稿日志（executor/session-N）不是壳的一部分：Codex 演练里它被抄进了
    work/ 和每一轮的快照。"""
    pack = make_loop_pack(tmp_path)
    (pack.pack / "executor" / "session-1").mkdir(parents=True)
    (pack.pack / "executor" / "session-1" / "prompt.md").write_text("草稿", encoding="utf-8")
    monkeypatch.setattr(paths, "domains_root", lambda: pack.domains_root)
    out, inputs = new_out(pack)
    auto_research.run(out, inputs, ports(0.015), max_iters=1)
    assert not (out / "work" / "executor").exists()
    assert not (out / "iters" / "iter_1" / "executor").exists()
