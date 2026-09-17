"""能力层：一个能力一个子包，互不 import；`discover()` 扫目录找到它们（纲领 P-10、P-12）。

能力之间不许直接调用对方，要串起来是协调层的活。所以这里没有顺序表、没有注册表：
加一个能力就是加一个子包，`discover()` 用 pkgutil 扫一遍，每个子包必须导出

    DESCRIPTOR: Capability                       机器可读的自我描述（contracts/capability.py）
    run(run_dir: Path, ports: Ports, *, <params>) -> str   统一入口；失败 raise CapabilityFailed
    （task 级能力的第一个参数叫 task_dir：它动的是任务包，那时还没有 run）

签名与描述符对不上在这里就断言炸掉，而不是等 CLI 起来才发现某个参数没人读（P-8）。
`discover()` 是 CLI 与 UI 后端拿能力的唯一入口，测试也走它。

能力之间的接口是文件名（纲领 P-13「文档即接口」）：一个文件只有一个生产者，谁要用就报名字。
所以扫完全部子包再查两条全局约束：没有两颗能力声明同一个输出路径；每个输入路径要么是种子
（发布那一刻任务包里已有的、或 start 建 run 时就有的），要么是某颗同级能力的输出。名字写错
在加载这一刻就被拒，不等跑到一半才发现"没人产出 summary.md"。
"""

from __future__ import annotations

import importlib
import inspect
import pkgutil
from types import ModuleType

from framework.contracts.capability import Capability
from framework.contracts.flow import RUN_SEEDS, TASK_SEEDS

ENTRYPOINT = "run"
# 每个级别里"一开始就有"的名字：输入不必有生产者的那几样
SEEDS_BY_LEVEL = {"task": TASK_SEEDS, "run": RUN_SEEDS}
# 前两个参数按 level 定：第一个参数的名字就说明了这个能力动的是什么目录
LEADING_PARAMS_BY_LEVEL = {"task": ("task_dir", "ports"), "run": ("run_dir", "ports")}


def discover() -> dict[str, ModuleType]:
    """名字 → 已 import 的能力子包，按名字排序。每个都过了描述符与入口签名的断言。"""
    found: dict[str, ModuleType] = {}
    for info in sorted(pkgutil.iter_modules(__path__), key=lambda i: i.name):
        if not info.ispkg:
            continue
        module = importlib.import_module(f"{__name__}.{info.name}")
        check_capability_module(info.name, module)
        found[info.name] = module
    check_catalog([module.DESCRIPTOR for module in found.values()])
    return found


def check_catalog(descriptors: list[Capability]) -> None:
    """整份清单的两条约束：输出路径唯一（同级别内）、输入路径有出处（种子或同级能力的输出）。

    `start` 是任务段到 run 段的桥，它声明的输出 `runs/<run_id>/` 是一个位置不是接口，没人把它当
    输入；桥的条件由 `contracts.flow` 按名字单独查，这里不管它。"""
    producers: dict[tuple[str, str], str] = {}
    for cap in descriptors:
        for artifact in cap.outputs:
            key = (cap.level, artifact.path)
            assert key not in producers, (
                f"能力 {cap.name} 与 {producers[key]} 都声明输出 {artifact.path!r}"
                f"（{cap.level} 级）：一个文件只有一个生产者，产物放在 <能力名>/ 下就不会撞")
            producers[key] = cap.name
    for cap in descriptors:
        available = set(SEEDS_BY_LEVEL[cap.level]) | {
            path for (level, path) in producers if level == cap.level}
        for artifact in cap.inputs:
            assert artifact.path in available, (
                f"能力 {cap.name} 要 {artifact.path!r}，{cap.level} 级里没人产出、也不是种子"
                f"（种子：{SEEDS_BY_LEVEL[cap.level]}；有人产出的：{sorted(available)}）")


def check_capability_module(package_name: str, module: ModuleType) -> Capability:
    """一个能力子包的三条硬约束：有描述符、名字对得上、入口签名等于描述符的参数表。"""
    descriptor = getattr(module, "DESCRIPTOR", None)
    assert isinstance(descriptor, Capability), (
        f"能力子包 {package_name} 没有导出 Capability 类型的 DESCRIPTOR")
    assert descriptor.name == package_name, (
        f"能力 {package_name} 的描述符名字是 {descriptor.name!r}，必须等于子包名")
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
