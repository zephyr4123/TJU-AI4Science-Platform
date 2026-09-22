"""删：产出只删叶子（兄弟读过的也算）、流程实例没挂产出才删、工作区与项目级联（主人 2026-09-22：
人产生的都能删，从根删干净，没有软删除）。目录外那部分（会话、镜像）这一层只收回调，回调返回的
「没清干净」原样进 Removed。"""

from __future__ import annotations

import os

import pytest

from framework.contracts import output
from framework.workspace import jobs, outputs, removal
from framework.workspace import project as project_mod
from tests.fixtures import spaces


def _ws(tmp_path):
    return spaces.make_workspace(tmp_path, "w")


def _open(ws, slug, inputs=(), **kw):
    fields = {"title": "t", "by": "assistant", "inputs": list(inputs), "params": {},
              "flow": None, "step": None, "requirement": 1, "chat_id": None, **kw}
    d, m = outputs.open_output(ws, slug, **fields)
    outputs.close_output(d, m, ok=True, line="ok")
    return d, m


def _job(ws, job_id, *, output_id=None, flow=None, status="running", pid=None):
    job = jobs.Job(job_id=job_id, cap="design", stage="design", argv=[], pid=pid or os.getpid(),
                   started_at="t", status=status, result="design ok", flow=flow, output=output_id)
    jobs._save(ws.jobs, job)
    return job


def test_only_leaf_outputs_can_be_removed_and_jobs_get_a_note(tmp_path):
    ws = _ws(tmp_path)
    d1, _ = _open(ws, "design")
    d2, _ = _open(ws, "experiment", inputs=["design/1"])
    _job(ws, "job-1", output_id="experiment/1", status="done")
    # design/1 被 experiment/1 读过：拒，说清先删谁
    with pytest.raises(removal.RemovalRefused, match="被 experiment/1 读过"):
        removal.remove_output(ws, "design/1")
    assert removal.referencing(ws, "design/1") == ["experiment/1"]
    # 正在跑的叶子也拒
    _job(ws, "job-2", output_id="experiment/1")
    with pytest.raises(removal.RemovalRefused, match="正有作业在跑"):
        removal.remove_output(ws, "experiment/1")
    jobs.finish(ws.jobs, "job-2", exit_code=0, result="done")
    # 从末端往回删：叶子删了，目录没了，作业记录留着、结论行补一句
    removed = removal.remove_output(ws, "experiment/1")
    assert removed.what == "experiment/1" and removed.clean and not d2.exists()
    assert all("产出已删" in job.result for job in jobs.jobs_for(ws.jobs, "experiment/1"))
    assert removal.remove_output(ws, "design/1").clean and not d1.exists()
    with pytest.raises(output.OutputNotFound):
        removal.remove_output(ws, "design/1")
    # 编号：作业记录里出现过的号不复用（experiment/1 有作业），没作业记录的删了号就空出来
    _, m = _open(ws, "experiment", inputs=[])
    assert m.id == "experiment/2"
    # 签过的叶子能删：签字是人的决定，删也是
    d3, m3 = _open(ws, "design")
    output.sign(d3, by="zephyr")
    assert removal.remove_output(ws, m3.id).clean and not d3.exists()


def test_flow_instance_is_removed_only_when_nothing_hangs_on_it(tmp_path):
    ws = _ws(tmp_path)
    (ws.flows / "research.yaml").write_text("name: research\n", encoding="utf-8")
    with pytest.raises(FileNotFoundError, match="没有叫 'nope'"):
        removal.remove_flow(ws, "nope")
    _open(ws, "design", flow="research", step=0)
    with pytest.raises(removal.RemovalRefused, match="挂着 design/1"):
        removal.remove_flow(ws, "research")
    removal.remove_output(ws, "design/1")
    _job(ws, "job-1", flow="research")
    with pytest.raises(removal.RemovalRefused, match="正有作业照流程 research"):
        removal.remove_flow(ws, "research")
    jobs.finish(ws.jobs, "job-1", exit_code=1, result="x")
    assert removal.remove_flow(ws, "research").what == "research"
    assert not (ws.flows / "research.yaml").exists()


def test_workspace_removal_cascades_through_callbacks_and_refuses_while_running(tmp_path):
    ws = _ws(tmp_path)
    _open(ws, "design", compute={"name": "autodl", "kind": "ssh"})
    _open(ws, "design", compute={"name": "autodl", "kind": "ssh"})
    _open(ws, "design", compute={"name": "local", "kind": "local"})
    _job(ws, "job-1")
    with pytest.raises(removal.RemovalRefused, match="有作业在跑（job-1）"):
        removal.remove_workspace(ws, remove_mirrors=lambda *_: [])
    jobs.finish(ws.jobs, "job-1", exit_code=0, result="ok")
    seen: dict = {}

    def mirrors(workspace, metas):
        seen["mirrors"] = removal.mirrors_of(metas)
        return ["gone 上的镜像没删：连不上"]

    removed = removal.remove_workspace(ws, remove_mirrors=mirrors)
    # ssh 机器按名字去重，本机不算镜像；没清干净的原样带回；目录没了
    assert seen == {"mirrors": ["autodl"]} and removed.what == "w"
    assert removed.leftovers == ["gone 上的镜像没删：连不上"]
    assert not removed.clean and not ws.root.exists()


def test_sibling_references_freeze_removal_across_workspaces(tmp_path):
    """兄弟工作区 `from` 过的产出不能删，它所在的工作区也不能删；先删下游。"""
    ws = _ws(tmp_path)
    paper = spaces.make_workspace(tmp_path, "paper")
    _open(ws, "analysis")
    _open(paper, "writing", inputs=["w:analysis/1"])
    assert removal.referencing(ws, "analysis/1") == ["paper:writing/1"]
    with pytest.raises(removal.RemovalRefused, match="被 paper:writing/1 读过"):
        removal.remove_output(ws, "analysis/1")
    with pytest.raises(removal.RemovalRefused,
                       match="兄弟工作区读过它的产出（paper:writing/1 读了"):
        removal.remove_workspace(ws, remove_mirrors=lambda *_: [])
    # 从末端往回删：删了 paper 里的叶子，w 就能删了
    assert removal.remove_output(paper, "writing/1").clean
    assert removal.remove_workspace(ws, remove_mirrors=lambda *_: []).clean


def test_project_removal_cascades_and_refuses_while_any_workspace_runs(tmp_path):
    ws = _ws(tmp_path)
    other = spaces.make_workspace(tmp_path, "other")
    _open(other, "design", compute={"name": "autodl", "kind": "ssh"})
    _job(ws, "job-1")
    project = project_mod.of(ws)
    with pytest.raises(removal.RemovalRefused, match="工作区 w 有作业在跑（job-1）"):
        removal.remove_project(project, forget_chats=lambda _: [], remove_mirrors=lambda *_: [])
    jobs.finish(ws.jobs, "job-1", exit_code=0, result="ok")
    seen: dict = {"mirrors": []}

    def forget(found):
        seen["chats"] = found.id
        return ["对话 chat-1 在 codex 那边的会话没清：没登录"]

    def mirrors(workspace, metas):
        seen["mirrors"].append((workspace.id, removal.mirrors_of(metas)))
        return []

    removed = removal.remove_project(project, forget_chats=forget, remove_mirrors=mirrors)
    assert seen == {"chats": "p", "mirrors": [("other", ["autodl"]), ("w", [])]}
    assert removed.what == "p"
    assert removed.leftovers == ["对话 chat-1 在 codex 那边的会话没清：没登录"]
    assert not project.root.exists()
