"""能力层：一个能力一个子包，互不 import；`discover()` 扫目录找到它们（纲领 P-10、P-12）。

能力之间不许直接调用对方，要串起来是协调层的活。所以这里没有顺序表、没有注册表：
加一个能力就是加一个子包，`discover()` 用 pkgutil 扫一遍，每个子包必须导出

    DESCRIPTOR: Capability                       机器可读的自我描述（contracts/capability.py）
    run(run_dir: Path, ports: Ports, *, <params>) -> str   统一入口；失败 raise CapabilityFailed

签名与描述符对不上在这里就断言炸掉，而不是等 CLI 起来才发现某个参数没人读（P-8）。
`discover()` 是 CLI 与 UI 后端拿能力的唯一入口，测试也走它。
"""

from __future__ import annotations

import importlib
import inspect
import pkgutil
from types import ModuleType

from framework.contracts.capability import Capability

ENTRYPOINT = "run"
LEADING_PARAMS = ("run_dir", "ports")


def discover() -> dict[str, ModuleType]:
    """名字 → 已 import 的能力子包，按名字排序。每个都过了描述符与入口签名的断言。"""
    found: dict[str, ModuleType] = {}
    for info in sorted(pkgutil.iter_modules(__path__), key=lambda i: i.name):
        if not info.ispkg:
            continue
        module = importlib.import_module(f"{__name__}.{info.name}")
        check_capability_module(info.name, module)
        found[info.name] = module
    return found


def check_capability_module(package_name: str, module: ModuleType) -> Capability:
    """一个能力子包的三条硬约束：有描述符、名字对得上、入口签名等于描述符的参数表。"""
    descriptor = getattr(module, "DESCRIPTOR", None)
    assert isinstance(descriptor, Capability), (
        f"能力子包 {package_name} 没有导出 Capability 类型的 DESCRIPTOR")
    assert descriptor.name == package_name, (
        f"能力 {package_name} 的描述符名字是 {descriptor.name!r}，必须等于子包名")
    entry = getattr(module, ENTRYPOINT, None)
    assert callable(entry), f"能力 {package_name} 没有导出 {ENTRYPOINT}()"
    params = inspect.signature(entry).parameters
    names = tuple(params)
    assert names[: len(LEADING_PARAMS)] == LEADING_PARAMS, (
        f"能力 {package_name} 的 {ENTRYPOINT}() 前两个参数必须是 {LEADING_PARAMS}，"
        f"得到 {names[:2]}")
    keyword_only = tuple(n for n, p in params.items() if p.kind is inspect.Parameter.KEYWORD_ONLY)
    assert keyword_only == descriptor.param_names(), (
        f"能力 {package_name} 的 {ENTRYPOINT}() 关键字参数 {keyword_only} 与描述符 params "
        f"{descriptor.param_names()} 对不上")
    assert len(names) == len(LEADING_PARAMS) + len(keyword_only), (
        f"能力 {package_name} 的 {ENTRYPOINT}() 除 {LEADING_PARAMS} 外只许关键字参数")
    return descriptor
