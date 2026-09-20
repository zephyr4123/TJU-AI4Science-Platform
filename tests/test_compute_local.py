"""本地算力后端的测试：全部在 tmp_path 里造，不依赖仓里的 tasks/（P-5）。

重点验三件事：超时真的把整组杀干净、句柄落盘再读回后"不知道退出码"不会被讲成成功、
名字对不上时报错列出可用名字。
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

import pytest

from compute import ComputeNotFound, ExitStatus, Job, available_computes, get_compute
from compute.local import LocalCompute
from compute.procs import group_alive


def _wait_group_gone(pgid: int, limit_s: float = 5.0) -> bool:
    deadline = time.monotonic() + limit_s
    while time.monotonic() < deadline:
        if not group_alive(pgid):
            return True
        time.sleep(0.02)
    return False


def test_get_compute_local_and_unknown_name_lists_available():
    assert available_computes() == ["local", "ssh"]
    assert hasattr(get_compute("local"), "submit")
    with pytest.raises(ComputeNotFound) as exc:
        get_compute("slurm")
    assert "local" in str(exc.value)


def test_put_copies_tree_and_ignores_git(tmp_path):
    src, dst = tmp_path / "work", tmp_path / "run_1"
    (src / "code").mkdir(parents=True)
    (src / "code" / "train.py").write_text("print(1)\n", encoding="utf-8")
    (src / ".git").mkdir()
    (src / ".git" / "HEAD").write_text("ref: refs/heads/main\n", encoding="utf-8")
    LocalCompute().put(src, dst)
    assert (dst / "code" / "train.py").read_text(encoding="utf-8") == "print(1)\n"
    assert not (dst / ".git").exists()


def test_put_refuses_to_overwrite_an_existing_snapshot(tmp_path):
    """快照目录已经在那儿，只能是被杀的一轮留下的：报清楚让人去 resume，不要往里叠。"""
    src, dst = tmp_path / "work", tmp_path / "run_1"
    (src / "code").mkdir(parents=True)
    (src / "code" / "train.py").write_text("print(1)\n", encoding="utf-8")
    dst.mkdir()
    with pytest.raises(FileExistsError) as exc:
        LocalCompute().put(src, dst)
    assert str(dst) in str(exc.value) and "resume" in str(exc.value)


def test_submit_wait_success_writes_logs_and_env(tmp_path):
    compute = LocalCompute()
    job = compute.submit(
        tmp_path, ["python3", "-c", "import os,sys; print(os.environ['AI4SCI_SEED']); sys.exit(0)"],
        {"AI4SCI_SEED": "42"}, timeout_s=30,
    )
    status = compute.wait(job)
    assert status.exit_code == 0 and status.timed_out is False and status.ok
    assert Path(status.stdout_path).read_text(encoding="utf-8").strip() == "42"
    assert Path(job.stderr_path).is_file()
    assert status.elapsed_s >= 0


def test_submit_nonzero_exit_is_reported_not_swallowed(tmp_path):
    compute = LocalCompute()
    job = compute.submit(tmp_path, ["python3", "-c", "raise SystemExit(3)"], {}, timeout_s=30)
    assert compute.wait(job).exit_code == 3


def test_wait_timeout_cancels_whole_process_group(tmp_path):
    """起一个 sleep 60 的任务，wait(timeout_s=1) 后 timed_out=True 且进程组无存活。"""
    compute = LocalCompute()
    job = compute.submit(
        tmp_path, ["bash", "-c", "python3 -c 'import time; time.sleep(60)'"], {}, timeout_s=600
    )
    started = time.monotonic()
    status = compute.wait(job, timeout_s=1)
    assert status.timed_out is True
    assert status.exit_code != 0  # 被 SIGKILL：负信号码，绝不是 0
    assert time.monotonic() - started < 20
    assert _wait_group_gone(job.pgid), "超时后进程组仍有存活进程"


def test_job_json_roundtrip_then_wait_reports_unknown_exit_code(tmp_path):
    """续跑读回的 job：进程已经不在，退出码必须是"未知"（None），不许拿 0 蒙混。"""
    compute = LocalCompute()
    job = compute.submit(tmp_path, ["python3", "-c", "raise SystemExit(0)"], {}, timeout_s=30)
    (tmp_path / "job.json").write_text(job.to_json(), encoding="utf-8")
    assert compute.wait(job).exit_code == 0  # 亲爹这轮拿得到

    reloaded = Job.from_json((tmp_path / "job.json").read_text(encoding="utf-8"))
    assert reloaded == job
    fresh = LocalCompute()  # 新进程模拟：手里没有 Popen
    status = fresh.wait(reloaded, timeout_s=1)
    assert status.exit_code is None, "已死但退出码不可知时必须是 None"
    assert status.timed_out is False
    assert status.ok is False, "未知不等于成功"


def test_job_json_missing_field_raises(tmp_path):
    with pytest.raises(TypeError):
        Job.from_json(json.dumps({"pid": 1}))


def test_get_same_dir_is_noop(tmp_path):
    (tmp_path / "results.json").write_text("{}", encoding="utf-8")
    LocalCompute().get(tmp_path, tmp_path)
    assert (tmp_path / "results.json").is_file()


def test_get_copies_artifacts_back(tmp_path):
    remote, local = tmp_path / "run_1", tmp_path / "work"
    remote.mkdir()
    local.mkdir()
    (remote / "results.json").write_text('{"metrics": {}}', encoding="utf-8")
    LocalCompute().get(remote, local)
    assert (local / "results.json").is_file()


def test_exit_status_unknown_is_not_ok():
    status = ExitStatus(
        exit_code=None, timed_out=False, elapsed_s=1.0, stdout_path="", stderr_path=""
    )
    assert status.ok is False


def test_cancel_is_idempotent_on_dead_job(tmp_path):
    compute = LocalCompute()
    job = compute.submit(tmp_path, ["python3", "-c", "pass"], {}, timeout_s=30)
    compute.wait(job)
    compute.cancel(job)  # 已经死了再杀一次不许抛
    assert os.getpgid(0) != job.pgid
