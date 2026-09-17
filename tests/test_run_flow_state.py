"""便条（外层 #63 等待状态）：快照那条流、按一颗记一步、流外的按钮不动、「在等谁」现算。"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from framework.contracts import workflows
from framework.run import flow_state, jobs

FLOW = """name: demo
title: 演示
summary: 开 → 跑 → 分析 → 人看 → 验证 → 人验收
steps:
  - by: 助理
    does: 开一次实验
    cap: start
  - by: 助理
    does: 跑几轮
    cap: experiment
  - by: 助理
    does: 写分析
    cap: analysis
  - by: 人
    does: 看一眼分析
  - by: 助理
    does: 验证
    cap: verify
  - by: 人
    does: 验收
    key: accept
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


def test_attach_snapshots_the_file_and_counts_start_as_pressed(tmp_path: Path):
    run_dir, path = _run_dir(tmp_path), _flow_file(tmp_path)
    state = flow_state.attach(run_dir, path)
    assert state["workflow"] == "demo" and state["step"] == 1
    snapshot = run_dir / "workflow" / "demo.yaml"
    assert snapshot.read_text(encoding="utf-8") == FLOW
    path.write_text(FLOW.replace("跑几轮", "改了"), encoding="utf-8")  # 仓里的流改了不影响 run
    assert workflows.load_workflow(snapshot).steps[1].does == "跑几轮"
    doc = flow_state.status(run_dir, tmp_path / "runs")
    assert doc["step"] == 1 and doc["total"] == 6 and doc["waiting"] == "assistant"
    assert doc["next"]["cap"] == "experiment"


def test_presses_advance_along_the_flow_and_offpath_presses_do_not_move(tmp_path: Path):
    run_dir = _run_dir(tmp_path)
    flow_state.attach(run_dir, _flow_file(tmp_path))
    assert flow_state.record_press(run_dir, "experiment")["step"] == 2
    assert flow_state.record_press(run_dir, "experiment")["step"] == 2  # 再跑一批：流里后面没有它
    assert flow_state.record_press(run_dir, "verify")["step"] == 5  # 跳过分析直接验证：记到验证那步
    assert flow_state.record_press(run_dir, "analysis")["step"] == 5  # 回头补分析：流外，不动
    doc = flow_state.status(run_dir, tmp_path / "runs")
    assert doc["waiting"] == "key:accept" and doc["next"]["key"] == "accept"


def test_waiting_is_derived_from_jobs_and_the_next_step(tmp_path: Path):
    run_dir = _run_dir(tmp_path)
    flow_state.attach(run_dir, _flow_file(tmp_path))
    flow_state.record_press(run_dir, "experiment")
    flow_state.record_press(run_dir, "analysis")
    assert flow_state.status(run_dir, tmp_path / "runs")["waiting"] == "human"  # 下一步是人看
    jobs._save(tmp_path / "runs", jobs.Job(job_id="job-1", cap="verify", level="run",
                                           target="r1", argv=[], pid=os.getpid(), started_at="t"))
    assert flow_state.status(run_dir, tmp_path / "runs")["waiting"] == "job:job-1"
    jobs.finish(tmp_path / "runs", "job-1", exit_code=0, result="ok")
    flow_state.record_press(run_dir, "verify")
    assert flow_state.status(run_dir, tmp_path / "runs")["waiting"] == "key:accept"
    (run_dir / "flow.json").write_text('{"workflow": "demo", "step": 6}', encoding="utf-8")
    assert flow_state.status(run_dir, tmp_path / "runs")["waiting"] == "done"


def test_no_flow_means_none_and_missing_snapshot_is_loud(tmp_path: Path):
    run_dir = _run_dir(tmp_path)
    assert flow_state.status(run_dir, tmp_path / "runs") is None
    assert flow_state.record_press(run_dir, "experiment") is None
    (run_dir / "flow.json").write_text('{"workflow": "gone", "step": 0}', encoding="utf-8")
    with pytest.raises(FileNotFoundError, match="快照却不在"):
        flow_state.status(run_dir, tmp_path / "runs")
    bad = tmp_path / "workflows" / "bad.yaml"
    bad.parent.mkdir()
    bad.write_text("name: bad\n", encoding="utf-8")
    with pytest.raises(workflows.WorkflowInvalid):
        flow_state.attach(run_dir, bad)
    assert not (run_dir / "workflow").exists() or not any((run_dir / "workflow").iterdir())
