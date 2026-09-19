"""agent 端口：一个 coding agent CLI 一个适配器文件。

两个端口，同一批适配器文件：`Runner` 是执行层（一次会话、跑完退出、只看它改了什么），
`Chat` 是协调层（多轮、按 session id 续接、事件流边跑边出）。同一个 CLI 两种用法，
所以放同一个文件里；换一家 CLI 就是加一个文件、在 `_BACKENDS` 加一行（主人红线：涉及
agent 的一律可替换）。

这里只放几样东西：结果结构、两个协议、按名字取适配器的函数。
没有注册表、没有抽象基类——纲领 §5 要求「一个后端一个文件，60 到 80 行」，
注册表会让"有哪些后端"散进各个模块的 import 副作用里，加后端时改动看不见。
显式字典反过来：加一个后端就是加一行，diff 里一眼能看到（P-8）。
"""

from __future__ import annotations

import importlib
import math
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol, runtime_checkable

__all__ = ["RunResult", "Runner", "ChatEvent", "Choice", "Tuning", "Knobs", "Chat",
           "BackendNotFound", "get_backend", "get_chat", "available_backends"]


@dataclass
class RunResult:
    """一次执行层调用的全部可取证产物。

    `changed_files` 由框架自己快照 diff 得出，不采信 CLI 自报（P-2：执行层不当自己的裁判）。
    `cost_usd` 在超时被杀时拿不到（result 事件根本没来），此时按约定填 NaN 表示"未知"，
    绝不填 0 —— 填 0 会让账本上的预算统计静默偏低，属于 P-7 说的静默降级。
    """

    exit_code: int
    events: list[dict] = field(default_factory=list)
    changed_files: list[str] = field(default_factory=list)
    cost_usd: float = 0.0
    duration_s: float = 0.0
    timed_out: bool = False
    stdout_tail: str = ""


@runtime_checkable
class Runner(Protocol):
    """执行层适配器的唯一形状。

    `allowed_paths` 是"只许改这些目录"的意图；各家 CLI 的权限模型语义对不齐，
    适配器只负责尽量收紧，真正的门是 runner 事后拿 `changed_files` 判（纲领 §5）。
    """

    def run(
        self,
        prompt: str,
        cwd: Path,
        timeout_s: float,
        allowed_paths: list[Path],
    ) -> RunResult: ...


# 事件种类：适配器把各家 CLI 的原生事件翻成这几种，上层（落盘、CLI 打印、网页 SSE）只认这几种。
# `delta` 是助理正在说的一小段字（外层 #65）：每家适配器都必须逐字吐，最后仍要有一条完整的 `text`
# ——上层拿 text 替换攒起来的 delta，落盘只留 text 不留 delta。不逐字吐的适配器，页面上一整段
# 突然蹦出来，那是体验事故不是实现细节
CHAT_EVENT_KINDS = ("init", "delta", "text", "tool_use", "tool_result", "denied", "done", "error")


@dataclass
class ChatEvent:
    """协调 agent 一轮里的一个事件。`raw` 是 CLI 的原生事件，留档用；上层不解析它。

    `done` 带这一轮的成本、耗时、后端 session id 与最终回复；`error` 是这一轮没走完
    （超时、进程死了、协议坏了），`text` 里是原因。成本拿不到填 NaN 不填 0（同 RunResult）。
    `delta` 的 `text` 是刚到的那几个字，不是累计；同一段话结束时会来一条完整的 `text`。
    """

    kind: str
    text: str = ""
    tool: str = ""
    tool_input: dict = field(default_factory=dict)
    is_error: bool = False
    session_id: str | None = None
    cost_usd: float = math.nan
    duration_s: float = 0.0
    exit_code: int | None = None
    raw: dict = field(default_factory=dict)

    def __post_init__(self) -> None:
        assert self.kind in CHAT_EVENT_KINDS, f"未知的事件种类 {self.kind!r}"


@dataclass(frozen=True)
class Choice:
    """旋钮上的一个刻度：`id` 给 CLI 看，`label` 给人看，`note` 是一句提示（可空）。"""

    id: str
    label: str
    note: str = ""


@dataclass(frozen=True)
class Tuning:
    """一轮用什么：模型与思考深度。`None` 是「后端自己的缺省」，适配器不替人猜一个。"""

    model: str | None = None
    effort: str | None = None


@dataclass(frozen=True)
class Knobs:
    """一家 CLI 能拧的两个旋钮（外层 #86）：有哪些模型、有哪几档思考深度、不选时用什么。

    清单由适配器自报（页面照单渲染，不写死哪家有什么）；`model` / `effort` 是不选时实际会用的值，
    拿不准（CLI 自己的缺省）就 None——页面上写「默认」，不编一个。每家 CLI 都能换模型、
    换思考深度，这是端口的要求；哪家真不能换就报空清单，页面上那枚旋钮不出现。
    """

    models: tuple[Choice, ...]
    efforts: tuple[Choice, ...]
    model: str | None = None
    effort: str | None = None

    def check(self, tuning: Tuning) -> None:
        """人选的值要在清单上；不在就报一句带清单的话（ValueError：配置值非法，不静默回落）。"""
        for name, picked, choices in (("模型", tuning.model, self.models),
                                       ("思考深度", tuning.effort, self.efforts)):
            if picked is not None and picked not in {c.id for c in choices}:
                raise ValueError(
                    f"{name} {picked!r} 不在清单上；可选：{', '.join(c.id for c in choices)}")


@runtime_checkable
class Chat(Protocol):
    """协调层适配器的唯一形状：一句话进、一串事件出，能按 session id 续。

    `session_id=None` 开新会话，否则续接；每一轮至少吐一个 `init`（带 session id）和
    一个 `done` 或 `error`。`system_prompt` 是协调层指南；`allowed_paths` 与 `bash_rules`
    的语义同 `Runner`：尽量收紧，各家 CLI 的权限模型对不齐；`readable_paths` 是工作目录之外
    「能读不能写」的目录（研究助理看流程库用，P-16）。`chat_id` 是这段对话的名字：
    适配器要让 agent 调用的命令拿得到它（环境变量 `AI4SCI_CHAT_ID`），后台作业跑完才知道叫醒谁。
    `tuning` 是这一轮用什么模型、什么思考深度（外层 #86）：None 或字段为 None 就用后端缺省；
    `knobs()` 报这家 CLI 有哪些刻度，页面与终端只许从里面选。
    `cost_reporting` 说清 `done.cost_usd` 是什么：`"turn"` 是这一轮的花费；`"session"` 是续接的
    整段会话到此刻的累计（Claude Code 的 `--resume` 就这样报），框架自己减上一轮的累计得到这一轮的。
    报错了就是页面上一句「你是什么模型」显示 $0.28（实测 2026-09-19：那一轮实际 $0.014）。
    """

    cost_reporting: str

    def knobs(self) -> Knobs: ...

    def turn(
        self,
        message: str,
        cwd: Path,
        timeout_s: float,
        *,
        session_id: str | None,
        system_prompt: str,
        allowed_paths: list[Path],
        bash_rules: tuple[str, ...],
        readable_paths: list[Path] = (),
        chat_id: str | None = None,
        tuning: Tuning | None = None,
    ) -> Iterator[ChatEvent]: ...


class BackendNotFound(ValueError):
    """要的后端不存在。继承 ValueError：调用方按"配置值非法"处理，不是运行时故障。"""


# 名字 → 模块。懒加载是为了让"没装某个 CLI 的 SDK"不影响别的后端 import。
_BACKENDS: dict[str, str] = {
    "claude_code": "backends.claude_code",
}


def available_backends() -> list[str]:
    return sorted(_BACKENDS)


def get_backend(name: str) -> Runner:
    """按名字取适配器。名字不对就报错退出，绝不静默回退到某个默认后端（P-7）。"""
    try:
        module_path = _BACKENDS[name]
    except KeyError:
        raise BackendNotFound(
            f"未知的执行层后端 {name!r}；可用的有：{', '.join(available_backends())}"
        ) from None
    module = importlib.import_module(module_path)
    runner = module.make_runner()
    # 断言而不是信任：适配器模块是人写的，形状对不上要在这里就炸，别等到跑一半
    assert hasattr(runner, "run"), f"后端 {name!r} 的 make_runner() 没有返回带 run() 的对象"
    return runner


def get_chat(name: str) -> Chat:
    """按名字取协调层适配器；同 `get_backend`，名字不对就报错，不回退。"""
    try:
        module_path = _BACKENDS[name]
    except KeyError:
        raise BackendNotFound(
            f"未知的 agent 后端 {name!r}；可用的有：{', '.join(available_backends())}"
        ) from None
    module = importlib.import_module(module_path)
    assert hasattr(module, "make_chat"), f"后端 {name!r} 还没有协调层适配器（make_chat）"
    chat = module.make_chat()
    assert hasattr(chat, "turn"), f"后端 {name!r} 的 make_chat() 没有返回带 turn() 的对象"
    assert hasattr(chat, "knobs"), \
        f"后端 {name!r} 的协调层适配器没有 knobs()：得报有哪些模型与思考深度"
    return chat
