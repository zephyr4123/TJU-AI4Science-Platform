"""能力描述符：每个能力一份机器可读的自我描述，以及能力入口的统一形状（纲领 P-12）。

为什么要有它：低代码 UI 要把能力当节点拖，协调 agent 要知道一个能力吃什么吐什么，
契约测试要能逐个能力核对——三方读的都是同一份描述。它是从实验与分析两个真实例里
抽出来的公共部分，不是先画好再往里填的：只放两个能力都用得上的字段。

入口约定（`framework/capabilities/__init__.py` 的 `discover()` 逐条断言）：

    每个能力子包导出 DESCRIPTOR: Capability
    每个能力子包导出 run(run_dir: Path, ports: Ports, *, <params...>) -> str
        成功返回一行给协调层看的结论；失败 raise CapabilityFailed，不降级不兜底（P-7）

CLI 的参数从 `params` 生成，所以"CLI 参数与描述符一致"是构造保证，不是靠人对。
在契约层：不读盘、不跑东西，只定义形状。`Ports` 引用两个端口的协议，端口是框架任何一层
都可以 import 的（见 `tests/test_layering.py`）。
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from backends import Runner
from compute import Compute

LEVELS = ("run", "project")
# 参数只认这三种标量：CLI 与 UI 表单都能直接映射；要更复杂的输入应当是产物文件，不是参数
PARAM_TYPES: dict[str, type] = {"int": int, "float": float, "str": str}


@dataclass(frozen=True)
class Artifact:
    """一个产物：相对 `runs/<run_id>/` 的路径（目录以 / 结尾），谁生产它由描述符的归属决定。"""

    name: str
    path: str
    description: str


@dataclass(frozen=True)
class Param:
    """能力的一个可调参数。CLI 里是 `--<name 下划线换连字符>`，缺省值就是这里的 default。"""

    name: str
    type: str
    default: Any
    help: str

    def __post_init__(self) -> None:
        assert self.type in PARAM_TYPES, (
            f"参数 {self.name} 的类型只认 {tuple(PARAM_TYPES)}，得到 {self.type!r}")
        assert self.name.isidentifier(), f"参数名要是合法标识符：{self.name!r}"


@dataclass(frozen=True)
class Capability:
    """一个能力的描述符。`name` 必须等于子包名，`discover()` 会核对。"""

    name: str
    level: str
    summary: str
    inputs: tuple[Artifact, ...]
    outputs: tuple[Artifact, ...]
    params: tuple[Param, ...] = ()
    needs_executor: bool = False
    needs_compute: bool = False
    criteria: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        assert self.level in LEVELS, f"能力 {self.name} 的 level 只认 {LEVELS}，得到 {self.level!r}"
        assert self.outputs, (
            f"能力 {self.name} 必须声明至少一个产物：没有产物的能力无法被验证（P-4）")
        names = [p.name for p in self.params]
        assert len(names) == len(set(names)), f"能力 {self.name} 的参数名重复：{names}"

    def param_names(self) -> tuple[str, ...]:
        return tuple(p.name for p in self.params)

    def to_dict(self) -> dict[str, Any]:
        """给 `ai4sci cap list --json` 与 UI 后端：纯数据，没有类。"""
        return asdict(self)


@dataclass
class Ports:
    """能力要用的端口，由 CLI（或 UI 后端、测试）按名字取好后注入；能力自己不按名字找后端。"""

    runner: Runner | None = None
    compute: Compute | None = None


class CapabilityFailed(RuntimeError):
    """能力没能交出合约的产物，或交出的产物不合约。信息要能直接给协调层看，不留半个栈让人猜。"""
