"""作业：把一条 `ai4sci cap ...` 起成独立进程，记录在工作区的 `jobs/<作业号>.json`（外层 #63）。

为什么在 run 层：作业是框架的磁盘状态，和 checkpoint 一样"在盘上、谁都能读"；它不认识能力，
也不认识对话——属于哪段对话只是记一个 id，跑完叫醒 agent 的活在 chat 层。
为什么是独立进程不是线程：调用命令的是协调 agent 的一轮对话，轮次一结束它的进程树就没了；
作业要活过那一刻，只能另起会话（`start_new_session`），stdout / stderr 落到自己的日志文件。

记录只写两次：起的时候（running）、结束的时候（done / failed，由子进程自己回写）。中途死了
（机器重启、`kill -9`）记录停在 running，`effective_status` 拿 pid 探一下不在了就报 lost——
不猜它跑完没有（P-7）。
"""

from __future__ import annotations

import json
import logging
import os
import secrets
import subprocess
import sys
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

LOGGER = logging.getLogger("ai4sci.jobs")
# 子进程凭它知道自己是哪个作业，跑完回写记录；起作业的进程看到它就拒绝再 --detach
JOB_ID_ENV = "AI4SCI_JOB_ID"
# 调用命令的那段对话：chat 层起 agent 时设，作业记下来，跑完好知道该叫醒谁
CHAT_ID_ENV = "AI4SCI_CHAT_ID"
STATUSES = ("running", "done", "failed")


class JobNotFound(FileNotFoundError):
    """没有这个作业号。"""


@dataclass
class Job:
    job_id: str
    cap: str
    level: str
    target: str
    argv: list[str]
    pid: int
    started_at: str
    status: str = "running"
    finished_at: str | None = None
    exit_code: int | None = None
    result: str = ""
    chat_id: str | None = None
    log: str = ""
    # 跑完叫醒那段对话的结果（chat 层写的一句话）；没有对话的作业是 None
    wake: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {**asdict(self), "effective_status": effective_status(self)}


def _path(jobs_dir: Path, job_id: str) -> Path:
    return Path(jobs_dir) / f"{job_id}.json"


def spawn(jobs_dir: Path, argv: list[str], *, cap: str, level: str, target: str,
          chat_id: str | None) -> Job:
    """起 `ai4sci <argv>` 当作业：新会话、日志落盘、记录写 running，立刻返回。

    `argv` 是去掉了 `--detach` 的那条命令；子进程从 `AI4SCI_JOB_ID` 知道自己是作业。
    起的是本解释器的 `framework.cli`，不是 PATH 上的 `ai4sci`：作业必须和命令跑在同一份代码里。
    """
    assert "--detach" not in argv, "作业的命令里不该还有 --detach"
    root = Path(jobs_dir)
    root.mkdir(parents=True, exist_ok=True)  # 日志文件先于记录落盘，记录由 _save 写
    stamp = datetime.now(UTC)
    job_id = f"job-{stamp:%Y%m%dT%H%M%SZ}-{secrets.token_hex(2)}"
    log_path = root / f"{job_id}.log"
    with log_path.open("w", encoding="utf-8") as log:
        proc = subprocess.Popen(
            [sys.executable, "-m", "framework.cli", *argv],
            stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT,
            start_new_session=True, env={**os.environ, JOB_ID_ENV: job_id},
        )
    job = Job(job_id=job_id, cap=cap, level=level, target=target, argv=list(argv), pid=proc.pid,
              started_at=stamp.isoformat(timespec="seconds"), chat_id=chat_id, log=str(log_path))
    _save(jobs_dir, job)
    LOGGER.info("job_spawn job_id=%s cap=%s target=%s pid=%d chat_id=%s",
                job_id, cap, target, proc.pid, chat_id or "-")
    return job


def finish(jobs_dir: Path, job_id: str, *, exit_code: int, result: str) -> Job:
    """子进程跑完回写：退出码 0 是 done，其余 failed；`result` 是那一行结论或那一句错误。"""
    job = load(jobs_dir, job_id)
    job.status = "done" if exit_code == 0 else "failed"
    job.exit_code = exit_code
    job.result = result.strip()
    job.finished_at = datetime.now(UTC).isoformat(timespec="seconds")
    _save(jobs_dir, job)
    LOGGER.info("job_finish job_id=%s status=%s exit_code=%d", job_id, job.status, exit_code)
    return job


def mark_wake(jobs_dir: Path, job_id: str, status: str) -> Job:
    """叫醒的结果记回作业：done / busy / failed / error 都留下，别让"没叫醒"无声消失。"""
    job = load(jobs_dir, job_id)
    job.wake = status
    _save(jobs_dir, job)
    return job


def load(jobs_dir: Path, job_id: str) -> Job:
    path = _path(jobs_dir, job_id)
    if not path.is_file():
        raise JobNotFound(f"没有这个作业：{job_id}（期望 {path}）")
    return Job(**json.loads(path.read_text(encoding="utf-8")))


def list_jobs(jobs_dir: Path) -> list[Job]:
    root = Path(jobs_dir)
    if not root.is_dir():
        return []
    return [Job(**json.loads(p.read_text(encoding="utf-8"))) for p in sorted(root.glob("*.json"))]


def jobs_for(jobs_dir: Path, target: str) -> list[Job]:
    """某个 run 或任务包的全部作业，按起的先后。"""
    return [job for job in list_jobs(jobs_dir) if job.target == target]


def running_for(jobs_dir: Path, target: str) -> Job | None:
    """正在跑的那个作业；没有就是 None。同一目标同时至多一个在跑（能力自己的 inflight 锁保证）。"""
    for job in reversed(jobs_for(jobs_dir, target)):
        if effective_status(job) == "running":
            return job
    return None


def effective_status(job: Job) -> str:
    """记录说 running 但进程不在了，就是 lost：没人回写过结束，不能当它跑完了。"""
    if job.status != "running":
        return job.status
    return "running" if _alive(job.pid) else "lost"


def _alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _save(jobs_dir: Path, job: Job) -> None:
    Path(jobs_dir).mkdir(parents=True, exist_ok=True)
    _path(jobs_dir, job.job_id).write_text(
        json.dumps(asdict(job), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
