"""便条（外层 #63 等待状态，P-18 按房间记）：快照那条流、按一颗记到那一间、流外的能力不动、
「在等谁」现算。"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from framework.contracts import workflows
from framework.run import flow_state, jobs

FLOW = """name: demo
title: 演示
summary: 跑 → 分析 → 人看 → 验证 → 人验收
rooms:
  - 实验: [auto-research]
  - 分析
  - 断点: 看一眼分析
  - 验证
  - 断点: 验收
"""


def _flow_file(tmp_path: Path) -> Path:
    path = tmp_path / "workflows" / "demo.yaml"
    path.parent.mkdir()
    path.write_text(FLOW, encoding="utf-8")
    return path


def _run_dir(tmp_path: Path) -> Path:
    run_dir = tmp_path / "runs" / "r1"
    run_dir.mkdir(parents=True)
    return run_dir


def test_attach_snapshots_the_file_and_stops_before_the_opening_room(tmp_path: Path):
    run_dir, path = _run_dir(tmp_path), _flow_file(tmp_path)
    state = flow_state.attach(run_dir, path, cap="auto-research", stage="实验")
    assert state["workflow"] == "demo" and state["step"] == 0  # 开 run 的能力在第 1 项：它之前是 0
    snapshot = run_dir / "workflow" / "demo.yaml"
    assert snapshot.read_text(encoding="utf-8") == FLOW
    path.write_text(FLOW.replace("看一眼分析", "改了"), encoding="utf-8")  # 仓里的流改了不影响 run
    assert workflows.load_workflow(snapshot).rooms[2].note == "看一眼分析"
    doc = flow_state.status(run_dir, tmp_path / "jobs")
    assert doc["step"] == 0 and doc["total"] == 5 and doc["waiting"] == "assistant"
    assert doc["next"] == {"kind": "room", "stage": "实验",
                           "caps": [{"cap": "auto-research", "with": {}}]}
    assert doc["rooms"][2] == {"kind": "stop", "key": None, "note": "看一眼分析"}
    # 流里开 run 的那一间不在开头：便条停在它前面，跑着的时候页面就知道当前是哪一间
    later = tmp_path / "workflows" / "later.yaml"
    text = FLOW.replace("name: demo", "name: later")
    text = text.replace("rooms:\n", "rooms:\n  - 假设\n  - 断点: 发布\n")
    later.write_text(text, encoding="utf-8")
    other = tmp_path / "runs" / "r2"
    other.mkdir()
    assert flow_state.attach(other, later, cap="auto-research", stage="实验")["step"] == 2
    assert flow_state.status(other, tmp_path / "jobs")["next"]["stage"] == "实验"
    assert flow_state.attach(other, later, cap="nope", stage="写作")["step"] == 0  # 流里没有它


def test_presses_land_on_rooms_by_name_or_by_stage_and_offpath_presses_do_not_move(tmp_path):
    run_dir = _run_dir(tmp_path)
    flow_state.attach(run_dir, _flow_file(tmp_path), cap="auto-research", stage="实验")
    assert flow_state.record_press(run_dir, "auto-research", "实验")["step"] == 1  # 点了名：按名字
    assert flow_state.record_press(run_dir, "auto-research", "实验")["step"] == 1  # 再跑：后面没它
    assert flow_state.record_press(run_dir, "verify", "验证")["step"] == 4  # 跳过分析：记到验证那间
    assert flow_state.record_press(run_dir, "analysis", "分析")["step"] == 4  # 回头补分析：不动
    doc = flow_state.status(run_dir, tmp_path / "jobs")
    assert doc["waiting"] == "key:accept" and doc["next"]["key"] == "accept"


def test_unnamed_room_matches_any_capability_of_that_stage(tmp_path):
    run_dir = _run_dir(tmp_path)
    flow_state.attach(run_dir, _flow_file(tmp_path), cap="auto-research", stage="实验")
    flow_state.record_press(run_dir, "auto-research", "实验")
    # 分析间没点名：这一间的任何能力都算走到了它；别的间的不算
    assert flow_state.record_press(run_dir, "some-plot", "分析")["step"] == 2
    assert flow_state.record_press(run_dir, "some-plot", "写作")["step"] == 2


def test_waiting_is_derived_from_jobs_and_the_next_item(tmp_path: Path):
    run_dir = _run_dir(tmp_path)
    flow_state.attach(run_dir, _flow_file(tmp_path), cap="auto-research", stage="实验")
    flow_state.record_press(run_dir, "auto-research", "实验")
    flow_state.record_press(run_dir, "analysis", "分析")
    assert flow_state.status(run_dir, tmp_path / "jobs")["waiting"] == "human"  # 下一项是断点
    jobs._save(tmp_path / "jobs", jobs.Job(job_id="job-1", cap="verify", level="run",
                                           target="r1", argv=[], pid=os.getpid(), started_at="t"))
    assert flow_state.status(run_dir, tmp_path / "jobs")["waiting"] == "job:job-1"
    jobs.finish(tmp_path / "jobs", "job-1", exit_code=0, result="ok")
    flow_state.record_press(run_dir, "verify", "验证")
    assert flow_state.status(run_dir, tmp_path / "jobs")["waiting"] == "key:accept"
    (run_dir / "flow.json").write_text('{"workflow": "demo", "step": 5}', encoding="utf-8")
    assert flow_state.status(run_dir, tmp_path / "jobs")["waiting"] == "done"


def test_no_flow_means_none_and_missing_snapshot_is_loud(tmp_path: Path):
    run_dir = _run_dir(tmp_path)
    assert flow_state.status(run_dir, tmp_path / "jobs") is None
    assert flow_state.record_press(run_dir, "auto-research", "实验") is None
    (run_dir / "flow.json").write_text('{"workflow": "gone", "step": 0}', encoding="utf-8")
    with pytest.raises(FileNotFoundError, match="快照却不在"):
        flow_state.status(run_dir, tmp_path / "jobs")
    bad = tmp_path / "workflows" / "bad.yaml"
    bad.parent.mkdir()
    bad.write_text("name: bad\n", encoding="utf-8")
    with pytest.raises(workflows.WorkflowInvalid):
        flow_state.attach(run_dir, bad, cap="auto-research", stage="实验")
    assert not (run_dir / "workflow").exists() or not any((run_dir / "workflow").iterdir())
