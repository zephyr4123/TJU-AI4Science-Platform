"""算力端口：一个后端一个文件（纲领 workflow.md §5，P-23 算力归人）。

runner 对算力的全部需求只有五个动作：快照过去（`put`，目录已在就拒——那是被杀的一轮）、
起任务拿句柄、等、杀、产物回来；外加几样让「远端」成立的东西：本地目录在那台机器上对应哪个目录
（`remote_dir_for`）、同步一个允许已在的目录（`sync`，设计那包）、同步跑一条短命令拿输出
（`run`，建 venv、算清单）、在那台机器上怎么起 uv（`uv`，远端按 `env/` 建自己的 venv）、
探一遍机器（`check`，接机器时与之后随时）。执行层 agent 永远在本机，远端只跑 harness。
`submit` / `wait` 分开而不是一个阻塞的 `run`：句柄要能落盘（`run_N/job.json`），
`loop resume` 重启后才接得回还在跑的任务、或给已经死掉的任务收尸——A-5 续跑的前提。

与 `backends/` 同一标准：没有抽象基类、没有注册表，加一个后端就是 `_COMPUTES` 里加一行。
一台机器的连接参数（主机、端口、用户、密钥路径、远端根）由 framework 从按人的
`computes.yaml` 读出来传给 `make_compute(**params)`；这里不读任何文件。
"""

from __future__ import annotations

import importlib
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Protocol, runtime_checkable

__all__ = ["Job", "ExitStatus", "Outcome", "Probe", "Compute", "ComputeNotFound", "get_compute",
           "available_computes"]


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


@dataclass
class Outcome:
    """同步跑完一条命令的结果（建 venv、算清单这类短活；跑 harness 走 submit / wait）。"""

    exit_code: int
    stdout: str
    stderr: str

    @property
    def ok(self) -> bool:
        return self.exit_code == 0


@dataclass
class Probe:
    """探一遍机器的结果：一项一行（名字、过没过、一句话），外加记进出处的几样。

    连不上也是一条 item（过没过 = False），不抛：`compute add` 要把整张报告打给人看，
    探测不过只报告不拒绝保留记录，用的时候再拒（主人：不设自我感动的坎）。
    """

    items: list[tuple[str, bool, str]] = field(default_factory=list)
    hostname: str = ""
    gpu: str = ""
    python: str = ""
    uv: str = ""
    # 机器上已有的 Python 环境（盘点给人选：隔离新建还是用现成的）：{name, python, version, torch}
    envs: list[dict] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return all(passed for _, passed, _ in self.items)

    def to_dict(self) -> dict:
        return {"ok": self.ok, "items": [list(i) for i in self.items], "hostname": self.hostname,
                "gpu": self.gpu, "python": self.python, "uv": self.uv, "envs": list(self.envs)}


@runtime_checkable
class Compute(Protocol):
    """算力适配器的唯一形状。`remote_dir` 一律是字符串：本地是本机路径，ssh 是那台机器上的路径。"""

    kind: str
    uv: list[str]  # 在这台机器上起 uv 的 argv 前缀：本地是 `python -m uv`，远端是 `uv`
    scratch: str  # 这台机器上跑探测类短命令的目录（`run` 会建），不属于任何产出

    def remote_dir_for(self, local_dir: Path) -> str: ...

    def put(self, local_dir: Path, remote_dir: str) -> None: ...

    def sync(self, local_dir: Path, remote_dir: str) -> None: ...

    def run(self, remote_dir: str, cmd: list[str], env: dict[str, str],
            timeout_s: float) -> Outcome: ...

    def submit(
        self, remote_dir: str, cmd: list[str], env: dict[str, str], timeout_s: float
    ) -> Job: ...

    def wait(self, job: Job, timeout_s: float | None = None) -> ExitStatus: ...

    def cancel(self, job: Job) -> None: ...

    def cancel_under(self, remote_dir: str) -> list[int]:
        """杀这个目录（含子目录）下所有还在跑的作业，返回杀掉的进程组；没有 Job 句柄也能停——
        人叫停时下手的是另一个进程（`ai4sci job stop`），它只知道产出目录在哪台机器的哪儿。"""
        ...

    def get(self, remote_dir: str, local_dir: Path) -> None: ...

    def check(self) -> Probe: ...


class ComputeError(RuntimeError):
    """那台机器够不着或它上面的命令起不来（连不上、密钥不对、rsync 失败）；各适配器的错都是
    它的子类，framework 只认这一个。"""


class ComputeNotFound(ValueError):
    """要的算力后端不存在。要的算力不可用绝不静默退回本地（纲领 §5）。"""


# 种类 → 模块。懒加载：ssh 后端要 rsync / ssh 这些外部命令，缺了不连累 local。
_COMPUTES: dict[str, str] = {
    "local": "compute.local",
    "ssh": "compute.ssh",
}


def available_computes() -> list[str]:
    return sorted(_COMPUTES)


def get_compute(kind: str, **params: object) -> Compute:
    """按种类取适配器，连接参数原样递给 `make_compute`。种类不对就报错，绝不静默退回本地（P-7）。"""
    try:
        module_path = _COMPUTES[kind]
    except KeyError:
        raise ComputeNotFound(
            f"未知的算力种类 {kind!r}；可用的有：{', '.join(available_computes())}"
        ) from None
    module = importlib.import_module(module_path)
    compute = module.make_compute(**params)
    # 断言而不是信任：后端模块是人写的，形状对不上要在这里就炸，别等到跑一半
    assert hasattr(compute, "submit"), f"算力后端 {kind!r} 的 make_compute() 返回值没有 submit()"
    assert compute.kind == kind, f"算力后端 {kind!r} 自报的 kind 是 {compute.kind!r}"
    return compute
