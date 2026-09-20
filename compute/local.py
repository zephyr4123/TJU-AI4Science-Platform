"""本地算力后端：put=cp，submit=Popen 新进程组，cancel=killpg，get=no-op。

本地"远端"就是本机另一个目录（`remote_dir_for` 是恒等映射），所以 `get` 在两边同一目录时
什么都不用做。即便如此也照走同一个 Protocol：调用点现在就存在（P-8），ssh 是第二个实现，
接口是它校验出来的。
"""

from __future__ import annotations

import os
import platform
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from compute import ExitStatus, Job, Outcome, Probe
from compute.procs import group_alive, kill_tree

# 快照不带过去的目录：`.git` 是 work/ 的状态载体（run_N 是只读快照，不该有仓）；
# `.ai4sci` 是执行层事件流日志、`__pycache__` 是字节码，带过去只会让每轮快照越滚越大；
# `.venv` 是环境不是产物，venv 也不可搬迁，harness 经 $AI4SCI_PYTHON 用 run 自己那份；
# `.job` 是上一次 submit 的日志与退出码。
IGNORED = (".git", ".ai4sci", "__pycache__", ".venv", ".job")
JOB_DIRNAME = ".job"
_POLL_S = 0.05


class LocalCompute:
    kind = "local"

    def __init__(self) -> None:
        # 本进程 submit 出去的任务留着 Popen：只有亲爹拿得到退出码。
        # 读回的 job（续跑）不在这里，wait 会走"已死、退出码未知"那条路。
        self._live: dict[int, subprocess.Popen] = {}

    @property
    def uv(self) -> list[str]:
        """本机的 uv 是平台 venv 里的那份（与 experiment/env.py 同一份），不找系统 PATH 上的。"""
        return [sys.executable, "-m", "uv"]

    @property
    def scratch(self) -> str:
        return str(Path(tempfile.gettempdir()) / "ai4sci-scratch")

    def remote_dir_for(self, local_dir: Path) -> str:
        return str(Path(local_dir).resolve())

    def put(self, local_dir: Path, remote_dir: str) -> None:
        remote_dir = Path(remote_dir)
        if Path(local_dir).resolve() == remote_dir.resolve():
            return
        if remote_dir.exists():
            # 快照目录一轮一个，已经在那儿只有一种解释：那一轮被杀了、没走完。
            # 往里叠一层新快照会把上一轮的产物和这一轮的混在一起，成绩就说不清了。
            raise FileExistsError(
                f"快照目录已存在，可能是被杀的一轮，请跑 ai4sci loop resume 收尾：{remote_dir}"
            )
        shutil.copytree(local_dir, remote_dir, ignore=shutil.ignore_patterns(*IGNORED))

    def sync(self, local_dir: Path, remote_dir: str) -> None:
        """同步过去，允许已在（设计那包建环境、跑基线）；本地跑本地就是同一个目录，什么都不做。"""
        remote_dir = Path(remote_dir)
        if Path(local_dir).resolve() == remote_dir.resolve():
            return
        shutil.copytree(local_dir, remote_dir, dirs_exist_ok=True,
                        ignore=shutil.ignore_patterns(*IGNORED))

    def run(self, remote_dir: str, cmd: list[str], env: dict[str, str],
            timeout_s: float) -> Outcome:
        """同步跑一条短命令（建 venv、算清单、探测）；目录不在就建；超时按非零退出报，不吞。"""
        Path(remote_dir).mkdir(parents=True, exist_ok=True)
        try:
            proc = subprocess.run(cmd, cwd=remote_dir, env={**os.environ, **env},
                                  stdin=subprocess.DEVNULL, capture_output=True, text=True,
                                  timeout=timeout_s, check=False)
        except subprocess.TimeoutExpired as exc:
            return Outcome(exit_code=124, stdout=str(exc.stdout or ""),
                           stderr=f"{str(exc.stderr or '')}\n超过 {timeout_s:g} 秒")
        except OSError as exc:
            return Outcome(exit_code=127, stdout="", stderr=str(exc))
        return Outcome(exit_code=proc.returncode, stdout=proc.stdout, stderr=proc.stderr)

    def submit(
        self, remote_dir: str, cmd: list[str], env: dict[str, str], timeout_s: float
    ) -> Job:
        remote_dir = Path(remote_dir).resolve()
        assert remote_dir.is_dir(), f"提交前 remote_dir 必须已经就位：{remote_dir}"
        assert timeout_s > 0, f"timeout_s 必须是正数，得到 {timeout_s!r}"
        job_dir = remote_dir / JOB_DIRNAME
        job_dir.mkdir(parents=True, exist_ok=True)
        out_path, err_path = job_dir / "stdout.log", job_dir / "stderr.log"
        # 日志句柄交给子进程后本进程就撒手：stdout 落盘不进 prompt（P-9）
        with out_path.open("wb") as out, err_path.open("wb") as err:
            proc = subprocess.Popen(
                cmd, cwd=remote_dir, env={**os.environ, **env},
                stdin=subprocess.DEVNULL, stdout=out, stderr=err,
                start_new_session=True,  # 自成进程组，超时才有一整组可杀
            )
        self._live[proc.pid] = proc
        return Job(pid=proc.pid, pgid=os.getpgid(proc.pid), started_at=time.time(),
                   remote_dir=str(remote_dir), stdout_path=str(out_path),
                   stderr_path=str(err_path), timeout_s=float(timeout_s))

    def wait(self, job: Job, timeout_s: float | None = None) -> ExitStatus:
        limit = job.timeout_s if timeout_s is None else timeout_s
        deadline = time.monotonic() + limit
        proc = self._live.get(job.pid)
        code: int | None = None
        timed_out = False
        if proc is not None:
            try:
                code = proc.wait(timeout=limit)
            except subprocess.TimeoutExpired:
                timed_out = True
        else:
            # 读回的句柄：只能看进程组还在不在，退出码内核不会给非亲代（保持 None=未知）
            while group_alive(job.pgid) and time.monotonic() < deadline:
                time.sleep(_POLL_S)
            timed_out = group_alive(job.pgid)
        if timed_out:
            self.cancel(job)
            if proc is not None:
                code = proc.wait(timeout=10)
        return ExitStatus(exit_code=code, timed_out=timed_out,
                          elapsed_s=time.time() - job.started_at,
                          stdout_path=job.stdout_path, stderr_path=job.stderr_path)

    def cancel(self, job: Job) -> None:
        kill_tree(job.pid, job.pgid)

    def get(self, remote_dir: str, local_dir: Path) -> None:
        remote_dir, local_dir = Path(remote_dir), Path(local_dir)
        if remote_dir.resolve() == local_dir.resolve():
            return  # 本地跑本地：产物本来就在那儿，拷回自己是白费一次 IO
        shutil.copytree(remote_dir, local_dir, dirs_exist_ok=True,
                        ignore=shutil.ignore_patterns(*IGNORED))

    def check(self) -> Probe:
        """本机：解释器、uv、有没有 GPU（nvidia-smi 在不在）、磁盘。"""
        probe = Probe(hostname=platform.node(), python=platform.python_version())
        probe.items.append(("Python", True, f"{probe.python}（平台 venv）"))
        uv = subprocess.run([*self.uv, "--version"], capture_output=True, text=True, check=False)
        probe.uv = uv.stdout.strip().split()[-1] if uv.returncode == 0 else ""
        probe.items.append(("uv", uv.returncode == 0, probe.uv or "平台 venv 里没有 uv：make venv"))
        smi = shutil.which("nvidia-smi")
        if smi:
            out = subprocess.run([smi, "--query-gpu=name,memory.total", "--format=csv,noheader"],
                                 capture_output=True, text=True, check=False)
            probe.gpu = out.stdout.strip().splitlines()[0] if out.returncode == 0 else ""
        probe.items.append(("GPU", True, probe.gpu or "无"))
        usage = shutil.disk_usage(Path.home())
        probe.items.append(("磁盘", True, f"{usage.free // 2**30} GB 可用"))
        return probe


def make_compute() -> LocalCompute:
    return LocalCompute()
