"""设置与冷启动自检（纲领 P-25）：按人的两份清单 + 存放，
三项同一种形状「探测 → 报告 → 写 last_check」。

页面「设置」与 `ai4sci check` / `agent check` 的共同读取点：`snapshot()` 读盘不连、
`check()` 真探并记回。整份里的 `assistant` 是助理那家现在能不能说话（`assistant()`，外层 #282）：
页面只在缺 key 时弹「填 DeepSeek 的 key」。
底座（agents.yaml）、算力（computes.yaml）
各自的读写点仍在 `framework/agents.py` 与 `framework/computes.py`，
这里只把它们摆成一张表；存放一项是平台的家在哪、每块多大、可写、余量，没有文件。
自检不过只报告不拒绝保留，用的时候再拒（主人：不设自我感动的坎）。
"""

from __future__ import annotations

import logging
import os
import re
import shutil
from collections.abc import Callable
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from backends import CUSTOM, LOGIN_ITEM, AgentProbe, available_backends, providers
from framework import agents, computes, keys, paths
from framework.agents import KnobsOf
from framework.chat.conversation import Conversation

LOGGER = logging.getLogger("ai4sci.settings")
WHATS = ("all", "agents", "computes", "storage")
# 谁来自检一家：缺省是真适配器的 probe；服务可以注入（测试里不跑真 CLI）
ProbeAgent = Callable[[str], AgentProbe]
# 助理那家的四种状态（外层 #282）：页面只在 needs_key 时弹 key 框，cannot_talk 只显示原因，
# unchecked 时页面在后台探一次
READY, NEEDS_KEY, CANNOT_TALK, UNCHECKED = "ready", "needs_key", "cannot_talk", "unchecked"
# 说话那一句被 API 拒的两类。CLI 只给原文（2026-10-07 实测一把假 key）：Claude Code「API Error: 401
# Authentication Fails …」，Codex「unexpected status 401 Unauthorized: …」；DeepSeek 余额不够是 402
# Insufficient Balance（api-docs.deepseek.com 的错误码表）
_KEY_REJECTED = re.compile(r"\b401\b|unauthori[sz]ed|authenticat|invalid api key", re.IGNORECASE)
_NO_BALANCE = re.compile(r"\b402\b|insufficient balance|余额不足", re.IGNORECASE)


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
    """底座那一段：两层各用哪家 + 每家一块（产品名、用谁的模型与它的清单、缺省、上次自检），外加
    这家能接的供应商目录（外层 #266：名、要不要 key、key 的名字、实测过没有）。"""
    registry = agents.load(knobs)
    entries = []
    for name, entry in registry.entries.items():
        picked = knobs(name)
        entries.append({"name": name, "title": entry.title, "provider": entry.provider,
                        "base_url": entry.base_url, "custom_models": list(entry.models),
                        "providers": _providers(name), "login": agents.login_hint(name),
                        "model": entry.model, "effort": entry.effort,
                        "models": [asdict(c) for c in picked.models],
                        "efforts": [asdict(c) for c in picked.efforts],
                        "last_check": entry.last_check})
    return {"chat": registry.chat, "executor": registry.executor, "entries": entries}


def _providers(name: str) -> list[dict[str, Any]]:
    """一家的供应商目录，最后一项是自定义（地址与模型名人填）。剧本后端（测试）没有目录。"""
    if name not in available_backends():
        return []
    rows = [{"id": p.id, "title": p.title, "key": p.key, "base_url": p.base_url,
             "tested": p.tested, "web_search": p.web_search} for p in providers(name).values()]
    return [*rows, {"id": CUSTOM, "title": "自定义", "key": f"{CUSTOM}.{name}", "base_url": "",
                    "tested": "", "web_search": None}]


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


# 家里的几块（页面「存放」照这个顺序念，外层 #263）：给人看的名字、包含家里哪些东西
PARTS = (("项目", ("projects",)), ("编辑台", ("studio",)),
         ("会话与登录", tuple(available_backends())), ("依赖缓存", (paths.UV_CACHE_PARTS[0],)),
         ("设置与 key", (paths.AGENTS_FILENAME, paths.COMPUTES_FILENAME, paths.KEYS_FILENAME)))


def storage_table(home: Path | None = None) -> dict[str, Any]:
    """存放：平台的家在哪、可写吗、还剩多少、清除认不认它（有没有标记）。`home` 是服务起时定的家；
    终端里就是 `paths.home()`。每块多大不在这里（`storage_sizes`）。"""
    home = paths.home() if home is None else Path(home)
    usage = shutil.disk_usage(home)
    projects = home / "projects"
    return {"home": str(home), "resettable": (home / paths.MARKER_NAME).is_file(),
            # 在仓库里跑还是装的包在跑、出厂件从哪读、页面有没有构建（外层 #138）
            "mode": "source" if paths.from_source() else "package",
            "shipped": str(paths.shipped_home()),
            "ui": str(paths.ui_dir()), "ui_built": (paths.ui_dir() / "index.html").is_file(),
            "writable": _writable(home), "free_gb": round(usage.free / 1e9, 1),
            "projects": sum(1 for _ in projects.glob("*/project.md")) if projects.is_dir() else 0,
            "workspaces": sum(1 for _ in projects.glob("*/workspaces/*/requirement.md"))
            if projects.is_dir() else 0}


def storage_sizes(home: Path | None = None) -> list[dict[str, Any]]:
    """家里每块占多大。要走遍整棵树（开发用的家 3.5 GB、7 万个文件走一遍 1 秒多），所以不进
    `snapshot`——不然每打开一次设置、每改一项都要等它；页面在「存放」那页打开时单独取
    （外层 #268）。"""
    home = paths.home() if home is None else Path(home)
    return [{"label": label, "bytes": sum(_size(home / n) for n in names)}
            for label, names in PARTS]


def _size(path: Path) -> int:
    """一个文件或一整棵目录占多少字节（不跟软链）；不在就是 0。"""
    if path.is_symlink() or path.is_file():
        return path.lstat().st_size
    total = 0
    for root, _, files in os.walk(path):
        for name in files:
            try:
                total += (Path(root) / name).lstat().st_size
            except OSError:
                continue  # 数着数着被删了（缓存在写）：少算这一个，不拦页面
    return total


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
    """页面「设置」那一整份，读盘不探。key 只给末四位（外层 #265）。"""
    table = agents_table(knobs)
    return {"agents": table, "assistant": assistant(table), "computes": computes_table(),
            "storage": storage_table(home), "keys": keys.masked()}


def assistant(table: dict[str, Any]) -> dict[str, Any]:
    """助理那家（对话用）现在能不能说话，只看它的 last_check（外层 #282）：算力、存放、执行层那家
    没过都不算——不然 AutoDL 关机也弹「填 key」。没检查过是 unchecked；第一个没过的那项是登录，或说话
    时 API 以 401 拒了 key，是 needs_key；别的没过（余额不足、没回话、没装）是 cannot_talk，原因照
    自检的原话，DeepSeek 余额不足换成一句去哪充值。"""
    name = table["chat"]
    entry = next(e for e in table["entries"] if e["name"] == name)
    check = entry["last_check"]
    row = {"agent": name, "provider": entry["provider"], "state": UNCHECKED, "reason": None,
           "checked_at": None}
    if not check:
        return row
    row["checked_at"] = check.get("at")
    if check.get("ok"):
        return {**row, "state": READY}
    failed = next((i for i in check.get("items") or () if not i.get("ok")), {})
    item, note = str(failed.get("name") or ""), str(failed.get("note") or "没有结果")
    title = next((p["title"] for p in entry["providers"] if p["id"] == entry["provider"]),
                 entry["provider"])
    if item == LOGIN_ITEM:
        return {**row, "state": NEEDS_KEY, "reason": note}
    if _KEY_REJECTED.search(note):
        return {**row, "state": NEEDS_KEY, "reason": f"{title} 不认这把 key：换一把再试"}
    if entry["provider"] == agents.QUICKSTART_PROVIDER and _NO_BALANCE.search(note):
        note = f"{title} 余额不足：去 {agents.QUICKSTART_SITE} 充值"
    return {**row, "state": CANNOT_TALK, "reason": note}


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
          probe_agent: ProbeAgent = agents.probe, home: Path | None = None) -> dict[str, Any]:
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
    """页面改「对话用 / 执行用」与每家的供应商与缺省：
    `{"chat": name, "executor": name, "agents": {name: {provider?, base_url?, models?, model?,
    effort?}}}`，给哪些改哪些；换了供应商没给的模型回到它的起点；值过那家那个供应商的清单，
    不在就 ValueError（调用方回 400）。"""
    for role in agents.ROLES:
        picked = body.get(role)
        if picked is not None:
            if not isinstance(picked, str):
                raise ValueError(f"{role} 要是字符串")
            agents.use(picked, roles=(role,), knobs=knobs)
    for name, doc in (body.get("agents") or {}).items():
        if not isinstance(doc, dict):
            raise ValueError(f"agents.{name} 要是键值对")
        texts = {k: doc.get(k) for k in ("provider", "base_url", "model", "effort")}
        if any(v is not None and not isinstance(v, str) for v in texts.values()):
            raise ValueError(f"agents.{name} 的 provider / base_url / model / effort 要是字符串")
        models = doc.get("models")
        if models is not None and (not isinstance(models, list)
                                   or not all(isinstance(m, str) for m in models)):
            raise ValueError(f"agents.{name}.models 要是字符串列表")
        agents.use(str(name), provider=texts["provider"], base_url=texts["base_url"],
                   models=None if models is None else tuple(models), model=texts["model"],
                   effort=texts["effort"], knobs=knobs)
    return snapshot(knobs, home)
