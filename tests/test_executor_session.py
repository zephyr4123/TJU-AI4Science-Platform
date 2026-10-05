"""执行层会话：没开工就失败的隔一会重试（外层 #235）。

#226 演练里 Codex 一时满载，会话起来就退（退出码 1、一个文件没动），精读因此丢了一篇关键论文。
判据只用框架看得见的：自己退出且退出码非零、没超时、没动文件、没花钱；别的失败照旧交给能力判。
"""

from __future__ import annotations

import math
from pathlib import Path

import pytest

from backends import RunResult
from framework.executor import session

NOT_STARTED = RunResult(exit_code=1, cost_usd=math.nan, stdout_tail="Selected model is at capacity")


class ListRunner:
    """按顺序交回预先写好的结果；每次往 cwd/.ai4sci/ 写一份事件流，像真适配器那样。"""

    name = "codex"

    def __init__(self, results: list[RunResult]) -> None:
        self.results = list(results)
        self.calls = 0

    @staticmethod
    def tool_guide(bash_rules: tuple[str, ...]) -> str:
        return ""

    def run(self, prompt: str, cwd: Path, **_: object) -> RunResult:
        self.calls += 1
        scratch = Path(cwd) / session.SCRATCH_DIRNAME
        scratch.mkdir(exist_ok=True)
        (scratch / f"executor-{self.calls}.jsonl").write_text("{}\n", encoding="utf-8")
        return self.results.pop(0)


@pytest.fixture
def waits(monkeypatch) -> list[float]:
    slept: list[float] = []
    monkeypatch.setattr(session.time, "sleep", slept.append)
    return slept


def _run(tmp_path: Path, runner: ListRunner) -> RunResult:
    return session.run_session(runner, "读这篇", cwd=tmp_path / "work", allowed_paths=[tmp_path],
                               log_dir=tmp_path / "logs")


@pytest.fixture(autouse=True)
def _work(tmp_path):
    (tmp_path / "work").mkdir()


def test_a_session_that_never_started_is_retried_after_a_wait(tmp_path, waits):
    done = RunResult(exit_code=0, changed_files=["note.md"], cost_usd=math.nan)
    runner = ListRunner([NOT_STARTED, done])
    assert _run(tmp_path, runner) is done
    assert runner.calls == 2
    assert waits == [session.RETRY_WAITS_S[0]]
    # 每次的事件流都留档，失败那次也在
    assert sorted(p.name for p in (tmp_path / "logs").iterdir()) == ["executor-1.jsonl",
                                                                     "executor-2.jsonl"]


def test_retries_run_out_and_the_last_failure_goes_back_to_the_capability(tmp_path, waits):
    runner = ListRunner([NOT_STARTED] * (len(session.RETRY_WAITS_S) + 1))
    assert _run(tmp_path, runner) is NOT_STARTED
    assert runner.calls == len(session.RETRY_WAITS_S) + 1
    assert waits == list(session.RETRY_WAITS_S)


@pytest.mark.parametrize("failed", [
    RunResult(exit_code=1, changed_files=["half.md"], cost_usd=math.nan),  # 动过文件
    RunResult(exit_code=1, timed_out=True, cost_usd=math.nan),  # 超时
    RunResult(exit_code=1, cost_usd=0.42),  # 花了钱：撞了轮数或预算的闸
    RunResult(exit_code=-9, cost_usd=math.nan),  # 被信号杀的：有人停了它
    RunResult(exit_code=0, cost_usd=math.nan),  # 走完了，只是没写东西：能力去判
], ids=["changed-files", "timed-out", "spent", "killed", "finished"])
def test_other_failures_are_not_retried(tmp_path, waits, failed):
    runner = ListRunner([failed])
    assert _run(tmp_path, runner) is failed
    assert runner.calls == 1
    assert waits == []
