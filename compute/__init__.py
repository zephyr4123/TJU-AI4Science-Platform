"""算力端口：一个后端一个文件（纲领 workflow.md §5）。

runner 对算力的全部需求只有五个动作：快照过去、起任务拿句柄、等、杀、产物回来。
`submit` / `wait` 分开而不是一个阻塞的 `run`：句柄要能落盘（`run_N/job.json`），
`loop resume` 重启后才接得回还在跑的任务、或给已经死掉的任务收尸——A-5 续跑的前提。

与 `backends/` 同一标准：没有抽象基类、没有注册表，加一个后端就是 `_COMPUTES` 里加一行。
"""

from __future__ import annotations

import importlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Protocol, runtime_checkable

__all__ = ["Job", "ExitStatus", "Compute", "ComputeNotFound", "get_compute", "available_computes"]


@dataclass
class Job:
    """一次远端任务的句柄，必须能落盘再读回（续跑靠它重新接上或 reap）。

    `pgid` 单独记而不是每次现查：进程死了以后 `os.getpgid` 就查不到了，
    而杀进程组恰恰发生在进程可能已经半死不活的时候。
    """

    pid: int
    pgid: int
    started_at: float
    remote_dir: str
    stdout_path: str
    stderr_path: str
    timeout_s: float

    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False, indent=2)

    @classmethod
    def from_json(cls, text: str) -> Job:
        """读回句柄。字段缺失直接抛 TypeError，不给默认值——续跑时蒙的值会变成错杀。"""
        return cls(**json.loads(text))


@dataclass
class ExitStatus:
    """任务的结局。`exit_code is None` 表示**未知**，不是成功。

    续跑时读回的 job 早已不是本进程的子进程，退出码根本拿不到（内核只留给亲爹）。
    这时填 0 就是把"不知道"讲成"成功"，账本会记下一条不存在的成绩（P-7）。
    """

    exit_code: int | None
    timed_out: bool
    elapsed_s: float
    stdout_path: str
    stderr_path: str

    @property
    def ok(self) -> bool:
        return self.exit_code == 0 and not self.timed_out


@runtime_checkable
class Compute(Protocol):
    def put(self, local_dir: Path, remote_dir: Path) -> None: ...

    def submit(
        self, remote_dir: Path, cmd: list[str], env: dict[str, str], timeout_s: float
    ) -> Job: ...

    def wait(self, job: Job, timeout_s: float | None = None) -> ExitStatus: ...

    def cancel(self, job: Job) -> None: ...

    def get(self, remote_dir: Path, local_dir: Path) -> None: ...


class ComputeNotFound(ValueError):
    """要的算力后端不存在。要的算力不可用绝不静默退回本地（纲领 §5）。"""


# 名字 → 模块。懒加载：将来 ssh / slurm 后端缺依赖时不连累 local。
_COMPUTES: dict[str, str] = {
    "local": "compute.local",
}


def available_computes() -> list[str]:
    return sorted(_COMPUTES)


def get_compute(name: str) -> Compute:
    try:
        module_path = _COMPUTES[name]
    except KeyError:
        raise ComputeNotFound(
            f"未知的算力后端 {name!r}；可用的有：{', '.join(available_computes())}"
        ) from None
    module = importlib.import_module(module_path)
    compute = module.make_compute()
    # 断言而不是信任：后端模块是人写的，形状对不上要在这里就炸，别等到跑一半
    assert hasattr(compute, "submit"), f"算力后端 {name!r} 的 make_compute() 返回值没有 submit()"
    return compute
