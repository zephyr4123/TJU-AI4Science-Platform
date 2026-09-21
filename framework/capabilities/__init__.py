"""能力层：一个能力一个子包，互不 import；`discover()` 扫目录找到它们（纲领 P-10、P-12、P-18）。

能力之间不许直接调用对方，要串起来是协调层的活。所以这里没有顺序表、没有注册表：
加一个能力就是加一个子包，`discover()` 用 pkgutil 扫一遍，每个子包必须导出

    DESCRIPTOR: Capability                       机器可读的自我描述（contracts/capability.py）
    run(output_dir: Path, inputs: Inputs, ports: Ports, *, <params>) -> str
                                                 统一入口：读 inputs、往 output_dir 写；失败 raise
                                                 CapabilityFailed

签名与描述符对不上在这里就断言炸掉，而不是等 CLI 起来才发现某个参数没人读（P-8）。
`discover()` 是 CLI 与 UI 后端拿能力的唯一入口，测试也走它。

能力之间没有显式的输入输出接口（P-18）：描述符里没有路径表，这里也不查"谁的输入谁产出"。一个能力
要的东西 `--from` 点名的产出里没有，它自己开始执行时报错（P-7），协调 agent
读了报错去补——这是它会的事。
子包名里的下划线在命令名里是连字符（`auto_research/` 就是 `ai4sci cap auto-research`）：包名
不许带连字符，给人看的名字又不该带下划线。

文件名按阶段定、不按能力定（纲领 P-20）：每个阶段钉一个**主文件**，进这个阶段的任何能力都必须
留下它，下游只认阶段主文件、不认是哪个能力产的——换一个同阶段的能力，下游不改。`MAIN_FILES` 一个
阶段一行，第一个进来的能力定名、之后锁死；还没有能力的阶段不预填（有第二个用例才抽象）。
`discover()` 断言描述符的「产出」栏写到了本阶段的主文件；同族能力私下的文件归族包
（`framework/experiment/`），能力另外留的文件是私有的，谁都不许依赖。接一个新能力看
`docs/add-a-capability.md`。
"""

from __future__ import annotations

import importlib
import inspect
import pkgutil
from types import ModuleType
from typing import Any

from framework.contracts import stages
from framework.contracts.capability import Capability

ENTRYPOINT = "run"
# 前三个参数：产出目录、输入、端口（纲领 P-19：能力是纯函数，显式输入 → 一个产出目录）
LEADING_PARAMS = ("output_dir", "inputs", "ports")
# 阶段主文件（P-20）：进这个阶段的能力都得留下它，「产出」栏里要写到它的名字。
# 文献、假设、写作三个阶段还没有能力，等第一个进来再填；设计那一行是实验族定的名，第二个族进设计
# 阶段那天要么沿用、要么改成族无关的，是一次决策。
MAIN_FILES: dict[str, tuple[str, ...]] = {
    # 文献格的主文件由助理手写（output new literature），不是能力产的：纲领 P-24 定名
    "文献": ("sources.md",),
    "设计": ("scoring.yaml",),
    "实验": ("ledger.tsv", "results.json"),
    "分析": ("analysis.md",),
    "验证": ("report.json",),
}
# 主文件在页面上的名字（P-21：文件名是机器的名字，上屏要翻译）；每个主文件一行，少一行导入时就炸
MAIN_FILE_LABELS: dict[str, str] = {
    "sources.md": "材料来源",
    "scoring.yaml": "评分契约",
    "ledger.tsv": "账本",
    "results.json": "结果",
    "analysis.md": "分析稿",
    "report.json": "核对报告",
}
assert {n for names in MAIN_FILES.values() for n in names} == set(MAIN_FILE_LABELS), (
    "MAIN_FILES 与 MAIN_FILE_LABELS 对不上：每个主文件要有页面上的名字")


def stage_table() -> list[dict[str, Any]]:
    """给 `GET /stages`：阶段表加每个阶段的主文件（名字 + 页面上的名字）。"""
    return [{**stage, "main_files": [{"name": n, "label": MAIN_FILE_LABELS[n]}
                                     for n in MAIN_FILES.get(stage["name"], ())]}
            for stage in stages.to_dicts()]


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
    """一个能力子包的四条硬约束：有描述符、名字对得上、入口签名等于描述符的参数表、
    「留下什么」写到了本阶段的主文件。"""
    descriptor = getattr(module, "DESCRIPTOR", None)
    assert isinstance(descriptor, Capability), (
        f"能力子包 {package_name} 没有导出 Capability 类型的 DESCRIPTOR")
    assert descriptor.name == command_name(package_name), (
        f"能力 {package_name} 的描述符名字是 {descriptor.name!r}，必须等于子包名"
        f"（下划线换连字符：{command_name(package_name)!r}）")
    entry = getattr(module, ENTRYPOINT, None)
    assert callable(entry), f"能力 {package_name} 没有导出 {ENTRYPOINT}()"
    leading = LEADING_PARAMS
    params = inspect.signature(entry).parameters
    names = tuple(params)
    assert names[: len(leading)] == leading, (
        f"能力 {package_name} 的 {ENTRYPOINT}() 前三个参数必须是 {leading}，得到 {names[:3]}")
    keyword_only = tuple(n for n, p in params.items() if p.kind is inspect.Parameter.KEYWORD_ONLY)
    assert keyword_only == descriptor.param_names(), (
        f"能力 {package_name} 的 {ENTRYPOINT}() 关键字参数 {keyword_only} 与描述符 params "
        f"{descriptor.param_names()} 对不上")
    assert len(names) == len(leading) + len(keyword_only), (
        f"能力 {package_name} 的 {ENTRYPOINT}() 除 {leading} 外只许关键字参数")
    for main in MAIN_FILES.get(descriptor.stage, ()):
        assert main in descriptor.leaves, (
            f"能力 {package_name} 在「{descriptor.stage}」阶段，「产出」栏里要写到这个阶段的"
            f"主文件 {main}（P-20：文件名按阶段定，下游只认它）")
    return descriptor
