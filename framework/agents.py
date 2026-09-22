"""按人的底座清单：`~/.config/ai4sci/agents.yaml` 的唯一读写点（纲领 P-25 底座归人）。

与算力清单并列（一个文件一个生产者，P-13）：助理用哪家 coding agent CLI、
执行层用哪家（两层可以不同），
每家新对话用的模型与思考深度——一律具体值，没有「跟缺省」这一项；文件里没填的那家用适配器给的起点
（`Knobs.model` / `.effort`）。上次自检（`last_check`）也记在这里，
页面与 `agent list` 读文件不再连。
文件永远不进 git、不进工作区、不进数据根；`AI4SCI_AGENTS` 可指向别处（测试）。

有哪几家不是这里定的：`backends._BACKENDS` 那张表就是「有哪些」，加一家是加一个适配器文件，没有
`agent add`。文件里写了 `_BACKENDS` 没有的名字、或清单外的模型 / 深度，读到就报错（AgentsInvalid），
不静默回落——CLI 升级把模型名下掉了，要人去 `ai4sci agent use` 重选，不是悄悄换一个。
"""

from __future__ import annotations

import os
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

from backends import (
    TITLES,
    AgentProbe,
    BackendNotFound,
    Knobs,
    Tuning,
    available_backends,
    get_chat,
)

PATH_ENV = "AI4SCI_AGENTS"
DEFAULT_PATH = Path.home() / ".config" / "ai4sci" / "agents.yaml"
ROLES = ("chat", "executor")
ROLE_LABELS = {"chat": "对话用", "executor": "执行用"}
FALLBACK = "claude_code"


class AgentsInvalid(ValueError):
    """文件不合形状：问题一行一条。"""


@dataclass
class Entry:
    name: str
    model: str
    effort: str
    last_check: dict[str, Any] | None = None

    @property
    def title(self) -> str:
        return TITLES.get(self.name, self.name)

    @property
    def tuning(self) -> Tuning:
        return Tuning(model=self.model, effort=self.effort)

    def summary(self) -> str:
        """`agent list` 的一行：名字、模型、深度、上次自检过没过。"""
        check = self.last_check
        state = "未检查" if not check else ("可用" if check.get("ok") else "检查未过")
        version = (check or {}).get("version") or "-"
        return f"{self.name}\t{self.title}\t{version}\t{self.model}\t{self.effort}\t{state}"


@dataclass
class Registry:
    entries: dict[str, Entry] = field(default_factory=dict)
    chat: str = FALLBACK
    executor: str = FALLBACK

    def get(self, name: str) -> Entry:
        try:
            return self.entries[name]
        except KeyError:
            raise BackendNotFound(
                f"没有叫 {name!r} 的 agent；有：{', '.join(self.entries)}") from None

    def role(self, role: str) -> str:
        assert role in ROLES, f"role 只认 {ROLES}，得到 {role!r}"
        return getattr(self, role)


def path() -> Path:
    raw = os.environ.get(PATH_ENV)
    return Path(raw).expanduser() if raw else DEFAULT_PATH


def knobs_of(name: str) -> Knobs:
    """这家的清单与起点（适配器自报）。名字不在 `_BACKENDS` 里就是 BackendNotFound。"""
    return get_chat(name).knobs()


# 谁来报清单：缺省是真适配器；服务把自己接的适配器传进来（测试里是剧本），清单与校验才对得上
KnobsOf = Callable[[str], Knobs]


def load(knobs: KnobsOf = knobs_of) -> Registry:
    """读文件；不存在就是每家用起点、两层都用 claude_code。形状不对整份报错，不带着半份往下走。"""
    registry = Registry(entries={name: _fresh(name, knobs) for name in available_backends()})
    file = path()
    if not file.is_file():
        return registry
    try:
        raw = yaml.safe_load(file.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        raise AgentsInvalid(f"{file}: 不是合法 YAML：{exc}") from exc
    if not isinstance(raw, dict):
        raise AgentsInvalid(f"{file}: 顶层要是键值对")
    problems: list[str] = []
    for name, doc in (raw.get("agents") or {}).items():
        if name not in registry.entries:
            problems.append(f"{file}: agents.{name}: 没有这家适配器"
                            f"（有：{', '.join(available_backends())}）")
            continue
        entry, why = _parse_entry(str(name), doc, knobs)
        if entry is None:
            problems.append(f"{file}: agents.{name}: {why}")
            continue
        registry.entries[str(name)] = entry
    for role in ROLES:
        picked = raw.get(role, FALLBACK)
        if picked not in registry.entries:
            problems.append(f"{file}: {role} = {picked!r} 不是一家适配器")
        else:
            setattr(registry, role, str(picked))
    if problems:
        raise AgentsInvalid("\n".join(problems))
    return registry


def save(registry: Registry) -> Path:
    file = path()
    file.parent.mkdir(parents=True, exist_ok=True)
    doc: dict[str, Any] = {"chat": registry.chat, "executor": registry.executor, "agents": {}}
    for name, entry in registry.entries.items():
        item: dict[str, Any] = {"model": entry.model, "effort": entry.effort}
        if entry.last_check:
            item["last_check"] = entry.last_check
        doc["agents"][name] = item
    header = ("# ai4sci 的底座清单（纲领 P-25）：按人、不进 git。\n"
              "# chat / executor 是助理与执行层各用哪家；每家写新对话用的模型与思考深度"
              "（具体值）。\n"
              "# 由 ai4sci agent use / check 维护；手改也行，值要在那家 ai4sci agent list "
              "的清单上。\n")
    file.write_text(header + yaml.safe_dump(doc, allow_unicode=True, sort_keys=False),
                    encoding="utf-8")
    return file


def _fresh(name: str, knobs: KnobsOf) -> Entry:
    picked = knobs(name)
    return Entry(name=name, model=picked.model, effort=picked.effort)


def _parse_entry(name: str, doc: Any, knobs: KnobsOf) -> tuple[Entry | None, str]:
    if not isinstance(doc, dict):
        return None, "要是键值对"
    picked = knobs(name)
    model = doc.get("model", picked.model)
    effort = doc.get("effort", picked.effort)
    if not isinstance(model, str) or not isinstance(effort, str):
        return None, "model 与 effort 要是字符串"
    try:
        picked.check(Tuning(model=model, effort=effort))
    except ValueError as exc:
        return None, f"{exc}（ai4sci agent use {name} --model … --effort … 重选）"
    check = doc.get("last_check")
    if check is not None and not isinstance(check, dict):
        return None, "last_check 要是键值对"
    return Entry(name=name, model=model, effort=effort, last_check=check), ""


def role_backend(role: str, knobs: KnobsOf = knobs_of) -> str:
    """助理（chat）或执行层（executor）用哪家。"""
    return load(knobs).role(role)


def tuning_for(name: str, knobs: KnobsOf = knobs_of) -> Tuning:
    """这家新对话 / 新会话用什么：文件里记的，没记就是起点；永远是具体值。"""
    return load(knobs).get(name).tuning


def use(name: str, *, roles: tuple[str, ...] = (), model: str | None = None,
        effort: str | None = None, knobs: KnobsOf = knobs_of) -> Entry:
    """换用哪家、改这家的缺省。值先过那家的清单，不在就报错不写。"""
    registry = load(knobs)
    entry = registry.get(name)
    if model is not None or effort is not None:
        picked = Tuning(model=model or entry.model, effort=effort or entry.effort)
        knobs(name).check(picked)
        entry.model, entry.effort = picked.model, picked.effort
    for role in roles:
        assert role in ROLES, f"role 只认 {ROLES}，得到 {role!r}"
        setattr(registry, role, name)
    save(registry)
    return entry


def record_check(name: str, probe: AgentProbe, knobs: KnobsOf = knobs_of) -> Entry:
    """自检结果记回文件（`last_check`），加时间。"""
    registry = load(knobs)
    entry = registry.get(name)
    entry.last_check = {**probe.to_dict(), "at": datetime.now(UTC).isoformat(timespec="seconds")}
    save(registry)
    return entry
