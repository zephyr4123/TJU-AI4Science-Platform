"""作业：把一条 `ai4sci cap ...` 起成独立进程，记录在工作区的 `.ai4sci/jobs/<作业号>.json`
（外层 #63）。

为什么在工作区层：作业是框架的磁盘状态，"在盘上、谁都能读"；它不认识能力，
也不认识对话——属于哪段对话只是记一个 id，跑完叫醒 agent 的活在 chat 层。
为什么是独立进程不是线程：调用命令的是协调 agent 的一轮对话，轮次一结束它的进程树就没了；
作业要活过那一刻（还有服务退出、外壳退出），只能另起一棵谁都不是它祖先的进程树
（`procs.spawn_detached`，外层 #284）。三个标准流一个都不接：Windows 上作业以 explorer 为父进程起，
句柄传不过去，所以 stdout / stderr 由作业自己按路径接到日志文件（`own_log`，两边同一个办法）。

记录只写两次：起的时候（running）、结束的时候（done / failed，由子进程自己回写）。中途死了
（机器重启、`kill -9`）记录停在 running，`effective_status` 拿 pid 探一下不在了就报 lost——
不猜它跑完没有（P-7）。人叫停（`ai4sci job stop`，外层 #115）是第三种结束：框架杀整棵进程树，
记录写 stopped 与谁停的，作业开的那次产出记 failed 与原因。
"""

from __future__ import annotations

import json
import logging
import os
import secrets
import sys
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import procs
from compute import ComputeError
from framework import computes
from framework.files import read_text, write_atomic
from framework.workspace import outputs
from framework.workspace.root import Workspace

LOGGER = logging.getLogger("ai4sci.jobs")
# 子进程凭它知道自己是哪个作业，跑完回写记录；起作业的进程看到它就拒绝再 --detach
JOB_ID_ENV = "AI4SCI_JOB_ID"
# 调用命令的那段对话：chat 层起 agent 时设，作业记下来，跑完好知道该叫醒谁
CHAT_ID_ENV = "AI4SCI_CHAT_ID"
# 作业的日志在哪：起作业时设，作业进程第一件事按它接好 stdout / stderr（`own_log`）就从环境里去掉
LOG_ENV = "AI4SCI_JOB_LOG"
STATUSES = ("running", "done", "failed", "stopped")


class JobNotFound(FileNotFoundError):
    """没有这个作业号。"""


class JobNotRunning(ValueError):
    """要停的作业已经不在跑了（done / failed / stopped / lost），没什么可停的。"""


@dataclass
class Job:
    job_id: str
    cap: str
    stage: str
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
    # 产出记在哪条流程下（开了产出与 output 一起回写；--flow 省了也一样）；没照流程是 None。
    # 页面靠它把跑着的作业画到那条流程上
    flow: str | None = None
    # 这个作业产的那次产出（子进程开了目录再回写）；接着干的作业开工时就知道
    output: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {**asdict(self), "effective_status": effective_status(self)}


def _path(jobs_dir: Path, job_id: str) -> Path:
    return Path(jobs_dir) / f"{job_id}.json"


def spawn(jobs_dir: Path, argv: list[str], *, cap: str, stage: str, chat_id: str | None,
          output: str | None = None) -> Job:
    """起 `ai4sci <argv>` 当作业：谁都不是它的祖先、日志落盘、记录写 running，立刻返回。

    `argv` 是去掉了 `--detach` 的那条命令；子进程从 `AI4SCI_JOB_ID` 知道自己是作业、从
    `AI4SCI_JOB_LOG` 知道日志在哪。起的是本解释器的 `framework.cli`，不是 PATH 上的 `ai4sci`：作业
    必须和命令跑在同一份代码里。没能脱离起它的进程（Windows 上没有 explorer）的那句话写在日志
    第一行。
    """
    assert "--detach" not in argv, "作业的命令里不该还有 --detach"
    root = Path(jobs_dir)
    root.mkdir(parents=True, exist_ok=True)  # 日志文件先于记录落盘，记录由 _save 写
    stamp = datetime.now(UTC)
    job_id = f"job-{stamp:%Y%m%dT%H%M%SZ}-{secrets.token_hex(2)}"
    log_path = root / f"{job_id}.log"
    log_path.write_text("", encoding="utf-8")
    started = procs.spawn_detached([sys.executable, "-m", "framework.cli", *argv],
                                   env={**os.environ, JOB_ID_ENV: job_id, LOG_ENV: str(log_path)})
    if started.warning:
        with log_path.open("a", encoding="utf-8") as log:
            log.write(f"WARNING {started.warning}\n")
        # info 不是 warning：--detach 那条命令还没配日志，WARNING 会原样打到助理的 stderr 最前面
        LOGGER.info("job_not_detached job_id=%s why=%s", job_id, started.warning)
    job = Job(job_id=job_id, cap=cap, stage=stage, argv=list(argv), pid=started.pid,
              started_at=stamp.isoformat(timespec="seconds"), chat_id=chat_id, log=str(log_path),
              output=output)
    _save(jobs_dir, job)
    LOGGER.info("job_spawn job_id=%s cap=%s pid=%d chat_id=%s",
                job_id, cap, started.pid, chat_id or "-")
    return job


def own_log() -> None:
    """作业进程第一件事：stdout / stderr 接到 `AI4SCI_JOB_LOG` 那个文件、stdin 接空，再把这个变量从
    环境里去掉（作业起的执行层、harness、叫醒的那一轮不该再接一遍）。不是作业什么都不做。

    在文件描述符这一层换（`dup2`）：作业起的子进程不另接也写进同一份日志（Windows 上 dup2 到
    0 / 1 / 2 同时换掉进程的标准句柄，子进程继承的就是它）。Python 这一层的三个流也重新包一遍：
    Windows 上原来接着控制台时，它们直接写控制台、不经文件描述符。进程活多久它们就开多久。"""
    path = os.environ.pop(LOG_ENV, None)
    if not path:
        return
    # O_BINARY：Windows 上 os.open 缺省开成文本模式，dup2 会把它带到 1、2，每行成了 \r\r\n
    binary = getattr(os, "O_BINARY", 0)
    log = os.open(path, os.O_WRONLY | os.O_APPEND | os.O_CREAT | binary)
    null = os.open(os.devnull, os.O_RDONLY | binary)
    for fd, std in ((null, 0), (log, 1), (log, 2)):
        os.dup2(fd, std)
    os.close(log)
    os.close(null)
    sys.stdin = open(0, encoding="utf-8", closefd=False)
    sys.stdout = open(1, "w", encoding="utf-8", errors="replace", buffering=1, closefd=False)
    sys.stderr = open(2, "w", encoding="utf-8", errors="backslashreplace", buffering=1,
                      closefd=False)


def attach_output(jobs_dir: Path, job_id: str, output: str, flow: str | None) -> Job:
    """子进程开了产出目录就回写它的 id 与它记在哪条流程下：看板从此能把这个作业画到那次产出、
    那条流程上。流程只认产出这一处——`--flow` 省了时是框架替它定的，命令行上看不出来。"""
    job = load(jobs_dir, job_id)
    job.output, job.flow = output, flow
    _save(jobs_dir, job)
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


def note(jobs_dir: Path, job_id: str, text: str) -> Job:
    """往一条作业的结论行后面补一句（产出删了：记录是历史留着，但指向的东西没了要说清）；已有就不重复。"""
    job = load(jobs_dir, job_id)
    if text not in job.result:
        job.result = f"{job.result}\t{text}" if job.result else text
        _save(jobs_dir, job)
    return job


def stop(ws: Workspace, job_id: str, *, by: str) -> Job:
    """人叫停：杀作业的整棵进程树（它自成会话，pgid 就是 pid；执行层的 Bash、harness 的 launcher
    各自还会开新的进程组，所以趟树逐组杀），记录写 stopped 与谁停的；作业开的那次产出还是 running
    的话替它记 failed（子进程被杀，没人回写）。产出是在别的机器上跑的（meta 记着 `compute`），
    那台机器上这次产出目录下还在跑的也一并杀（`cancel_under`）——演练里本机杀了、远端的
    uv pip sync 还在装（外层 #118）。远端没杀成不吞：记录照写 stopped，把错抛给叫停的人。
    cli 与 serve 共用这一个函数。

    只停真在跑的：已经结束的、lost 的都抛 JobNotRunning——对着一具尸体报「停了」是假话（P-7）。
    """
    job = load(ws.jobs, job_id)
    state = effective_status(job)
    if state != "running":
        raise JobNotRunning(f"作业 {job_id} 不在跑（{state}），停不了")
    killed = procs.kill_tree(job.pid, job.pid)
    job.status = "stopped"
    job.exit_code = None
    job.result = f"人停的（{by}）"
    job.finished_at = datetime.now(UTC).isoformat(timespec="seconds")
    _save(ws.jobs, job)
    LOGGER.info("job_stop job_id=%s by=%s killed_pgids=%s", job_id, by, killed)
    if not job.output:
        return job
    directory, meta = outputs.find_output(ws, job.output)
    if meta.status == "running":
        outputs.close_output(directory, meta, ok=False, line=job.result)
    name = (meta.compute or {}).get("name")
    if name and name != computes.LOCAL:
        compute = computes.instance(name)
        try:
            remote_killed = compute.cancel_under(compute.remote_dir_for(directory))
        except ComputeError as exc:
            job.result += f"；{name} 上的没停下来：{exc}"
            _save(ws.jobs, job)
            raise
        LOGGER.info("job_stop_remote job_id=%s compute=%s killed_pgids=%s",
                    job_id, name, remote_killed)
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
    return Job(**json.loads(read_text(path)))


def list_jobs(jobs_dir: Path) -> list[Job]:
    root = Path(jobs_dir)
    if not root.is_dir():
        return []
    return [Job(**json.loads(read_text(p))) for p in sorted(root.glob("*.json"))]


def jobs_for(jobs_dir: Path, output: str) -> list[Job]:
    """某次产出的全部作业，按起的先后。"""
    return [job for job in list_jobs(jobs_dir) if job.output == output]


def running_for(jobs_dir: Path, output: str) -> Job | None:
    """正在给某次产出干活的作业；没有就是 None。"""
    for job in reversed(jobs_for(jobs_dir, output)):
        if effective_status(job) == "running":
            return job
    return None


def running_flow(jobs_dir: Path, flow: str) -> Job | None:
    """正在照某条流程跑的作业；没有就是 None。"""
    for job in reversed(list_jobs(jobs_dir)):
        if job.flow == flow and effective_status(job) == "running":
            return job
    return None


def running_jobs(jobs_dir: Path) -> list[Job]:
    return [job for job in list_jobs(jobs_dir) if effective_status(job) == "running"]


def effective_status(job: Job) -> str:
    """记录说 running 但进程不在了，就是 lost：没人回写过结束，不能当它跑完了。"""
    if job.status != "running":
        return job.status
    return "running" if procs.pid_alive(job.pid) else "lost"


def _save(jobs_dir: Path, job: Job) -> None:
    Path(jobs_dir).mkdir(parents=True, exist_ok=True)
    write_atomic(_path(jobs_dir, job.job_id),
                 json.dumps(asdict(job), ensure_ascii=False, indent=2) + "\n")
