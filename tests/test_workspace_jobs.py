"""作业（外层 #63）：`--detach` 起独立进程、记录两次写、子进程回写、pid 探活判 lost、查询。"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

from framework.workspace import jobs
from framework.workspace import root as workspace
from tests.fixtures import runs_factory as rf

REPO_ROOT = Path(__file__).resolve().parent.parent


def _env(monkeypatch, ws: workspace.Workspace) -> None:
    """作业子进程靠环境认工作区（它的 cwd 是测试进程的），和 agent 调用的命令一样只认一个工作区。"""
    monkeypatch.setenv("PYTHONPATH", str(REPO_ROOT))
    monkeypatch.setenv(workspace.WORKSPACE_ENV, str(ws.root))


def _wait_done(jobs_dir: Path, job_id: str, timeout_s: float = 90.0) -> jobs.Job:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        job = jobs.load(jobs_dir, job_id)
        if job.status != "running":
            return job
        time.sleep(0.2)
    raise AssertionError(f"作业 {job_id} {timeout_s} 秒内没结束：{jobs.load(jobs_dir, job_id)}")


def test_spawned_job_runs_the_capability_and_writes_back(tmp_path: Path, monkeypatch):
    """起 `cap verify` 当作业：记录先是 running，子进程开了产出就回写 id，跑完回写 done 与结论行，
    日志落盘。"""
    run_dir, pack = rf.make_run(tmp_path)
    rf.write_analysis(pack, rf.good_analysis(run_dir))
    ws = pack.workspace
    _env(monkeypatch, ws)
    argv = ["cap", "verify", "--from", "analysis/1", "--from", "experiment/1"]
    job = jobs.spawn(ws.jobs, argv, cap="verify", stage="verification", chat_id="chat-x",
                     flow=None)
    assert job.status == "running" and job.job_id.startswith("job-") and job.chat_id == "chat-x"
    on_disk = json.loads((ws.jobs / f"{job.job_id}.json").read_text())
    assert on_disk["argv"] == argv and on_disk["pid"] == job.pid and on_disk["output"] is None
    done = _wait_done(ws.jobs, job.job_id)
    assert done.status == "done" and done.exit_code == 0, done
    assert done.result.startswith("verify PASS\t") and done.output == "verification/1"
    assert (ws.root / "verification" / "1" / "report.json").is_file()
    assert "verify_done" in Path(done.log).read_text(encoding="utf-8")  # 子进程的日志在文件里
    assert jobs.effective_status(done) == "done"
    assert jobs.jobs_for(ws.jobs, "verification/1")[0].job_id == job.job_id
    assert jobs.running_for(ws.jobs, "verification/1") is None
    assert jobs.running_jobs(ws.jobs) == []


def test_failed_job_writes_the_capabilitys_own_sentence(tmp_path: Path, monkeypatch):
    ws = workspace.create(tmp_path / "workspaces", "w1", template="# w1\n\n## 问题\n\n有。\n")
    _env(monkeypatch, ws)  # 需求没确认：门关着
    job = jobs.spawn(ws.jobs, ["cap", "verify", "--from", "analysis/1"], cap="verify",
                     stage="verification", chat_id=None)
    done = _wait_done(ws.jobs, job.job_id)
    assert done.status == "failed" and done.exit_code == 1 and "需求还没确认" in done.result
    assert jobs.running_flow(ws.jobs, "research") is None


def test_running_record_with_dead_pid_is_lost_not_done(tmp_path: Path):
    """没人回写就不猜：记录 running、进程不在 = lost。"""
    proc = subprocess.Popen([sys.executable, "-c", "pass"])
    proc.wait()
    job = jobs.Job(job_id="job-x", cap="auto-research", stage="experiment", argv=[],
                   pid=proc.pid, started_at="t", output="experiment/1")
    (tmp_path / "jobs").mkdir()
    (tmp_path / "jobs" / "job-x.json").write_text(json.dumps(job.__dict__), encoding="utf-8")
    assert jobs.effective_status(jobs.load(tmp_path / "jobs", "job-x")) == "lost"
    assert jobs.running_for(tmp_path / "jobs", "experiment/1") is None
    alive = jobs.Job(job_id="job-y", cap="auto-research", stage="experiment", argv=[],
                     pid=os.getpid(), started_at="t", output="experiment/1")
    assert jobs.effective_status(alive) == "running"
    with pytest.raises(jobs.JobNotFound):
        jobs.load(tmp_path / "jobs", "nope")
    assert jobs.list_jobs(tmp_path / "empty") == []
