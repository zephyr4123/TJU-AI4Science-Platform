"""执行层端口：一个 coding agent CLI 一个适配器文件。

这里只放三样东西：结果结构、`Runner` 协议、按名字取适配器的函数。
没有注册表、没有抽象基类——纲领 §5 要求「一个后端一个文件，60 到 80 行」，
注册表会让"有哪些后端"散进各个模块的 import 副作用里，加后端时改动看不见。
显式字典反过来：加一个后端就是加一行，diff 里一眼能看到（P-8）。
"""

from __future__ import annotations

import importlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol, runtime_checkable

__all__ = ["RunResult", "Runner", "BackendNotFound", "get_backend", "available_backends"]


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
