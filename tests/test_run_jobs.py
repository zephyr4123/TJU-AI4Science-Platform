"""作业（外层 #63）：`--detach` 起独立进程、记录两次写、子进程回写、pid 探活判 lost、查询。"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

from framework.run import jobs

REPO_ROOT = Path(__file__).resolve().parent.parent


def _lock(root: Path) -> Path:
    lock = root / "freeze.txt"
    lock.write_text("numpy==2.0.0\n", encoding="utf-8")
    return lock


def _wait_done(runs_root: Path, job_id: str, timeout_s: float = 90.0) -> jobs.Job:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        job = jobs.load(runs_root, job_id)
        if job.status != "running":
            return job
        time.sleep(0.2)
    raise AssertionError(f"作业 {job_id} {timeout_s} 秒内没结束：{jobs.load(runs_root, job_id)}")


def test_spawned_job_runs_the_capability_and_writes_back(tmp_path: Path, monkeypatch):
    """起 `cap init` 当作业：记录先是 running，子进程跑完回写 done 与结论行，日志落盘。"""
    monkeypatch.setenv("PYTHONPATH", str(REPO_ROOT))
    monkeypatch.setenv("AI4SCI_RUNS_ROOT", str(tmp_path / "runs"))
    (tmp_path / "tasks").mkdir()
    argv = ["cap", "init", str(tmp_path / "tasks" / "t"), "--python", "3.12",
            "--lock", str(_lock(tmp_path))]
    job = jobs.spawn(tmp_path / "runs", argv, cap="init", level="task",
                     target=str(tmp_path / "tasks" / "t"), chat_id="chat-x")
    assert job.status == "running" and job.job_id.startswith("job-") and job.chat_id == "chat-x"
    on_disk = json.loads((tmp_path / "runs" / "jobs" / f"{job.job_id}.json").read_text())
    assert on_disk["argv"] == argv and on_disk["pid"] == job.pid
    done = _wait_done(tmp_path / "runs", job.job_id)
    assert done.status == "done" and done.exit_code == 0 and done.result.startswith("ok t\t")
    assert (tmp_path / "tasks" / "t" / "manifest.yaml").is_file()
    assert "init_done" in Path(done.log).read_text(encoding="utf-8")  # 子进程的日志在文件里
    assert jobs.effective_status(done) == "done" and jobs.running_for(tmp_path / "runs",
                                                                       done.target) is None


def test_failed_job_writes_the_capabilitys_own_sentence(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("PYTHONPATH", str(REPO_ROOT))
    monkeypatch.setenv("AI4SCI_RUNS_ROOT", str(tmp_path / "runs"))
    existing = tmp_path / "tasks" / "old"
    existing.mkdir(parents=True)
    job = jobs.spawn(tmp_path / "runs", ["cap", "init", str(existing), "--python", "3.12",
                                         "--lock", str(_lock(tmp_path))],
                     cap="init", level="task", target=str(existing), chat_id=None)
    done = _wait_done(tmp_path / "runs", job.job_id)
    assert done.status == "failed" and done.exit_code == 1 and "已存在" in done.result


def test_running_record_with_dead_pid_is_lost_not_done(tmp_path: Path):
    """没人回写就不猜：记录 running、进程不在 = lost。"""
    proc = subprocess.Popen([sys.executable, "-c", "pass"])
    proc.wait()
    job = jobs.Job(job_id="job-x", cap="experiment", level="run", target="r1", argv=[],
                   pid=proc.pid, started_at="t")
    (tmp_path / "jobs").mkdir()
    (tmp_path / "jobs" / "job-x.json").write_text(json.dumps(job.__dict__), encoding="utf-8")
    assert jobs.effective_status(jobs.load(tmp_path, "job-x")) == "lost"
    assert jobs.running_for(tmp_path, "r1") is None
    alive = jobs.Job(job_id="job-y", cap="experiment", level="run", target="r1", argv=[],
                     pid=os.getpid(), started_at="t")
    assert jobs.effective_status(alive) == "running"
    with pytest.raises(jobs.JobNotFound):
        jobs.load(tmp_path, "nope")
    assert jobs.list_jobs(tmp_path / "empty") == []
