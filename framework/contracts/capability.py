"""能力描述符：每个能力一份机器可读的自我描述，以及能力入口的统一形状（纲领 P-12、P-18）。

三层：**阶段**（七个研究阶段，固定）→ **能力**（一个阶段里的一件活，对 agent 就是一个 tool：
一条 `ai4sci cap` 命令）→ **实现**（这件活怎么干：一段代码、一个 skill、领域包里的东西）。
描述符说的是中间那层：它属于哪个阶段、干什么、不干什么、要带什么进来、留下什么、什么时候停。五栏都是给人读的——研究者、
协调 agent、工程师读同一份——讲机制、带通用的专业术语，不讲路径表：能力之间没有显式的输入输出
接口，下一颗开始执行时自己看盘上有什么（P-18）。

入口约定（`framework/capabilities/__init__.py` 的 `discover()` 逐条断言）：

    每个能力子包导出 DESCRIPTOR: Capability
    每个能力子包导出 run(run_dir, ports, *, <params...>) -> str（task 级第一个参数叫 workspace）
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

# task：动任务包（说清课题、写评分脚本跑基线、开一次实验），入口 run(workspace, ports, ...)；
# run：动一个 run，入口 run(run_dir, ports, ...)；project 还没有实例
LEVELS = ("task", "run", "project")
# 七个研究阶段（纲领 workflow §1，P-18）。每颗能力属于且只属于一个阶段；一个阶段可以有几颗能力，
# 也可以暂时空着（清单里照样列出来，让人看见缺什么）。阶段不定先后、没有代码、没有运行时——顺序归流与
# 协调层（P-10），这里只回答"这颗能力是干哪一段科研的"。顺序是页面与 `show caps` 列清单的顺序。
STAGES = ("文献", "假设", "设计", "实验", "分析", "写作", "验证")
# 参数只认这几种标量：CLI 与 UI 表单都能直接映射（bool 在 CLI 上是开关）；要更复杂的输入
# 应当是产物文件，不是参数
PARAM_TYPES: dict[str, type] = {"int": int, "float": float, "str": str, "bool": bool}
# 描述符的五栏：每栏必填，页面与 `show caps` 按这个顺序、用这几个标题摆
COLUMNS = (("does", "干什么"), ("does_not", "不干什么"), ("brings", "要带什么进来"),
           ("leaves", "留下什么"), ("stops", "什么时候停"))


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
    """一颗能力的描述符。`name` 是命令名（`ai4sci cap <name>`），等于子包名（连字符对下划线），
    `discover()` 会核对。

    `title` 是给研究者看的人话名（「写分析初稿」）；五栏（`COLUMNS`）说清这件活的边界与机制，
    页面、终端、协调 agent 的指南读同一份，不在某个界面里另抄。"谁来做"不另设字段：
    `needs_executor` 为真就是助理（执行层 agent）做，否则是机器。"""

    name: str
    level: str
    stage: str
    title: str
    does: str
    does_not: str
    brings: str
    leaves: str
    stops: str
    params: tuple[Param, ...] = ()
    needs_executor: bool = False
    needs_compute: bool = False

    def __post_init__(self) -> None:
        assert self.level in LEVELS, f"能力 {self.name} 的 level 只认 {LEVELS}，得到 {self.level!r}"
        assert self.stage in STAGES, f"能力 {self.name} 的阶段只认 {STAGES}，得到 {self.stage!r}"
        assert self.title.strip(), f"能力 {self.name} 要有给研究者看的 title"
        for key, label in COLUMNS:
            assert getattr(self, key).strip(), f"能力 {self.name} 的「{label}」空着：五栏必填"
        names = [p.name for p in self.params]
        assert len(names) == len(set(names)), f"能力 {self.name} 的参数名重复：{names}"

    def param_names(self) -> tuple[str, ...]:
        return tuple(p.name for p in self.params)

    def to_dict(self) -> dict[str, Any]:
        """给 `ai4sci show caps --json` 与 UI 后端：纯数据，没有类。"""
        return asdict(self)


@dataclass
class Ports:
    """能力要用的端口，由 CLI（或 UI 后端、测试）按名字取好后注入；能力自己不按名字找后端。"""

    runner: Runner | None = None
    compute: Compute | None = None


class CapabilityFailed(RuntimeError):
    """能力没能交出该留下的东西，或留下的不合约。信息要能直接给协调层看，不留半个栈让人猜。"""
