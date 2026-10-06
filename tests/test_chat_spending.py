"""首页的花费（外层 #256）：从对话每一轮与执行层每次会话的留档里汇总，按天 / 项目 / 模型 / 会话。

造的是真实的盘面形状：对话在 `<项目>/.ai4sci/chats/<id>/turn-N/`（events.jsonl 是 CLI 原生事件、
trace.jsonl 是框架记的单轮花费），编辑台的对话在 `studio/chats/`，执行层的留档在产出目录下某处的
`executor-<时刻>.jsonl`，产出的 meta.yaml 记着是哪个能力、执行层用的哪家哪个模型。
"""

from __future__ import annotations

import json
import math
import os
from datetime import UTC, datetime
from pathlib import Path

import pytest

from framework.chat import scope, spending
from framework.workspace import outputs
from framework.workspace.root import Workspace
from tests.fixtures import spaces

NOW = datetime(2026, 10, 6, 12, 0, tzinfo=UTC)

_CLAUDE_INIT = {"type": "system", "subtype": "init", "model": "claude-opus-5[1m]"}


def _claude(cost: float, read: int = 1000, out: int = 100) -> list[dict]:
    return [_CLAUDE_INIT, {"type": "result", "total_cost_usd": cost, "duration_ms": 1,
                           "usage": {"input_tokens": read, "cache_creation_input_tokens": 0,
                                     "cache_read_input_tokens": 0, "output_tokens": out}}]


def _codex(read: int = 5000, cached: int = 0, out: int = 50) -> list[dict]:
    return [{"type": "thread.started", "thread_id": "t"},
            {"type": "turn.completed", "usage": {"input_tokens": read,
                                                 "cached_input_tokens": cached,
                                                 "output_tokens": out}}]


def _lines(path: Path, events: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(e) + "\n" for e in events), encoding="utf-8")


def _at(path: Path, when: datetime) -> None:
    stamp = when.timestamp()
    os.utime(path, (stamp, stamp))


def _turn(chats: Path, chat_id: str, n: int, *, backend: str, model: str, events: list[dict],
          cost: float | None, when: datetime, said: str | None = None) -> None:
    """一段对话的第 n 轮：meta.json、人说的话、原生事件、框架记的 done（cost 是这一轮的，
    None = 报不出）。"""
    conv = chats / chat_id
    conv.mkdir(parents=True, exist_ok=True)
    (conv / "meta.json").write_text(json.dumps({
        "chat_id": chat_id, "backend": backend, "cwd": str(chats), "created_at": when.isoformat(),
        "model": model}), encoding="utf-8")
    if said:
        (conv / f"turn-{n}").mkdir(parents=True, exist_ok=True)
        (conv / f"turn-{n}" / "message.md").write_text(said + "\n", encoding="utf-8")
    _lines(conv / f"turn-{n}" / "events.jsonl", events)
    _lines(conv / f"turn-{n}" / "trace.jsonl", [{"kind": "done", "cost_usd": cost}])
    _at(conv / f"turn-{n}" / "events.jsonl", when)


def _run(ws: Workspace, stage: str, title: str, stamp: str, events: list[dict], *,
         agent: dict | None = None) -> Path:
    """一次产出：能力开的目录与 meta.yaml，底下某处执行层的一份留档。"""
    directory, _ = outputs.open_output(ws, stage, title=title, by="cap", inputs=[], params={},
                                       flow=None, step=None, requirement=None, chat_id=None,
                                       agent=agent)
    log = directory / "executor" / "hop-0" / f"executor-{stamp}.jsonl"
    _lines(log, events)
    return log


@pytest.fixture
def home(tmp_path: Path) -> Path:
    gua = spaces.make_project(tmp_path, "gua", title="复现 GUA")
    ws = spaces.make_workspace(tmp_path, "w", project_id="gua", title="第一张表")
    pinn = spaces.make_project(tmp_path, "pinn", title="复现 PINN")
    # 复现 GUA：Claude Code 对话两轮（第 2 轮超时，什么都没报）；执行层三次：一次文献检索、
    # 一次两个月前的设计、一次老版本的 Codex 实验（留档里没记模型，产出的 meta 记着）
    _turn(gua.chats, "c1", 1, backend="claude_code", model="opus", events=_claude(1.2),
          cost=0.5, when=datetime(2026, 10, 5, 12, tzinfo=UTC),
          said="复现论文的第一张表\n细节见附件")
    _turn(gua.chats, "c1", 2, backend="claude_code", model="opus", events=[_CLAUDE_INIT],
          cost=None, when=datetime(2026, 10, 5, 13, tzinfo=UTC))
    _run(ws, "literature", "文献检索", "20261004T120000000000Z", _claude(0.25, read=2000, out=200))
    _run(ws, "design", "实验设计", "20260801T120000000000Z", _claude(9.0))
    _run(ws, "experiment", "自动实验", "20261003T120000000000Z",
         _codex(read=100_000, cached=80_000, out=1000),
         agent={"backend": "codex", "model": "gpt-5.6-terra", "effort": "medium"})
    # 复现 PINN：Codex 对话一轮，订阅报不出成本
    _turn(pinn.chats, "c2", 1, backend="codex", model="gpt-6.1-sol", events=_codex(),
          cost=None, when=datetime(2026, 10, 6, 11, tzinfo=UTC))
    # 编辑台的对话
    _turn(scope.studio(tmp_path).chats, "c3", 1, backend="claude_code", model="sonnet",
          events=[{**_CLAUDE_INIT, "model": "claude-sonnet-5"}, *_claude(0.1)[1:]], cost=0.1,
          when=datetime(2026, 10, 6, 9, tzinfo=UTC))
    return tmp_path


# 照定价表折算（美元 / 百万 token）：GPT-6.1 Sol 输入 2、输出 10；
# GPT-5.6 Terra 输入 2、缓存 0.2、输出 12
_C2 = (5000 * 2 + 50 * 10) / 1e6
_EXPERIMENT = (20_000 * 2 + 80_000 * 0.2 + 1000 * 12) / 1e6


def test_records_cover_chats_studio_and_every_output_s_executor_sessions(home: Path):
    got = sorted(spending.records(home), key=lambda r: r.at)
    assert [(r.project, r.kind, r.backend) for r in got] == [
        ("gua", "run", "claude_code"), ("gua", "run", "codex"), ("gua", "run", "claude_code"),
        ("gua", "chat", "claude_code"), ("gua", "chat", "claude_code"),
        (None, "chat", "claude_code"), ("pinn", "chat", "codex")]
    old, experiment, literature, first, timed_out, studio, codex = got
    assert old.at == datetime(2026, 8, 1, 12, tzinfo=UTC) and old.cost_usd == 9.0
    assert (literature.title, literature.workspace, literature.session) == (
        "文献检索", "w", "gua/w/literature/1")
    assert literature.at == datetime(2026, 10, 4, 12, tzinfo=UTC) and literature.tokens == 2200
    assert literature.model == "claude-opus-5", "CLI 报的那一版，去掉 [1m]"
    assert first.cost_usd == 0.5, "续接会话的累计（1.2）不算，用框架减好的单轮花费"
    assert (first.title, first.session) == ("复现论文的第一张表", "gua/c1")
    assert math.isnan(timed_out.cost_usd) and timed_out.tokens is None, "超时没报：未知，不是 0"
    assert studio.model == "claude-sonnet-5" and studio.session == "studio/c3"
    assert codex.cost_usd == pytest.approx(_C2), "订阅报不出成本：照对话 meta 记的模型折算"
    assert experiment.model == "gpt-5.6-terra", "留档没记模型：用产出 meta 里记的"
    assert experiment.cost_usd == pytest.approx(_EXPERIMENT), "命中缓存的按缓存价"


def test_summary_buckets_by_day_project_model_and_counts_unknown_cost(home: Path):
    got = spending.summary(home, days=30, now=NOW, tz=UTC)
    assert got["days"] == 30 and len(got["by_day"]) == 30
    assert got["by_day"][-1]["day"] == "2026-10-06" and got["by_day"][0]["day"] == "2026-09-07"
    today = got["by_day"][-1]
    assert today["cost_usd"] == pytest.approx(0.1 + _C2) and today["unknown"] == 0
    assert today["tokens"] == 5050 + 1100
    total = got["total"]
    assert total["cost_usd"] == pytest.approx(0.25 + 0.5 + 0.1 + _C2 + _EXPERIMENT), \
        "两个月前那次 $9 不在近 30 天里"
    assert total["unknown"] == 1 and total["count"] == 6
    assert (total["input_tokens"], total["cached_tokens"]) == (2000 + 1000 + 1000 + 5000 + 100_000,
                                                               80_000)
    assert [(p["id"], p["title"]) for p in got["by_project"]] == [
        ("gua", "复现 GUA"), (None, "编辑台"), ("pinn", "复现 PINN")]
    models = {(m["backend_title"], m["model_title"]): m for m in got["by_model"]}
    assert models[("Claude Code", "Opus 5")]["cost_usd"] == pytest.approx(0.75)
    assert models[("Claude Code", "Opus")]["unknown"] == 1, \
        "超时那轮没有 init，哪一版不知道：记对话 meta 里的别名"
    assert models[("Codex", "GPT-5.6 Terra")]["cost_usd"] == pytest.approx(_EXPERIMENT)
    assert {k["kind"]: k["count"] for k in got["by_kind"]} == {"chat": 4, "run": 2}


def test_summary_lists_sessions_newest_first_and_the_price_table(home: Path):
    got = spending.summary(home, days=30, now=NOW, tz=UTC)
    sessions = got["sessions"]
    assert [s["key"] for s in sessions] == [
        "pinn/c2", "studio/c3", "gua/c1", "gua/w/literature/1", "gua/w/experiment/1"]
    chat = sessions[2]
    assert (chat["kind"], chat["title"], chat["project_title"], chat["count"], chat["unknown"]) == (
        "chat", "复现论文的第一张表", "复现 GUA", 2, 1)
    assert chat["at"] == "2026-10-05T13:00:00+00:00", "一段会话最后一次调用的时刻"
    run = sessions[3]
    assert (run["kind"], run["title"], run["workspace"], run["workspace_title"],
            run["model_title"]) == ("run", "文献检索", "w", "第一张表", "Opus 5")
    assert sessions[1]["project"] is None and sessions[1]["project_title"] == "编辑台"
    sol = next(p for p in got["pricing"] if p["model"] == "gpt-6.1-sol")
    assert (sol["backend_title"], sol["model_title"], sol["input"], sol["cached"],
            sol["output"]) == ("Codex", "GPT-6.1 Sol", 2, 0.10, 10)


def test_summary_rereads_a_session_only_after_it_changes(home: Path, monkeypatch):
    spending.summary(home, days=30, now=NOW, tz=UTC)
    reads: list[Path] = []
    original = spending._events

    def counted(path: Path) -> list[dict]:
        reads.append(path)
        return original(path)

    monkeypatch.setattr(spending, "_events", counted)
    before = spending.summary(home, days=30, now=NOW, tz=UTC)["total"]["cost_usd"]
    assert reads == [], "没改过的留档不重读"
    log = next(home.glob("projects/gua/workspaces/w/literature/1/executor/hop-0/*.jsonl"))
    _lines(log, _claude(0.75, read=10, out=10))
    got = spending.summary(home, days=30, now=NOW, tz=UTC)
    assert reads == [log] and got["total"]["cost_usd"] == pytest.approx(before + 0.5)
