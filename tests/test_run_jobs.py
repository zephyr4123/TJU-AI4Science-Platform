"""作业（外层 #63）：`--detach` 起独立进程、记录两次写、子进程回写、pid 探活判 lost、查询。"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

from framework.run import jobs, workspace

REPO_ROOT = Path(__file__).resolve().parent.parent


def _lock(root: Path) -> Path:
    lock = root / "freeze.txt"
    lock.write_text("numpy==2.0.0\n", encoding="utf-8")
    return lock


def _ws(tmp_path: Path, monkeypatch) -> workspace.Workspace:
    """作业子进程靠环境认工作区（它的 cwd 是测试进程的），和 agent 调用的命令一样只认一个工作区。"""
    ws = workspace.create(tmp_path / "workspaces", "w1")
    monkeypatch.setenv("PYTHONPATH", str(REPO_ROOT))
    monkeypatch.setenv(workspace.WORKSPACE_ENV, str(ws.root))
    return ws


def _wait_done(jobs_dir: Path, job_id: str, timeout_s: float = 90.0) -> jobs.Job:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        job = jobs.load(jobs_dir, job_id)
        if job.status != "running":
            return job
        time.sleep(0.2)
    raise AssertionError(f"作业 {job_id} {timeout_s} 秒内没结束：{jobs.load(jobs_dir, job_id)}")


def test_spawned_job_runs_the_capability_and_writes_back(tmp_path: Path, monkeypatch):
    """起 `cap init` 当作业：记录先是 running，子进程跑完回写 done 与结论行，日志落盘。"""
    ws = _ws(tmp_path, monkeypatch)
    argv = ["cap", "init", "--python", "3.12", "--lock", str(_lock(tmp_path))]
    job = jobs.spawn(ws.jobs, argv, cap="init", level="task", target=ws.id, chat_id="chat-x")
    assert job.status == "running" and job.job_id.startswith("job-") and job.chat_id == "chat-x"
    on_disk = json.loads((ws.jobs / f"{job.job_id}.json").read_text())
    assert on_disk["argv"] == argv and on_disk["pid"] == job.pid
    done = _wait_done(ws.jobs, job.job_id)
    assert done.status == "done" and done.exit_code == 0 and done.result.startswith("ok w1\t")
    assert (ws.task / "manifest.yaml").is_file()
    assert "init_done" in Path(done.log).read_text(encoding="utf-8")  # 子进程的日志在文件里
    assert jobs.effective_status(done) == "done"
    assert jobs.running_for(ws.jobs, done.target) is None


def test_failed_job_writes_the_capabilitys_own_sentence(tmp_path: Path, monkeypatch):
    ws = _ws(tmp_path, monkeypatch)
    ws.task.mkdir()  # 任务包已经在了：init 拒绝
    job = jobs.spawn(ws.jobs, ["cap", "init", "--python", "3.12", "--lock", str(_lock(tmp_path))],
                     cap="init", level="task", target=ws.id, chat_id=None)
    done = _wait_done(ws.jobs, job.job_id)
    assert done.status == "failed" and done.exit_code == 1 and "已经有任务包" in done.result


def test_running_record_with_dead_pid_is_lost_not_done(tmp_path: Path):
    """没人回写就不猜：记录 running、进程不在 = lost。"""
    proc = subprocess.Popen([sys.executable, "-c", "pass"])
    proc.wait()
    job = jobs.Job(job_id="job-x", cap="experiment", level="run", target="r1", argv=[],
                   pid=proc.pid, started_at="t")
    (tmp_path / "jobs").mkdir()
    (tmp_path / "jobs" / "job-x.json").write_text(json.dumps(job.__dict__), encoding="utf-8")
    assert jobs.effective_status(jobs.load(tmp_path / "jobs", "job-x")) == "lost"
    assert jobs.running_for(tmp_path / "jobs", "r1") is None
    alive = jobs.Job(job_id="job-y", cap="experiment", level="run", target="r1", argv=[],
                     pid=os.getpid(), started_at="t")
    assert jobs.effective_status(alive) == "running"
    with pytest.raises(jobs.JobNotFound):
        jobs.load(tmp_path / "jobs", "nope")
    assert jobs.list_jobs(tmp_path / "empty") == []
