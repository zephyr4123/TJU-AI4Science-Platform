"""首页的花费（外层 #256）：从对话每一轮与执行层每次会话的留档里汇总，按天 / 项目 / 模型。

造的是真实的盘面形状：对话在 `<项目>/.ai4sci/chats/<id>/turn-N/`（events.jsonl 是 CLI 原生事件、
trace.jsonl 是框架记的单轮花费），编辑台的对话在 `studio/chats/`，执行层的留档是产出目录下某处的
`executor-<时刻>.jsonl`。
"""

from __future__ import annotations

import json
import math
import os
from datetime import UTC, datetime
from pathlib import Path

import pytest

from framework.chat import scope, spending
from tests.fixtures import spaces

NOW = datetime(2026, 10, 6, 12, 0, tzinfo=UTC)

_CLAUDE_INIT = {"type": "system", "subtype": "init", "model": "claude-opus-5[1m]"}


def _claude(cost: float, read: int = 1000, out: int = 100) -> list[dict]:
    return [_CLAUDE_INIT, {"type": "result", "total_cost_usd": cost, "duration_ms": 1,
                           "usage": {"input_tokens": read, "cache_creation_input_tokens": 0,
                                     "cache_read_input_tokens": 0, "output_tokens": out}}]


def _codex(read: int = 5000, out: int = 50) -> list[dict]:
    return [{"type": "thread.started", "thread_id": "t"},
            {"type": "turn.completed", "usage": {"input_tokens": read, "cached_input_tokens": 0,
                                                 "output_tokens": out}}]


def _lines(path: Path, events: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(e) + "\n" for e in events), encoding="utf-8")


def _at(path: Path, when: datetime) -> None:
    stamp = when.timestamp()
    os.utime(path, (stamp, stamp))


def _turn(chats: Path, chat_id: str, n: int, *, backend: str, model: str, events: list[dict],
          cost: float | None, when: datetime) -> None:
    """一段对话的第 n 轮：meta.json、原生事件、框架记的 done（cost 是这一轮的，None = 报不出）。"""
    conv = chats / chat_id
    conv.mkdir(parents=True, exist_ok=True)
    (conv / "meta.json").write_text(json.dumps({"chat_id": chat_id, "backend": backend,
                                                "model": model}), encoding="utf-8")
    _lines(conv / f"turn-{n}" / "events.jsonl", events)
    _lines(conv / f"turn-{n}" / "trace.jsonl", [{"kind": "done", "cost_usd": cost}])
    _at(conv / f"turn-{n}" / "events.jsonl", when)


@pytest.fixture
def home(tmp_path: Path) -> Path:
    gua = spaces.make_project(tmp_path, "gua", title="复现 GUA")
    ws = spaces.make_workspace(tmp_path, "w", project_id="gua")
    pinn = spaces.make_project(tmp_path, "pinn", title="复现 PINN")
    # 复现 GUA：Claude Code 对话两轮（第 2 轮超时，什么都没报）+ 执行层一次会话 + 一次两个月前的
    _turn(gua.chats, "c1", 1, backend="claude_code", model="opus", events=_claude(1.2),
          cost=0.5, when=datetime(2026, 10, 5, 12, tzinfo=UTC))
    _turn(gua.chats, "c1", 2, backend="claude_code", model="opus", events=[_CLAUDE_INIT],
          cost=None, when=datetime(2026, 10, 5, 13, tzinfo=UTC))
    run_dir = ws.root / "literature" / "1" / "executor" / "3"
    _lines(run_dir / "executor-20261004T120000000000Z.jsonl", _claude(0.25, read=2000, out=200))
    _lines(ws.root / "design" / "1" / "executor" / "executor-20260801T120000000000Z.jsonl",
           _claude(9.0))
    # 复现 PINN：Codex 对话一轮，报不出美元
    _turn(pinn.chats, "c2", 1, backend="codex", model="gpt-6.1-sol", events=_codex(),
          cost=None, when=datetime(2026, 10, 6, 11, tzinfo=UTC))
    # 编辑台的对话
    _turn(scope.studio(tmp_path).chats, "c3", 1, backend="claude_code", model="sonnet",
          events=[{**_CLAUDE_INIT, "model": "claude-sonnet-5"}, *_claude(0.1)[1:]], cost=0.1,
          when=datetime(2026, 10, 6, 9, tzinfo=UTC))
    return tmp_path


def test_records_cover_project_chats_studio_chats_and_executor_sessions(home: Path):
    got = sorted(spending.records(home), key=lambda r: r.at)
    assert [(r.project, r.kind, r.backend) for r in got] == [
        ("gua", "run", "claude_code"), ("gua", "run", "claude_code"),
        ("gua", "chat", "claude_code"), ("gua", "chat", "claude_code"),
        (None, "chat", "claude_code"), ("pinn", "chat", "codex")]
    old, run, first, timed_out, studio, codex = got
    assert old.at == datetime(2026, 8, 1, 12, tzinfo=UTC) and old.cost_usd == 9.0
    assert run.at == datetime(2026, 10, 4, 12, tzinfo=UTC) and run.tokens == 2200
    assert first.cost_usd == 0.5, "续接会话的累计（1.2）不算，用框架减好的单轮花费"
    assert math.isnan(timed_out.cost_usd) and timed_out.tokens is None, "超时没报：未知，不是 0"
    assert studio.model == "sonnet"
    assert math.isnan(codex.cost_usd) and codex.tokens == 5050 and codex.model == "gpt-6.1-sol"


def test_summary_buckets_by_day_project_and_model_and_counts_unknown_dollars(home: Path):
    got = spending.summary(home, days=30, now=NOW, tz=UTC)
    assert got["days"] == 30 and len(got["by_day"]) == 30
    assert got["by_day"][-1]["day"] == "2026-10-06" and got["by_day"][0]["day"] == "2026-09-07"
    today = got["by_day"][-1]
    assert today["cost_usd"] == pytest.approx(0.1) and today["unknown"] == 1
    assert today["tokens"] == 5050 + 1100
    total = got["total"]
    assert total["cost_usd"] == pytest.approx(0.85), "两个月前那次 $9 不在近 30 天里"
    assert total["unknown"] == 2 and total["count"] == 5
    assert [(p["id"], p["title"]) for p in got["by_project"]] == [
        ("gua", "复现 GUA"), (None, "编辑台"), ("pinn", "复现 PINN")]
    assert got["by_project"][2]["cost_usd"] is None, "一次都没报过美元的项目：未知，不是 $0"
    models = {(m["backend_title"], m["model_title"]): m for m in got["by_model"]}
    assert models[("Claude Code", "Opus")]["cost_usd"] == pytest.approx(0.75)
    assert models[("Codex", "GPT-6.1 Sol")]["unknown"] == 1
    assert {k["kind"]: k["count"] for k in got["by_kind"]} == {"chat": 4, "run": 1}


def test_summary_rereads_a_session_only_after_it_changes(home: Path, monkeypatch):
    spending.summary(home, days=30, now=NOW, tz=UTC)
    reads: list[Path] = []
    original = spending._events

    def counted(path: Path) -> list[dict]:
        reads.append(path)
        return original(path)

    monkeypatch.setattr(spending, "_events", counted)
    spending.summary(home, days=30, now=NOW, tz=UTC)
    assert reads == [], "没改过的留档不重读"
    log = next(home.glob("projects/gua/workspaces/w/literature/1/executor/3/*.jsonl"))
    _lines(log, _claude(0.75, read=10, out=10))
    got = spending.summary(home, days=30, now=NOW, tz=UTC)
    assert reads == [log] and got["total"]["cost_usd"] == pytest.approx(1.35)
