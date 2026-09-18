"""能力层：一个能力一个子包，互不 import；`discover()` 扫目录找到它们（纲领 P-10、P-12、P-18）。

能力之间不许直接调用对方，要串起来是协调层的活。所以这里没有顺序表、没有注册表：
加一个能力就是加一个子包，`discover()` 用 pkgutil 扫一遍，每个子包必须导出

    DESCRIPTOR: Capability                       机器可读的自我描述（contracts/capability.py）
    run(run_dir: Path, ports: Ports, *, <params>) -> str   统一入口；失败 raise CapabilityFailed
    （task 级能力的第一个参数叫 workspace：它动的是工作区里的任务包，那时还没有 run；纲领 P-15）

签名与描述符对不上在这里就断言炸掉，而不是等 CLI 起来才发现某个参数没人读（P-8）。
`discover()` 是 CLI 与 UI 后端拿能力的唯一入口，测试也走它。

能力之间不接管子（P-18）：描述符里没有吃吐路径表，这里也不查"谁的输入谁产出"。一颗能力要的东西
盘上没有，它自己进门时报错（P-7），协调 agent 读了报错去补——这是它会的事。子包名里的下划线
在命令名里是连字符（`auto_research/` 就是 `ai4sci cap auto-research`）：Python 的包名不许带连字符，
给人看的名字又不该带下划线。
"""

from __future__ import annotations

import importlib
import inspect
import pkgutil
from types import ModuleType

from framework.contracts.capability import Capability

ENTRYPOINT = "run"
# 前两个参数按 level 定：第一个参数的名字就说明了这个能力动的是什么（工作区 / run 目录）
LEADING_PARAMS_BY_LEVEL = {"task": ("workspace", "ports"), "run": ("run_dir", "ports")}


def command_name(package_name: str) -> str:
    """子包名 → 命令名：下划线换连字符。"""
    return package_name.replace("_", "-")


def discover() -> dict[str, ModuleType]:
    """命令名 → 已 import 的能力子包，按名字排序。每个都过了描述符与入口签名的断言。"""
    found: dict[str, ModuleType] = {}
    for info in sorted(pkgutil.iter_modules(__path__), key=lambda i: i.name):
        if not info.ispkg:
            continue
        module = importlib.import_module(f"{__name__}.{info.name}")
        descriptor = check_capability_module(info.name, module)
        found[descriptor.name] = module
    return found


def check_capability_module(package_name: str, module: ModuleType) -> Capability:
    """一个能力子包的三条硬约束：有描述符、名字对得上、入口签名等于描述符的参数表。"""
    descriptor = getattr(module, "DESCRIPTOR", None)
    assert isinstance(descriptor, Capability), (
        f"能力子包 {package_name} 没有导出 Capability 类型的 DESCRIPTOR")
    assert descriptor.name == command_name(package_name), (
        f"能力 {package_name} 的描述符名字是 {descriptor.name!r}，必须等于子包名"
        f"（下划线换连字符：{command_name(package_name)!r}）")
    entry = getattr(module, ENTRYPOINT, None)
    assert callable(entry), f"能力 {package_name} 没有导出 {ENTRYPOINT}()"
    assert descriptor.level in LEADING_PARAMS_BY_LEVEL, (
        f"能力 {package_name} 的 level {descriptor.level!r} 还没有入口约定"
        f"（有的：{tuple(LEADING_PARAMS_BY_LEVEL)}）")
    leading = LEADING_PARAMS_BY_LEVEL[descriptor.level]
    params = inspect.signature(entry).parameters
    names = tuple(params)
    assert names[: len(leading)] == leading, (
        f"能力 {package_name}（level={descriptor.level}）的 {ENTRYPOINT}() 前两个参数必须是 "
        f"{leading}，得到 {names[:2]}")
    keyword_only = tuple(n for n, p in params.items() if p.kind is inspect.Parameter.KEYWORD_ONLY)
    assert keyword_only == descriptor.param_names(), (
        f"能力 {package_name} 的 {ENTRYPOINT}() 关键字参数 {keyword_only} 与描述符 params "
        f"{descriptor.param_names()} 对不上")
    assert len(names) == len(leading) + len(keyword_only), (
        f"能力 {package_name} 的 {ENTRYPOINT}() 除 {leading} 外只许关键字参数")
    return descriptor
