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
from tests.fixtures import spaces

REPO_ROOT = Path(__file__).resolve().parent.parent


def _env(monkeypatch, ws: workspace.Workspace) -> None:
    """作业子进程靠环境认工作区（它的 cwd 是测试进程的），和 agent 调用的命令一样只认一个工作区。"""
    monkeypatch.setenv("PYTHONPATH", str(REPO_ROOT))
    monkeypatch.chdir(ws.root)


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
    ws = spaces.make_workspace(tmp_path, "w1", template="# w1\n\n## 问题\n\n有。\n")
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


def test_stop_kills_the_whole_tree_and_closes_the_output(tmp_path: Path):
    """外层 #115：人叫停——作业自成会话，它下面再开的进程组也要一起死；记录 stopped、产出 failed。
    已经不在跑的（停过的、lost 的）不许再停：对着尸体说「停了」是假话。"""
    from framework.contracts import output
    from framework.workspace import outputs

    ws = spaces.make_workspace(tmp_path, "w1", template="# w1\n\n## 问题\n\n有。\n")
    directory, _ = outputs.open_output(ws, "design", title="t", by="design", inputs=[], params={},
                                       flow=None, step=None, requirement=1, chat_id=None)
    # 顶上一个 python 自成会话，再起一个自成进程组的孙子（像执行层的 Bash、harness 的 launcher）
    proc = subprocess.Popen(
        [sys.executable, "-c",
         "import subprocess,sys,time; subprocess.Popen([sys.executable,'-c','import time; "
         "time.sleep(300)'], start_new_session=True); time.sleep(300)"],
        start_new_session=True)
    time.sleep(1.0)
    grandchild = subprocess.run(["pgrep", "-P", str(proc.pid)], capture_output=True, text=True)
    assert grandchild.stdout.split(), "夹具该有一个孙进程"
    record = jobs.Job(job_id="job-s", cap="design", stage="design", argv=[], pid=proc.pid,
                      started_at="t", output="design/1")
    ws.jobs.mkdir(parents=True)
    (ws.jobs / "job-s.json").write_text(json.dumps(record.__dict__), encoding="utf-8")

    stopped = jobs.stop(ws, "job-s", by="zephyr")
    proc.wait(timeout=5)
    assert stopped.status == "stopped" and stopped.exit_code is None and "zephyr" in stopped.result
    assert jobs.effective_status(jobs.load(ws.jobs, "job-s")) == "stopped"
    for pid in grandchild.stdout.split():  # 孙进程也死了，不留孤儿烧 CPU
        assert subprocess.run(["ps", "-p", pid, "-o", "stat="], capture_output=True,
                              text=True).stdout.strip() in ("", "Z")
    meta = output.read_meta(directory)
    assert meta.status == "failed" and "人停的" in meta.error
    with pytest.raises(jobs.JobNotRunning, match="stopped"):
        jobs.stop(ws, "job-s", by="zephyr")
    dead = subprocess.Popen([sys.executable, "-c", "pass"])
    dead.wait()
    (ws.jobs / "job-l.json").write_text(json.dumps({**record.__dict__, "job_id": "job-l",
                                                    "pid": dead.pid}), encoding="utf-8")
    with pytest.raises(jobs.JobNotRunning, match="lost"):
        jobs.stop(ws, "job-l", by="zephyr")


def test_stop_also_cancels_whatever_runs_under_the_output_on_its_compute(tmp_path, monkeypatch):
    """外层 #118：产出在别的机器上跑（meta 记着 compute），本机杀了树远端的 uv pip sync 还在装——
    停作业要连那台机器上这次产出目录下的一并杀；远端没杀成不吞，记录照写 stopped 再抛。"""
    from compute import ComputeError
    from framework import computes
    from framework.contracts import output
    from framework.workspace import outputs

    ws = spaces.make_workspace(tmp_path, "w1", template="# w1\n\n## 问题\n\n有。\n")
    label = {"name": "box", "kind": "ssh", "hostname": "h", "gpu": ""}
    directory, _ = outputs.open_output(ws, "design", title="t", by="design", inputs=[], params={},
                                       flow=None, step=None, requirement=1, chat_id=None,
                                       compute=label)
    calls: list[str] = []

    class Box:
        def remote_dir_for(self, local_dir):
            return f"/box{Path(local_dir).resolve()}"

        def cancel_under(self, remote_dir):
            calls.append(remote_dir)
            if remote_dir.endswith("/1") and len(calls) > 1:
                raise ComputeError("ssh 起不来")
            return [7]

    monkeypatch.setattr(computes, "instance", lambda name: Box() if name == "box" else None)

    def running_job(job_id: str) -> None:
        proc = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(300)"],
                                start_new_session=True)
        record = jobs.Job(job_id=job_id, cap="design", stage="design", argv=[], pid=proc.pid,
                          started_at="t", output="design/1")
        ws.jobs.mkdir(parents=True, exist_ok=True)
        (ws.jobs / f"{job_id}.json").write_text(json.dumps(record.__dict__), encoding="utf-8")

    running_job("job-a")
    stopped = jobs.stop(ws, "job-a", by="zephyr")
    assert stopped.status == "stopped" and calls == [f"/box{directory.resolve()}"]
    assert output.read_meta(directory).status == "failed"
    # 远端够不着：本机照样停了、记录说清远端没停，错抛给叫停的人
    running_job("job-b")
    with pytest.raises(ComputeError, match="ssh 起不来"):
        jobs.stop(ws, "job-b", by="zephyr")
    again = jobs.load(ws.jobs, "job-b")
    assert again.status == "stopped" and "box 上的没停下来" in again.result
