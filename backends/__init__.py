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

__all__ = ["RunResult", "Runner", "ChatEvent", "Chat", "BackendNotFound", "get_backend",
           "get_chat", "available_backends"]


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


# 事件种类：适配器把各家 CLI 的原生事件翻成这几种，上层（落盘、CLI 打印、网页 SSE）只认这几种
CHAT_EVENT_KINDS = ("init", "text", "tool_use", "tool_result", "denied", "done", "error")


@dataclass
class ChatEvent:
    """协调 agent 一轮里的一个事件。`raw` 是 CLI 的原生事件，留档用；上层不解析它。

    `done` 带这一轮的成本、耗时、后端 session id 与最终回复；`error` 是这一轮没走完
    （超时、进程死了、协议坏了），`text` 里是原因。成本拿不到填 NaN 不填 0（同 RunResult）。
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


@runtime_checkable
class Chat(Protocol):
    """协调层适配器的唯一形状：一句话进、一串事件出，能按 session id 续。

    `session_id=None` 开新会话，否则续接；每一轮至少吐一个 `init`（带 session id）和
    一个 `done` 或 `error`。`system_prompt` 是协调层指南；`allowed_paths` 与 `bash_rules`
    的语义同 `Runner`：尽量收紧，各家 CLI 的权限模型对不齐。`chat_id` 是这段对话的名字：
    适配器要让 agent 按的按钮拿得到它（环境变量 `AI4SCI_CHAT_ID`），后台作业跑完才知道叫醒谁。
    """

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
        chat_id: str | None = None,
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
    return chat
