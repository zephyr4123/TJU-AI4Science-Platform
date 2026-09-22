"""设置与冷启动自检（纲领 P-25）：按人的两份清单 + 存放，
三项同一种形状「探测 → 报告 → 写 last_check」。

页面「设置」与 `ai4sci check` / `agent check` 的共同读取点：`snapshot()` 读盘不连、
`check()` 真探并记回。
底座（agents.yaml）、算力（computes.yaml）
各自的读写点仍在 `framework/agents.py` 与 `framework/computes.py`，
这里只把它们摆成一张表；存放一项是数据根在哪、可写、余量，没有文件。
自检不过只报告不拒绝保留，用的时候再拒（主人：不设自我感动的坎）。
"""

from __future__ import annotations

import logging
import shutil
from collections.abc import Callable
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from backends import AgentProbe, available_backends, probe
from framework import agents, computes, paths
from framework.agents import KnobsOf
from framework.chat.conversation import Conversation

LOGGER = logging.getLogger("ai4sci.settings")
WHATS = ("all", "agents", "computes", "storage")
# 谁来自检一家：缺省是真适配器的 probe；服务可以注入（测试里不跑真 CLI）
ProbeAgent = Callable[[str], AgentProbe]


def ensure_tuned(conv: Conversation, knobs: KnobsOf = agents.knobs_of) -> Conversation:
    """老对话（升级前记的 `model: null`）读到时按当时的缺省填成具体值并落盘：
    P-25 之后 meta 里不留 None。
    剧本后端（测试）不在 `_BACKENDS` 里，照原样返回。"""
    if (conv.model is None or conv.effort is None) and conv.backend in available_backends():
        picked = agents.tuning_for(conv.backend, knobs)
        LOGGER.info("chat_meta_filled chat_id=%s backend=%s model=%s effort=%s", conv.chat_id,
                    conv.backend, picked.model, picked.effort)
        conv.tune(picked)
    return conv


def agents_table(knobs: KnobsOf = agents.knobs_of) -> dict[str, Any]:
    """底座那一段：两层各用哪家 + 每家一块（产品名、清单、缺省、上次自检）。"""
    registry = agents.load(knobs)
    entries = []
    for name, entry in registry.entries.items():
        picked = knobs(name)
        entries.append({"name": name, "title": entry.title, "model": entry.model,
                        "effort": entry.effort, "models": [asdict(c) for c in picked.models],
                        "efforts": [asdict(c) for c in picked.efforts],
                        "last_check": entry.last_check})
    return {"chat": registry.chat, "executor": registry.executor, "entries": entries}


def computes_table() -> list[dict[str, Any]]:
    registry = computes.load()
    rows = []
    for entry in registry.entries.values():
        params = entry.params
        where = (f"{params.get('user')}@{params.get('host')}:{params.get('port')}"
                 if entry.kind == "ssh" else "本机")
        rows.append({"name": entry.name, "kind": entry.kind, "where": where,
                     "default": entry.name == registry.default, "last_check": entry.last_check})
    return rows


def storage_table(home: Path | None = None) -> dict[str, Any]:
    """存放只看不改：数据根、配置目录、uv 缓存在哪，可写吗，还剩多少。`home` 是服务起时定的数据根；
    终端里就是 `paths.home()`。"""
    home = paths.home() if home is None else Path(home)
    usage = shutil.disk_usage(home)
    return {"home": str(home), "config": str(paths.config_dir()),
            "uv_cache": str(paths.uv_cache_dir()),
            "writable": _writable(home), "free_gb": round(usage.free / 1e9, 1),
            "projects": sum(1 for _ in (home / "projects").glob("*/project.md"))
            if (home / "projects").is_dir() else 0,
            "workspaces": sum(1 for _ in (home / "projects").glob("*/workspaces/*/requirement.md"))
            if (home / "projects").is_dir() else 0}


def _writable(directory: Path) -> bool:
    try:
        marker = directory / f".ai4sci-write-check-{datetime.now(UTC):%Y%m%dT%H%M%S%f}"
        marker.write_text("", encoding="utf-8")
        marker.unlink()
        return True
    except OSError as exc:
        LOGGER.warning("storage_not_writable dir=%s why=%s", directory, exc)
        return False


def snapshot(knobs: KnobsOf = agents.knobs_of, home: Path | None = None) -> dict[str, Any]:
    """页面「设置」那一整份，读盘不探。"""
    return {"agents": agents_table(knobs), "computes": computes_table(),
            "storage": storage_table(home)}


def problems(snap: dict[str, Any] | None = None, knobs: KnobsOf = agents.knobs_of,
             home: Path | None = None) -> list[str]:
    """哪些项没过（给 `GET /health` 的一位与地方栏那个点）：只看在用的两家与每台算力的 last_check、
    存放。
    没检查过不算没过——冷启动第一次打开设置页再检查，不拦人。"""
    snap = snapshot(knobs, home) if snap is None else snap
    found: list[str] = []
    table = snap["agents"]
    used = {table["chat"], table["executor"]}
    for entry in table["entries"]:
        check = entry["last_check"]
        if entry["name"] in used and check and not check.get("ok"):
            found.append(f"agent:{entry['name']}")
    for row in snap["computes"]:
        if row["last_check"] and not row["last_check"].get("ok"):
            found.append(f"compute:{row['name']}")
    if not snap["storage"]["writable"]:
        found.append("storage")
    return found


def check(what: str = "all", name: str | None = None, *, knobs: KnobsOf = agents.knobs_of,
          probe_agent: ProbeAgent = probe, home: Path | None = None) -> dict[str, Any]:
    """真探：底座每家 `probe()`、算力每台 `check()`（记回 last_check），存放现算。返回新的一整份加
    `ok` 与 `failed`。`name` 给了只探那一个。"""
    assert what in WHATS, f"what 只认 {WHATS}，得到 {what!r}"
    failed: list[str] = []
    if what in ("all", "agents"):
        for agent_name in ([name] if name else available_backends()):
            result = probe_agent(agent_name)
            agents.record_check(agent_name, result, knobs)
            LOGGER.info("agent_check name=%s ok=%s version=%s", agent_name, result.ok,
                        result.version)
            if not result.ok:
                failed.append(f"agent:{agent_name}")
    checked: dict[str, dict[str, Any]] = {}
    if what in ("all", "computes"):
        registry = computes.load()
        for compute_name in ([name] if name else list(registry.entries)):
            # 名字不对就是 ComputeNotFound，原样往上抛
            result = computes.instance(compute_name, registry).check()
            # local 不落盘（每次现探），这一次的结果只在这份报告里
            checked[compute_name] = computes.record_check(compute_name, result).last_check or {}
            LOGGER.info("compute_check name=%s ok=%s", compute_name, result.ok)
            if not result.ok:
                failed.append(f"compute:{compute_name}")
    snap = snapshot(knobs, home)
    for row in snap["computes"]:
        if row["name"] in checked:
            row["last_check"] = checked[row["name"]]
    if what in ("all", "storage") and not snap["storage"]["writable"]:
        failed.append("storage")
    return {**snap, "ok": not failed, "failed": failed}


def update_agents(body: dict[str, Any], knobs: KnobsOf = agents.knobs_of,
                  home: Path | None = None) -> dict[str, Any]:
    """页面改「对话用 / 执行用」与每家的缺省：
    `{"chat": name, "executor": name, "agents": {name: {model, effort}}}`，
    给哪些改哪些；值过那家的清单，不在就 ValueError（调用方回 400）。"""
    for role in agents.ROLES:
        picked = body.get(role)
        if picked is not None:
            if not isinstance(picked, str):
                raise ValueError(f"{role} 要是字符串")
            agents.use(picked, roles=(role,), knobs=knobs)
    for name, doc in (body.get("agents") or {}).items():
        if not isinstance(doc, dict):
            raise ValueError(f"agents.{name} 要是键值对")
        model, effort = doc.get("model"), doc.get("effort")
        if (model is not None and not isinstance(model, str)) or \
                (effort is not None and not isinstance(effort, str)):
            raise ValueError(f"agents.{name} 的 model / effort 要是字符串")
        agents.use(str(name), model=model, effort=effort, knobs=knobs)
    return snapshot(knobs, home)
