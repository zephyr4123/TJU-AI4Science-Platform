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

from dataclasses import asdict, dataclass, field
from typing import Any

from backends import Runner
from compute import Compute

# task：动任务包（接任务、跑基线），产物路径相对任务包目录，入口 run(task_dir, ports, ...)；
# run：动一个 run，产物路径相对 runs/<run_id>/，入口 run(run_dir, ports, ...)；project 还没有实例
LEVELS = ("task", "run", "project")
# 做科研的七个阶段（纲领 workflow §1，Q-1）。它是能力上面的一层标签：每颗能力属于一个阶段，
# 一个阶段下可以挂几颗能力（设计 = design + baseline，实验 = start + experiment）。阶段不定先后、
# 没有代码、没有运行时——顺序归协调层（P-10），这里只回答"这颗按钮是干哪一段科研的"。
# 顺序是页面与 `show caps` 列清单的顺序，空着的阶段也列出来，让人看见还缺什么
STAGES = ("文献", "假设", "设计", "实验", "分析", "写作", "验证")
# 参数只认这几种标量：CLI 与 UI 表单都能直接映射（bool 在 CLI 上是开关）；要更复杂的输入
# 应当是产物文件，不是参数
PARAM_TYPES: dict[str, type] = {"int": int, "float": float, "str": str, "bool": bool}


@dataclass(frozen=True)
class Artifact:
    """一个产物：相对根目录的路径（目录以 / 结尾）。根由能力的 level 定：run 级相对
    `runs/<run_id>/`，task 级相对任务包目录。谁生产它由描述符的归属决定。"""

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
    """一个能力的描述符。`name` 必须等于子包名，`discover()` 会核对。

    `summary` 给协调 agent 与工程师看（说机制）；`title` 与 `what` 是给研究者看的人话（说效果），
    页面、终端界面读同一份，不在某个界面里另抄一份。`stage` 是它属于哪个科研阶段。
    "谁来做"不另设字段：`needs_executor` 为真就是助理（执行层 agent）做，否则是机器。"""

    name: str
    level: str
    summary: str
    inputs: tuple[Artifact, ...]
    outputs: tuple[Artifact, ...]
    params: tuple[Param, ...] = ()
    needs_executor: bool = False
    needs_compute: bool = False
    criteria: tuple[str, ...] = ()
    stage: str = field(kw_only=True)
    title: str = field(kw_only=True)
    what: str = field(kw_only=True)

    def __post_init__(self) -> None:
        assert self.level in LEVELS, f"能力 {self.name} 的 level 只认 {LEVELS}，得到 {self.level!r}"
        assert self.stage in STAGES, f"能力 {self.name} 的阶段只认 {STAGES}，得到 {self.stage!r}"
        assert self.title.strip() and self.what.strip(), (
            f"能力 {self.name} 要有给研究者看的 title 与 what（人话标题与一句说明）")
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
