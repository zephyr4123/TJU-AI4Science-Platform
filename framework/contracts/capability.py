"""能力描述符：每个能力一份机器可读的自我描述，以及能力入口的统一形状（纲领 P-12、P-18、P-19）。

三层：**阶段**（七个研究阶段，固定）→ **能力**（一个阶段里的一件活，对 agent 就是一个 tool：
一条 `ai4sci cap` 命令）→ **实现**（这件活怎么干：一段代码、一个 skill、领域包里的东西）。
描述符说的是中间那层：它属于哪个阶段、职责、边界、输入、产出、终止条件。五栏都是给人读的——研究者、
协调 agent、工程师读同一份——讲机制、带通用的专业术语，不讲路径表：能力之间没有显式的输入输出
接口，一个能力要的东西不在 `--from` 点名的产出里，它开始执行时自己报错（P-18）。

给人看的字分三层（纲领 P-21）：`title` 是名，页面直接显示；`brief` 是一行，hover 显示；五栏是详情，
点开才看。三层各有规矩，`__post_init__` 断言：名是名词不超过八字（方法有公认名字的原样写，
AutoResearch），一行三十字内不带路径与参数名，详情是工程语言——文件名可以写，CLI 参数、口语不写。
参数的 `label` 是页面上的名字，`help` 是 hover 的一句。

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
# 描述符的五栏：每栏必填，页面与 `show caps` 按这个顺序、用这几个标题摆（栏名是词表里的词，P-21）
COLUMNS = (("does", "职责"), ("does_not", "边界"), ("brings", "输入"),
           ("leaves", "产出"), ("stops", "终止条件"))
# 文案三层的边界（P-21）：名不超过八字（拉丁字母的词整个算一个字）、一行三十字内、参数名不超过八字
TITLE_MAX = 8
BRIEF_MAX = 30
LABEL_MAX = 8
# 页面与描述符里都不许出现的词：口语、问句式标签、借来的量词与比喻。页面那份在 ui/web 的 copy 测试里
BANNED_WORDS = ("签了", "没成", "在跑", "续命", "这包", "越界", "干什么", "收尸", "按钮", "房间",
                "裁判", "一颗", "几颗", "每颗", "那颗", "哪颗")


def check_copy(where: str, text: str) -> None:
    """一段给人看的字里没有禁用词、没有 CLI 参数（`--x`）。断言信息只说位置与撞上的词。"""
    for word in BANNED_WORDS:
        assert word not in text, f"{where}里有「{word}」：换成词表里的词（P-21）"
    assert "--" not in text, f"{where}里写了 CLI 参数：页面与详情不写命令行的写法（P-21）"


def _cjk_length(text: str) -> int:
    """算字数：一个中日韩字算一个，拉丁字母的词整个算一个（AutoResearch 是一个词，
    不是十二个字）。"""
    count, in_word = 0, False
    for ch in text:
        if ch.isascii() and ch.isalnum():
            if not in_word:
                count += 1
                in_word = True
            continue
        in_word = False
        if not ch.isspace():
            count += 1
    return count


@dataclass(frozen=True)
class Param:
    """能力的一个可调参数。CLI 里是 `--<name 下划线换连字符>`，缺省值就是这里的 default。

    `in_flow` 为假的是每次调用时才定的（接不接着跑、修改意见），流程里写不了：
    编辑台不给它输入框，`workflows` 的检查也拒。"""

    name: str
    type: str
    default: Any
    help: str
    # 页面上的名字（`max_iters` → 最多轮数）：名词，不超过八字；`help` 是 hover 的一句
    label: str
    in_flow: bool = True

    def __post_init__(self) -> None:
        assert self.type in PARAM_TYPES, (
            f"参数 {self.name} 的类型只认 {tuple(PARAM_TYPES)}，得到 {self.type!r}")
        assert self.name.isidentifier(), f"参数名要是合法标识符：{self.name!r}"
        assert self.label.strip(), f"参数 {self.name} 要有页面上的名字 label（P-21）"
        assert _cjk_length(self.label) <= LABEL_MAX, (
            f"参数 {self.name} 的 label 超过 {LABEL_MAX} 字：名词，不写句子（P-21）")
        check_copy(f"参数 {self.name} 的 label", self.label)
        check_copy(f"参数 {self.name} 的 help", self.help)


@dataclass(frozen=True)
class Capability:
    """一个能力的描述符。`name` 是命令名（`ai4sci cap <name>`），等于子包名（连字符对下划线），
    `discover()` 会核对。

    `title` 是名（「分析初稿」：名词短语不超过八字，不用动宾；方法有公认名字的原样写，
    AutoResearch）；`brief` 是一行（三十字内，说拿什么做出什么，不带路径与参数名）；
    五栏（`COLUMNS`）是详情，说清这件活的
    边界与机制，页面、终端、协调 agent 的指南读同一份，不在某个界面里另抄。"谁来做"不另设字段：
    `needs_executor` 为真就是要起执行层（模型），否则不经模型；这一项是机器读的，页面不显示
    （P-21）。

    `continuable` 为真的能力可以接着上一次的产出继续干（`--continue <stage>/<n>`），不另开目录：
    auto-research 一批一批跑就是这样；别的能力每次都是新产出。"""

    name: str
    stage: str
    title: str
    brief: str
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
        assert _cjk_length(self.title) <= TITLE_MAX, (
            f"能力 {self.name} 的 title 超过 {TITLE_MAX} 字：名词短语，或方法的公认名字（P-21）")
        check_copy(f"能力 {self.name} 的 title", self.title)
        assert self.brief.strip(), f"能力 {self.name} 要有一行 brief（P-21）"
        assert _cjk_length(self.brief) <= BRIEF_MAX, (
            f"能力 {self.name} 的 brief 超过 {BRIEF_MAX} 字：一句话，细节进五栏（P-21）")
        assert not any(ch in self.brief for ch in "/_"), (
            f"能力 {self.name} 的 brief 里有路径或参数名：一行不写这些（P-21）")
        check_copy(f"能力 {self.name} 的 brief", self.brief)
        for key, label in COLUMNS:
            assert getattr(self, key).strip(), f"能力 {self.name} 的「{label}」空着：五栏必填"
            check_copy(f"能力 {self.name} 的「{label}」", getattr(self, key))
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
    """一个能力这次读什么：工作区根（需求、原件在那儿）与 `--from` 点名的产出目录。

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
    """能力要用的端口，由 CLI（或 UI 后端、测试）按名字取好后注入；能力自己不按名字找后端。
    `compute_label` 是那台算力的出处（名字、种类、主机名、GPU，P-23），记进产出的 meta。"""

    runner: Runner | None = None
    compute: Compute | None = None
    compute_label: dict | None = None


class CapabilityFailed(RuntimeError):
    """能力没能交出该留下的东西，或留下的不合约。信息要能直接给协调层看，不留半个栈让人猜。"""
