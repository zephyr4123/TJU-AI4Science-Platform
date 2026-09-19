"""能力描述符：每个能力一份机器可读的自我描述，以及能力入口的统一形状（纲领 P-12、P-18、P-19）。

三层：**阶段**（七个研究阶段，固定）→ **能力**（一个阶段里的一件活，对 agent 就是一个 tool：
一条 `ai4sci cap` 命令）→ **实现**（这件活怎么干：一段代码、一个 skill、领域包里的东西）。
描述符说的是中间那层：它属于哪个阶段、干什么、不干什么、要带什么进来、留下什么、什么时候停。五栏都是给人读的——研究者、
协调 agent、工程师读同一份——讲机制、带通用的专业术语，不讲路径表：能力之间没有显式的输入输出
接口，一颗能力要的东西不在 `--from` 点名的产出里，它开始执行时自己报错（P-18）。

能力是纯函数（P-19）：显式输入 → 自己阶段下的一个新产出目录。它没有「最新」这种状态，不默认读谁——
选输入是协调层的事（agent 看盘、或人指定）。入口约定（`framework/capabilities/__init__.py` 的
`discover()` 逐条断言）：

    每个能力子包导出 DESCRIPTOR: Capability
    每个能力子包导出 run(output_dir, inputs, ports, *, <params...>) -> str
        output_dir  框架已经建好的产出目录 <stage>/<n>/，能力往里写自己的文件（meta.yaml
        是框架写的）
        inputs      工作区根 + --from 点名的产出目录
        成功返回一行给协调层看的结论；失败 raise CapabilityFailed，不降级不兜底（P-7）

CLI 的参数从 `params` 生成，所以"CLI 参数与描述符一致"是构造保证，不是靠人对。
在契约层：不读盘、不跑东西，只定义形状。`Ports` 引用两个端口的协议，端口是框架任何一层
都可以 import 的（见 `tests/test_layering.py`）。
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from backends import Runner
from compute import Compute
from framework.contracts.stages import STAGE_NAMES, slug_of

# 参数只认这几种标量：CLI 与 UI 表单都能直接映射（bool 在 CLI 上是开关）；要更复杂的输入
# 应当是产物文件，不是参数
PARAM_TYPES: dict[str, type] = {"int": int, "float": float, "str": str, "bool": bool}
# 描述符的五栏：每栏必填，页面与 `show caps` 按这个顺序、用这几个标题摆
COLUMNS = (("does", "干什么"), ("does_not", "不干什么"), ("brings", "要带什么进来"),
           ("leaves", "留下什么"), ("stops", "什么时候停"))


@dataclass(frozen=True)
class Param:
    """能力的一个可调参数。CLI 里是 `--<name 下划线换连字符>`，缺省值就是这里的 default。

    `in_flow` 为假的是每次调用时才定的（接不接着跑、修改意见），流里写不了：
    编辑台不给它输入框，`workflows` 的检查也拒。"""

    name: str
    type: str
    default: Any
    help: str
    in_flow: bool = True

    def __post_init__(self) -> None:
        assert self.type in PARAM_TYPES, (
            f"参数 {self.name} 的类型只认 {tuple(PARAM_TYPES)}，得到 {self.type!r}")
        assert self.name.isidentifier(), f"参数名要是合法标识符：{self.name!r}"


@dataclass(frozen=True)
class Capability:
    """一颗能力的描述符。`name` 是命令名（`ai4sci cap <name>`），等于子包名（连字符对下划线），
    `discover()` 会核对。

    `title` 是给研究者看的人话名（「分析初稿」：名词短语，不用动宾）；五栏（`COLUMNS`）说清这件活的
    边界与机制，页面、终端、协调 agent 的指南读同一份，不在某个界面里另抄。"谁来做"不另设字段：
    `needs_executor` 为真就是助理（执行层 agent）做，否则是机器。

    `continuable` 为真的能力可以接着上一次的产出继续干（`--continue <stage>/<n>`），不另开目录：
    auto-research 一批一批跑就是这样；别的能力每次都是新产出。"""

    name: str
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
    continuable: bool = False

    def __post_init__(self) -> None:
        assert self.stage in STAGE_NAMES, (
            f"能力 {self.name} 的阶段只认 {STAGE_NAMES}，得到 {self.stage!r}")
        assert self.title.strip(), f"能力 {self.name} 要有给研究者看的 title"
        for key, label in COLUMNS:
            assert getattr(self, key).strip(), f"能力 {self.name} 的「{label}」空着：五栏必填"
        names = [p.name for p in self.params]
        assert len(names) == len(set(names)), f"能力 {self.name} 的参数名重复：{names}"

    @property
    def stage_slug(self) -> str:
        return slug_of(self.stage)

    def param_names(self) -> tuple[str, ...]:
        return tuple(p.name for p in self.params)

    def to_dict(self) -> dict[str, Any]:
        """给 `ai4sci show caps --json` 与 UI 后端：纯数据，没有类。"""
        return {**asdict(self), "stage_slug": self.stage_slug}


@dataclass(frozen=True)
class Inputs:
    """一颗能力这次读什么：工作区根（需求、原件在那儿）与 `--from` 点名的产出目录。

    目录都是绝对路径、框架已经核过在不在、冻没冻；能力自己只管从里面找它要的文件，找不到就报错
    说清缺哪个阶段的哪个文件。"""

    workspace: Path
    outputs: tuple[Path, ...] = ()
    # 与 outputs 一一对应的 id（"design/1"），报错与结论行里用它指东西
    ids: tuple[str, ...] = field(default_factory=tuple)

    def of_stage(self, slug: str) -> list[Path]:
        """点名的产出里属于某个阶段的那几个（按 id 的阶段目录名判）。"""
        return [p for p, i in zip(self.outputs, self.ids, strict=True) if i.split("/")[0] == slug]

    def one_of(self, slug: str, label: str) -> Path:
        """恰好要一个某阶段的产出；少了、多了都是能力开工时的错，报清楚。"""
        found = self.of_stage(slug)
        if len(found) != 1:
            raise CapabilityFailed(
                f"{label}要且只要一个「{slug}」阶段的产出（--from {slug}/<n>），"
                f"得到 {len(found)} 个：{[i for i in self.ids if i.startswith(slug + '/')]}")
        return found[0]


@dataclass
class Ports:
    """能力要用的端口，由 CLI（或 UI 后端、测试）按名字取好后注入；能力自己不按名字找后端。"""

    runner: Runner | None = None
    compute: Compute | None = None


class CapabilityFailed(RuntimeError):
    """能力没能交出该留下的东西，或留下的不合约。信息要能直接给协调层看，不留半个栈让人猜。"""
