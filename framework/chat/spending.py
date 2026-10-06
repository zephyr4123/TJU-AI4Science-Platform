"""首页的花费（外层 #256）：对话每一轮、执行层每一次会话用掉多少，读的时候从盘上汇总，
按天 / 项目 / 模型 / 会话，外加两家的定价表。

不新增账本文件：往产出目录写新文件会让已确认的产出变成「之后有改动」，而要的数字都已经在留档里——
- **对话**：`<域>/chats/<id>/turn-N/`。token 与模型问适配器（`backends.read_usage` 认
  events.jsonl 里的原生事件，框架不解析 CLI 的事件，端口方向）；美元取框架自己记的 trace.jsonl
  末尾那条 done / error（Claude Code 续接的会话报的是累计，那里已经减成单轮）；事件里没写模型的
  用对话 meta 的；时刻取 events.jsonl 最后写入的时间。一段对话是一段会话，名字是人说的第一句。
- **执行层**：项目里每个工作区每次产出的目录下的 `executor-<时刻>.jsonl`（两家适配器同名留档），
  token、美元、模型都问适配器，留档里没记模型的用产出 meta 记的；时刻取文件名里的。一次产出是一段
  会话（文献检索几跳就是几份留档），名字是能力名。

成本：CLI 报了用报的；报不出（Codex 用订阅登录）照这家的定价表（`backends.prices`）折算；模型没记、
表里没有、或这一轮超时被杀连用量都没有，记 NaN——汇总时不算 0，另数「几次未知」，一次都没算出的那一格
是 None。两种都是按 API 公开价折算，订阅账号不是实扣——页面写「折算」。
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
from functools import partial
from pathlib import Path
from typing import Any

from backends import TITLES, BackendNotFound, Usage, available_backends, prices, read_usage
from framework import agents
from framework.chat import conversation, scope
from framework.contracts.output import Meta
from framework.workspace import outputs
from framework.workspace import project as project_mod

LOGGER = logging.getLogger("ai4sci.spending")

KINDS = {"chat": "对话", "run": "运行"}
STUDIO = "studio"
STUDIO_TITLE = "编辑台"
# 会话清单露几段（最近的在前）：再往前的翻项目页看
SESSIONS_SHOWN = 50
# 产出目录里往下找执行层留档时整段跳过的：环境、git 对象库、缓存（几千个文件，没有留档）
_SKIPPED = frozenset({".venv", ".git", "__pycache__", "node_modules"})
_STAMP = "%Y%m%dT%H%M%S%fZ"


@dataclass(frozen=True)
class Spend:
    """一次调用：哪个项目（None 是编辑台）、哪个工作区（运行才有）、哪段会话（`session` 是
    「项目 / 对话」或「项目 / 工作区 / 产出」，`title` 是它的名：人说的第一句——还没有是 None——
    或能力名）、对话还是运行、哪家哪个模型、几时、成本（报的或折算的，都没有是 NaN）与用量
    （不知道是 None）。"""

    at: datetime
    project: str | None
    workspace: str | None
    session: str
    title: str | None
    kind: str
    backend: str
    model: str | None
    cost_usd: float
    usage: Usage | None

    @property
    def tokens(self) -> int | None:
        """读进去的 + 写出来的。"""
        return None if self.usage is None else self.usage.input_tokens + self.usage.output_tokens


# 一份留档 → 它算出来的那次调用；键是文件，值带（改动时间、大小）
_SEEN: dict[Path, tuple[tuple[int, int], Spend | None]] = {}


def records(home: Path) -> list[Spend]:
    """数据根下全部的调用：各项目的对话与每次产出的执行层会话、编辑台的对话。"""
    found: list[Spend | None] = []
    for proj in project_mod.list_projects(project_mod.projects_root(home)):
        found += [_cached(events, partial(_turn, project=proj.id)) for events in _turns(proj.chats)]
        for ws in proj.workspaces():
            for directory, meta in outputs.list_outputs(ws):
                read = partial(_run, project=proj.id, workspace=ws.id, meta=meta)
                found += [_cached(log, read) for log in _executor_logs(directory)]
    found += [_cached(events, partial(_turn, project=None))
              for events in _turns(scope.studio(home).chats)]
    return [r for r in found if r is not None]


def summary(home: Path, *, days: int, now: datetime | None = None,
            tz: tzinfo | None = None) -> dict[str, Any]:
    """近 `days` 天（含今天，按 `tz` 的日历，缺省本机时区）：合计、按天（每天一格，没有的是 0）、
    按项目、按模型、按对话 / 运行、最近的会话，外加两家的定价表。每一格：折算美元（只加算得出的；
    一次都没算出是 None）、几次未知、token（读进去的、其中命中缓存的）、几次。"""
    assert days > 0, f"days 要是正数，得到 {days!r}"
    zone = tz or datetime.now().astimezone().tzinfo
    today = (now or datetime.now(UTC)).astimezone(zone).date()
    first = today - timedelta(days=days - 1)
    picked = [r for r in records(home) if first <= r.at.astimezone(zone).date() <= today]
    projects = project_mod.list_projects(project_mod.projects_root(home))
    titles = {p.id: p.title() for p in projects}
    spaces = {(p.id, ws.id): ws.title() for p in projects for ws in p.workspaces()}
    by_day = {first + timedelta(days=i): [] for i in range(days)}
    for r in picked:
        by_day[r.at.astimezone(zone).date()].append(r)
    project_title = lambda pid: STUDIO_TITLE if pid is None else titles.get(pid, pid)  # noqa: E731
    return {
        "days": days,
        "total": _cell(picked),
        "by_day": [{"day": d.isoformat(), **_cell(rs, zero=True)}
                   for d, rs in sorted(by_day.items())],
        "by_project": _ranked(_group(picked, lambda r: r.project), lambda pid: {
            "id": pid, "title": project_title(pid)}),
        "by_model": _ranked(_group(picked, lambda r: (r.backend, r.model)), lambda key: {
            "backend": key[0], "model": key[1], "backend_title": TITLES.get(key[0], key[0]),
            "model_title": _model_title(*key)}),
        "by_kind": [{"kind": k, "title": KINDS[k], **_cell([r for r in picked if r.kind == k])}
                    for k in KINDS],
        "sessions": _sessions(picked, project_title, spaces),
        "pricing": [{"backend": b, "backend_title": TITLES.get(b, b), "model": m,
                     "model_title": p.title, "input": p.input, "cached": p.cached,
                     "output": p.output}
                    for b in available_backends() for m, p in prices(b).items()],
    }


# ── 汇总 ─────────────────────────────────────────────────────────────────
def _cell(rows: list[Spend], *, zero: bool = False) -> dict[str, Any]:
    """一格：算得出的美元加起来（一次都没算出：按天那一列是 0——那天什么都没花或都没算出，
    几次未知另写；其余是 None）、几次未知、token（不知道的不加；另记读进去的与其中命中缓存的，
    缓存命中率用）、几次。"""
    known = [r.cost_usd for r in rows if not math.isnan(r.cost_usd)]
    cost = sum(known) if known else (0.0 if zero else None)
    used = [r.usage for r in rows if r.usage is not None]
    return {"cost_usd": cost, "unknown": len(rows) - len(known),
            "tokens": sum(u.input_tokens + u.output_tokens for u in used),
            "input_tokens": sum(u.input_tokens for u in used),
            "cached_tokens": sum(u.cached_tokens for u in used), "count": len(rows)}


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


def _sessions(rows: list[Spend], project_title: Callable[[str | None], str],
              spaces: dict[tuple[str, str], str]) -> list[dict[str, Any]]:
    """按会话并：最近一次调用的在前，露 `SESSIONS_SHOWN` 段；模型写最后那次用的（对话中途能换）。"""
    heads = []
    for key, rs in _group(rows, lambda r: r.session).items():
        last = max(rs, key=lambda r: r.at)
        heads.append({"key": key, "kind": last.kind, "title": last.title,
                      "project": last.project, "project_title": project_title(last.project),
                      "workspace": last.workspace,
                      "workspace_title": spaces.get((last.project, last.workspace))
                      if last.workspace else None,
                      "at": last.at.isoformat(), "backend_title": TITLES.get(last.backend,
                                                                             last.backend),
                      "model_title": _model_title(last.backend, last.model), **_cell(rs)})
    return sorted(heads, key=lambda h: h["at"], reverse=True)[:SESSIONS_SHOWN]


def _model_title(backend: str, model: str | None) -> str:
    """定价表上有的写表上的名（Opus 5、GPT-6.1 Sol），清单上的别名写清单上的名（Opus）；
    都不是的照原样；没记的说没记。"""
    if model is None:
        return "未记录模型"
    try:
        priced = prices(backend).get(model)
        listed = (c.label for c in agents.knobs_of(backend).models if c.id == model)
    except BackendNotFound:
        return model
    return priced.title if priced else next(listed, model)


def _cost(backend: str, model: str | None, usage: Usage | None, reported: float) -> float:
    """CLI 报了用报的；报不出照这家的定价表折算；模型没记、表里没有、连用量都没有：NaN。"""
    if not math.isnan(reported) or usage is None or model is None:
        return reported
    try:
        price = prices(backend).get(model)
    except BackendNotFound:
        return reported
    return price.cost(usage) if price else reported


# ── 读留档 ───────────────────────────────────────────────────────────────
def _turns(chats: Path) -> list[Path]:
    """一个域里每段对话、每一轮的原生事件：`<chats>/<id>/turn-N/events.jsonl`。"""
    return sorted(chats.glob("*/turn-*/events.jsonl")) if chats.is_dir() else []


def _executor_logs(output_dir: Path) -> list[Path]:
    """一次产出目录往下的执行层留档；环境与缓存目录整段不进。"""
    found = []
    for directory, dirs, files in os.walk(output_dir):
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


def _turn(events_path: Path, *, project: str | None) -> Spend | None:
    """对话的一轮。框架还没记下 done / error（这一轮还在跑）就先不算。"""
    turn_dir = events_path.parent
    closing = [e for e in _events(turn_dir / "trace.jsonl") if e.get("kind") in ("done", "error")]
    if not closing:
        return None
    conv = conversation.load_conversation(turn_dir.parent.parent, turn_dir.parent.name)
    reported = closing[-1].get("cost_usd")
    found = read_usage(_events(events_path))
    usage = found[1] if found else None
    model = usage.model if usage and usage.model else conv.model
    return Spend(at=datetime.fromtimestamp(events_path.stat().st_mtime, UTC), project=project,
                 workspace=None, session=f"{project or STUDIO}/{conv.chat_id}",
                 title=conversation.title(conv), kind="chat", backend=conv.backend, model=model,
                 cost_usd=_cost(conv.backend, model, usage,
                                math.nan if reported is None else float(reported)),
                 usage=usage)


def _run(log: Path, *, project: str, workspace: str, meta: Meta) -> Spend | None:
    """执行层的一次会话；事件里认不出是哪家、也没有用量（超时被杀）就不算——花了多少不知道，
    也不知道是哪家，记不进任何一格。留档里没记模型（Codex 老留档）用产出 meta 记的。"""
    found = read_usage(_events(log))
    if found is None:
        LOGGER.info("spending_session_unreadable log=%s", log)
        return None
    backend, usage = found
    agent = meta.agent or {}
    model = usage.model or (agent.get("model") if agent.get("backend") == backend else None)
    try:
        at = datetime.strptime(log.stem.removeprefix("executor-"), _STAMP).replace(tzinfo=UTC)
    except ValueError:
        at = datetime.fromtimestamp(log.stat().st_mtime, UTC)
    return Spend(at=at, project=project, workspace=workspace,
                 session=f"{project}/{workspace}/{meta.id}", title=meta.title, kind="run",
                 backend=backend, model=model,
                 cost_usd=_cost(backend, model, usage, usage.cost_usd), usage=usage)


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

