"""首页的花费（外层 #256）：对话每一轮、执行层每一次会话用掉多少，读的时候从盘上汇总，
按天 / 项目 / 模型。

不新增账本文件：往产出目录写新文件会让已确认的产出变成「之后有改动」，而要的数字都已经在留档里——
- **对话**：`<域>/chats/<id>/turn-N/`。token 与模型问适配器（`backends.read_usage` 认
  events.jsonl 里的原生事件，框架不解析 CLI 的事件，端口方向）；美元取框架自己记的 trace.jsonl
  末尾那条 done / error（Claude Code 续接的会话报的是累计，那里已经减成单轮）；事件里没写模型的
  用对话 meta 的；时刻取 events.jsonl 最后写入的时间。
- **执行层**：项目里每个工作区七个阶段目录下的 `executor-<时刻>.jsonl`（两家适配器同名留档），
  token、美元、模型都问适配器，时刻取文件名里的。

美元报不出（Codex 用订阅登录、超时被杀）记 NaN：汇总时不算 0，另数「几次未知」；一次都没报过的那一格
是 None。Claude Code 报的是按 API 价折算的美元，订阅账号不是实扣——页面写「折算」。
留档按（改动时间、大小）缓存：没改过的不重读。
"""

from __future__ import annotations

import json
import logging
import math
import os
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta, tzinfo
from pathlib import Path
from typing import Any

from backends import TITLES, BackendNotFound, read_usage
from framework import agents
from framework.chat import scope
from framework.workspace import project as project_mod

LOGGER = logging.getLogger("ai4sci.spending")

KINDS = {"chat": "对话", "run": "运行"}
STUDIO_TITLE = "编辑台"
# 阶段目录里往下找执行层留档时整段跳过的：环境、git 对象库、缓存（几千个文件，没有留档）
_SKIPPED = frozenset({".venv", ".git", "__pycache__", "node_modules"})
_STAMP = "%Y%m%dT%H%M%S%fZ"


@dataclass(frozen=True)
class Spend:
    """一次调用：哪个项目（None 是编辑台）、对话还是运行、哪家哪个模型、几时、多少美元与 token。
    `cost_usd` 报不出是 NaN；`tokens`（读进去的 + 写出来的）不知道是 None。"""

    at: datetime
    project: str | None
    kind: str
    backend: str
    model: str | None
    cost_usd: float
    tokens: int | None


# 一份留档 → 它算出来的那次调用；键是文件，值带（改动时间、大小）
_SEEN: dict[Path, tuple[tuple[int, int], Spend | None]] = {}


def records(home: Path) -> list[Spend]:
    """数据根下全部的调用：各项目的对话与执行层会话、编辑台的对话。"""
    found: list[Spend | None] = []
    for proj in project_mod.list_projects(project_mod.projects_root(home)):
        found += [_cached(events, lambda p, pid=proj.id: _turn(p, pid))
                  for events in _turns(proj.chats)]
        for ws in proj.workspaces():
            for stage_dir in ws.stage_dirs():
                found += [_cached(log, lambda p, pid=proj.id: _session(p, pid))
                          for log in _executor_logs(stage_dir)]
    found += [_cached(events, lambda p: _turn(p, None))
              for events in _turns(scope.studio(home).chats)]
    return [r for r in found if r is not None]


def summary(home: Path, *, days: int, now: datetime | None = None,
            tz: tzinfo | None = None) -> dict[str, Any]:
    """近 `days` 天（含今天，按 `tz` 的日历，缺省本机时区）：合计、按天（每天一格，没有的是 0）、
    按项目、按模型、按对话 / 运行。每一格：折算美元（只加报了的；一次都没报过是 None）、几次未知、
    token、几次。"""
    assert days > 0, f"days 要是正数，得到 {days!r}"
    zone = tz or datetime.now().astimezone().tzinfo
    today = (now or datetime.now(UTC)).astimezone(zone).date()
    first = today - timedelta(days=days - 1)
    picked = [r for r in records(home) if first <= r.at.astimezone(zone).date() <= today]
    titles = {p.id: p.title() for p in project_mod.list_projects(project_mod.projects_root(home))}
    by_day = {first + timedelta(days=i): [] for i in range(days)}
    for r in picked:
        by_day[r.at.astimezone(zone).date()].append(r)
    return {
        "days": days,
        "total": _cell(picked),
        "by_day": [{"day": d.isoformat(), **_cell(rs, zero=True)}
                   for d, rs in sorted(by_day.items())],
        "by_project": _ranked(_group(picked, lambda r: r.project), lambda pid: {
            "id": pid, "title": STUDIO_TITLE if pid is None else titles.get(pid, pid)}),
        "by_model": _ranked(_group(picked, lambda r: (r.backend, r.model)), lambda key: {
            "backend": key[0], "model": key[1], "backend_title": TITLES.get(key[0], key[0]),
            "model_title": _model_title(*key)}),
        "by_kind": [{"kind": k, "title": KINDS[k], **_cell([r for r in picked if r.kind == k])}
                    for k in KINDS],
    }


# ── 汇总 ─────────────────────────────────────────────────────────────────
def _cell(rows: list[Spend], *, zero: bool = False) -> dict[str, Any]:
    """一格：报了的美元加起来（一次都没报过：按天那一列是 0——那天什么都没花或都没报，几次未知另写；
    其余是 None）、几次未知、token（不知道的不加）、几次。"""
    known = [r.cost_usd for r in rows if not math.isnan(r.cost_usd)]
    cost = sum(known) if known else (0.0 if zero else None)
    return {"cost_usd": cost, "unknown": len(rows) - len(known),
            "tokens": sum(r.tokens for r in rows if r.tokens is not None), "count": len(rows)}


def _group(rows: Iterable[Spend], key: Callable[[Spend], Any]) -> dict[Any, list[Spend]]:
    groups: dict[Any, list[Spend]] = {}
    for r in rows:
        groups.setdefault(key(r), []).append(r)
    return groups


def _ranked(groups: dict[Any, list[Spend]], head: Callable[[Any], dict[str, Any]]) -> list[dict]:
    """按折算美元从多到少，一样（或都未知）再按 token；美元未知的排在报了的后面。"""
    rows = [{**head(k), **_cell(rs)} for k, rs in groups.items()]
    return sorted(rows, key=lambda c: (c["cost_usd"] is None, -(c["cost_usd"] or 0.0),
                                       -c["tokens"]))


def _model_title(backend: str, model: str | None) -> str:
    """清单上的模型写清单上的名（Opus、GPT-6.1 Sol）；不在清单上的照原样；没记的说没记。"""
    if model is None:
        return "未记录模型"
    try:
        return next((c.label for c in agents.knobs_of(backend).models if c.id == model), model)
    except BackendNotFound:
        return model


# ── 读留档 ───────────────────────────────────────────────────────────────
def _turns(chats: Path) -> list[Path]:
    """一个域里每段对话、每一轮的原生事件：`<chats>/<id>/turn-N/events.jsonl`。"""
    return sorted(chats.glob("*/turn-*/events.jsonl")) if chats.is_dir() else []


def _executor_logs(stage_dir: Path) -> list[Path]:
    """一个阶段目录往下的执行层留档；环境与缓存目录整段不进。"""
    found = []
    for directory, dirs, files in os.walk(stage_dir):
        dirs[:] = [d for d in dirs if d not in _SKIPPED]
        found += [Path(directory) / f for f in files
                  if f.startswith("executor-") and f.endswith(".jsonl")]
    return sorted(found)


def _cached(path: Path, read: Callable[[Path], Spend | None]) -> Spend | None:
    """（改动时间、大小）没变就用上次算的；对话那一轮还要看 trace.jsonl，它跟着 events.jsonl
    一起写。"""
    stat = path.stat()
    stamp = (stat.st_mtime_ns, stat.st_size)
    hit = _SEEN.get(path)
    if hit is not None and hit[0] == stamp:
        return hit[1]
    got = read(path)
    _SEEN[path] = (stamp, got)
    return got


def _turn(events_path: Path, project: str | None) -> Spend | None:
    """对话的一轮。框架还没记下 done / error（这一轮还在跑）就先不算。"""
    turn_dir = events_path.parent
    closing = [e for e in _events(turn_dir / "trace.jsonl") if e.get("kind") in ("done", "error")]
    if not closing:
        return None
    meta = json.loads((turn_dir.parent / "meta.json").read_text(encoding="utf-8"))
    cost = closing[-1].get("cost_usd")
    found = read_usage(_events(events_path))
    usage = found[1] if found else None
    return Spend(at=datetime.fromtimestamp(events_path.stat().st_mtime, UTC), project=project,
                 kind="chat", backend=meta["backend"],
                 model=(usage.model if usage and usage.model else meta.get("model")),
                 cost_usd=math.nan if cost is None else float(cost),
                 tokens=usage.input_tokens + usage.output_tokens if usage else None)


def _session(log: Path, project: str | None) -> Spend | None:
    """执行层的一次会话；事件里认不出是哪家、也没有用量（超时被杀）就不算——花了多少不知道，
    也不知道是哪家，记不进任何一格。"""
    found = read_usage(_events(log))
    if found is None:
        LOGGER.info("spending_session_unreadable log=%s", log)
        return None
    backend, usage = found
    try:
        at = datetime.strptime(log.stem.removeprefix("executor-"), _STAMP).replace(tzinfo=UTC)
    except ValueError:
        at = datetime.fromtimestamp(log.stat().st_mtime, UTC)
    return Spend(at=at, project=project, kind="run", backend=backend, model=usage.model,
                 cost_usd=usage.cost_usd, tokens=usage.input_tokens + usage.output_tokens)


def _events(path: Path) -> list[dict]:
    """一份 JSONL：一行一个事件；坏行（写到一半的最后一行、CLI 吐的杂行）记一条日志跳过。"""
    if not path.is_file():
        return []
    events = []
    for n, line in enumerate(path.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
        if not line.strip():
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            LOGGER.info("spending_bad_line path=%s line=%d", path, n)
            continue
        if isinstance(event, dict):
            events.append(event)
    return events

