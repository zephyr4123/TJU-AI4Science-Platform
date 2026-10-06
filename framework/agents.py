"""按人的底座清单：平台的家里 `agents.yaml` 的唯一读写点（纲领 P-25 底座归人；位置由
`paths.agents_file()` 给，外层 #263）。

与算力清单并列（一个文件一个生产者，P-13）：助理用哪家 coding agent CLI、
执行层用哪家（两层可以不同），每家用谁的模型（供应商：官方登录、官方 API、DeepSeek、Kimi、自定义，
外层 #266）、新对话用的模型与思考深度——一律具体值，没有「跟缺省」这一项；文件里没填的那家用官方
登录与它的起点（`Knobs.model` / `.effort`）。模型清单跟着供应商走：用 DeepSeek 的 key 就只有
DeepSeek 的模型。上次自检（`last_check`）也记在这里，页面与 `agent list` 读文件不再连。
文件永远不进 git、不进工作区；key 不在这里，在 `keys.yaml`（`framework/keys.py`）。

有哪几家不是这里定的：`backends._BACKENDS` 那张表就是「有哪些」，加一家是加一个适配器文件，没有
`agent add`；每家有哪些供应商是适配器的 `PROVIDERS`。文件里写了没有的家、没有的供应商、或清单外的
模型 / 深度，读到就报错（AgentsInvalid），不静默回落——CLI 升级把模型名下掉了，要人去
`ai4sci agent use` 重选，不是悄悄换一个。

框架起适配器只走这里的 `chat` / `runner` / `probe`：`Link`（私有目录、供应商、key）只在
`link()` 造。开新对话把供应商和模型一起抄进对话 meta，续这段对话按 meta 里的供应商接
（`chat(name, provider)`），改设置只影响之后开的对话（P-25）。
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

import backends
from backends import (
    CUSTOM,
    OFFICIAL,
    TITLES,
    AgentProbe,
    BackendNotFound,
    Chat,
    Knobs,
    Link,
    Provider,
    Runner,
    Tuning,
    available_backends,
    get_backend,
    get_chat,
)
from framework import keys, paths

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
    provider: str = OFFICIAL
    # 只有自定义供应商才有：兼容的接口地址与人填的模型名
    base_url: str = ""
    models: tuple[str, ...] = ()
    last_check: dict[str, Any] | None = None

    @property
    def title(self) -> str:
        return TITLES.get(self.name, self.name)

    @property
    def tuning(self) -> Tuning:
        return Tuning(model=self.model, effort=self.effort)

    def summary(self) -> str:
        """`agent list` 的一行：名字、供应商、模型、深度、上次自检过没过。"""
        check = self.last_check
        state = "未检查" if not check else ("可用" if check.get("ok") else "检查未过")
        version = (check or {}).get("version") or "-"
        return (f"{self.name}\t{self.title}\t{version}\t{self.provider}\t{self.model}"
                f"\t{self.effort}\t{state}")


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
    return paths.agents_file()


def provider_of(name: str, provider: str, base_url: str = "",
                models: tuple[str, ...] = ()) -> Provider:
    """这家的一个供应商（目录里的，或照地址与模型名拼的自定义）；没有就 ValueError。"""
    return backends.provider_of(name, Link(home=Path(), provider=provider, base_url=base_url,
                                           models=models))


def link(name: str, provider: str | None = None) -> Link:
    """这家 CLI 这次怎么接（外层 #263 / #266）：私有目录在平台的家里；供应商缺省照文件里这家选的
    （续一段老对话时给它 meta 里记的），key 从家里的 keys.yaml 取。"""
    raw = _raw_entry(name)
    picked = provider or str(raw.get("provider") or OFFICIAL)
    base_url = str(raw.get("base_url") or "") if picked == CUSTOM else ""
    models = tuple(str(m) for m in raw.get("models") or ()) if picked == CUSTOM else ()
    key_name = provider_of(name, picked, base_url, models).key
    return Link(home=paths.agent_home(name), provider=picked,
                key=keys.get(key_name) if key_name else None, base_url=base_url, models=models)


def chat(name: str, provider: str | None = None) -> Chat:
    """协调层适配器。名字不在 `_BACKENDS` 里就是 BackendNotFound；`provider` 给了就按它接
    （续老对话）。"""
    return get_chat(name, link(name, provider))


def runner(name: str) -> Runner:
    """执行层适配器：执行层每次都是新会话，照设置接。"""
    return get_backend(name, link(name))


def probe(name: str) -> AgentProbe:
    """自检一家（四句人话，P-25）：照设置里这家的供应商。"""
    return backends.probe(name, link(name))


def login_command(name: str) -> tuple[list[str], dict[str, str]]:
    """在平台的家里登录这家的官方账号：命令与环境。"""
    return backends.login_command(name, link(name, OFFICIAL))


def logout_command(name: str) -> tuple[list[str], dict[str, str]]:
    """登出平台家里这家的官方账号。"""
    return backends.logout_command(name, link(name, OFFICIAL))


def knobs_of(name: str) -> Knobs:
    """这家的清单与起点：跟着文件里这家选的供应商走。名字不对是 BackendNotFound。"""
    return chat(name).knobs()


# 谁来报清单：缺省是真适配器；服务把自己接的适配器传进来（测试里是剧本），清单与校验才对得上
KnobsOf = Callable[[str], Knobs]


def load(knobs: KnobsOf = knobs_of) -> Registry:
    """读文件；不存在就是每家用官方登录的起点、两层都用 claude_code。形状不对整份报错，
    不带着半份往下走。"""
    registry = Registry(entries={name: _fresh(name, knobs) for name in available_backends()})
    file = path()
    if not file.is_file():
        return registry
    raw = _read(file)
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
        item: dict[str, Any] = {"provider": entry.provider, "model": entry.model,
                                "effort": entry.effort}
        if entry.provider == CUSTOM:
            item["base_url"] = entry.base_url
            item["models"] = list(entry.models)
        if entry.last_check:
            item["last_check"] = entry.last_check
        doc["agents"][name] = item
    header = ("# ai4sci 的底座清单（纲领 P-25）：按人、不进 git。\n"
              "# chat / executor 是助理与执行层各用哪家；每家写用谁的模型（provider）、"
              "新对话用的模型与思考深度（具体值）。\n"
              "# 由 ai4sci agent use / check 与设置页维护；手改也行，值要在那家那个供应商的清单上。"
              "key 不在这里（keys.yaml）。\n")
    file.write_text(header + yaml.safe_dump(doc, allow_unicode=True, sort_keys=False),
                    encoding="utf-8")
    return file


def _read(file: Path) -> dict[str, Any]:
    try:
        raw = yaml.safe_load(file.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        raise AgentsInvalid(f"{file}: 不是合法 YAML：{exc}") from exc
    if not isinstance(raw, dict):
        raise AgentsInvalid(f"{file}: 顶层要是键值对")
    return raw


def _raw_entry(name: str) -> dict[str, Any]:
    """文件里这家那一块，不校验（算清单要先知道供应商，校验又要清单：这里只取供应商那几样）。"""
    file = path()
    doc = (_read(file).get("agents") or {}).get(name) if file.is_file() else None
    return doc if isinstance(doc, dict) else {}


def _fresh(name: str, knobs: KnobsOf) -> Entry:
    picked = knobs(name)
    return Entry(name=name, model=picked.model, effort=picked.effort)


def _parse_entry(name: str, doc: Any, knobs: KnobsOf) -> tuple[Entry | None, str]:
    if not isinstance(doc, dict):
        return None, "要是键值对"
    provider = doc.get("provider", OFFICIAL)
    base_url = doc.get("base_url", "")
    models = doc.get("models") or []
    if not isinstance(provider, str) or not isinstance(base_url, str) \
            or not isinstance(models, list) or not all(isinstance(m, str) for m in models):
        return None, "provider 与 base_url 要是字符串，models 要是字符串列表"
    try:
        provider_of(name, provider, base_url, tuple(models))
    except ValueError as exc:
        return None, f"{exc}（ai4sci agent use {name} --provider … 重选）"
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
    return Entry(name=name, model=model, effort=effort, provider=provider,
                 base_url=base_url if provider == CUSTOM else "",
                 models=tuple(models) if provider == CUSTOM else (), last_check=check), ""


def role_backend(role: str, knobs: KnobsOf = knobs_of) -> str:
    """助理（chat）或执行层（executor）用哪家。"""
    return load(knobs).role(role)


def tuning_for(name: str, knobs: KnobsOf = knobs_of) -> Tuning:
    """这家新对话 / 新会话用什么：文件里记的，没记就是起点；永远是具体值。"""
    return load(knobs).get(name).tuning


def use(name: str, *, roles: tuple[str, ...] = (), provider: str | None = None,
        base_url: str | None = None, models: tuple[str, ...] | None = None,
        model: str | None = None, effort: str | None = None,
        knobs: KnobsOf = knobs_of) -> Entry:
    """换用哪家、换这家的供应商、改它的缺省。换了供应商，没给的模型与深度回到那个供应商的起点
    （DeepSeek 的 key 配不了 Opus）；值先过那个供应商的清单，不在就报错不写。"""
    registry = load(knobs)
    entry = registry.get(name)
    if provider is not None or base_url is not None or models is not None:
        new = provider or entry.provider
        url = entry.base_url if base_url is None else base_url.strip()
        names = entry.models if models is None else tuple(m.strip() for m in models if m.strip())
        picked = provider_of(name, new, url, names).knobs()
        if new != entry.provider or picked.models != knobs(name).models:
            entry.model, entry.effort = picked.model, picked.effort
            entry.last_check = None  # 上次检查的是别的供应商，不作数了
        entry.provider = new
        entry.base_url, entry.models = (url, names) if new == CUSTOM else ("", ())
    else:
        picked = knobs(name)
    if model is not None or effort is not None:
        tuned = Tuning(model=model or entry.model, effort=effort or entry.effort)
        picked.check(tuned)
        entry.model, entry.effort = tuned.model, tuned.effort
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
