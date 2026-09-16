"""验收记录：结果验收看板上那颗键（外层 vision「两个发布键、一次验收」）。

与 `contracts.publish` 对称：发布签的是需求（manifest.yaml、design.md），验收签的是结果
（checkpoint 里的 best_iter / best_metric / best_commit 与验证报告的结论）。验收之后内环又跑了、
best 变了，记录就对不上——看板据此说「验收过的不是现在这个 best」，要人再看一遍，
而不是让旧签名盖住新结果。

放在 run 层而不是 contracts：它读 checkpoint，contracts 不认识 run 的目录。
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from framework.contracts.report import read_report
from framework.run import layout
from framework.run.checkpoint import read_checkpoint

LOGGER = logging.getLogger("ai4sci.run")
ACCEPT_NAME = "accept.json"
RECORD_FORMAT_VERSION = 1


class AcceptRefused(ValueError):
    """现在不能验收；`str(exc)` 说清为什么、该做什么。"""


def accept_run(run_dir: Path, *, by: str) -> dict[str, Any]:
    """写 `<run_dir>/accept.json`，返回记录。人按的键；协调 agent 不该替人按。

    三道门：要署名、内环没在跑、至少跑过一轮（只有基线没东西可验）。验证报告有就把结论签进去，
    报告不合约就拒绝——坏报告不能被一次验收盖过去。
    """
    run_dir = Path(run_dir).resolve()
    if not by.strip():
        raise AcceptRefused("验收要署名：--by <谁>，这是记录上的名字")
    if not layout.checkpoint(run_dir).is_file():
        raise AcceptRefused(f"run 没有 checkpoint，没东西可验收：{run_dir}")
    if layout.inflight(run_dir).is_file():
        raise AcceptRefused("内环正在跑（experiment/inflight.json 在），等它停下再验收")
    state = read_checkpoint(run_dir)
    if int(state["last_iter"]) == 0:
        raise AcceptRefused("一轮都没跑，只有基线，没东西可验收")
    verify = None
    report = layout.verify_report(run_dir)
    if report.is_file():
        try:
            verify = read_report(report)["status"]
        except ValueError as exc:
            raise AcceptRefused(f"验证报告不合约，先修再验收：{exc}") from exc
    record = {
        "format_version": RECORD_FORMAT_VERSION,
        "accepted_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "by": by.strip(),
        "best_iter": state["best_iter"],
        "best_metric": state["best_metric"],
        "best_commit": state["best_commit"],
        "verify": verify,
    }
    (run_dir / ACCEPT_NAME).write_text(
        json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    LOGGER.info("run_accept run_dir=%s by=%s best_iter=%s verify=%s",
                run_dir, record["by"], record["best_iter"], verify)
    return record


def read_acceptance(run_dir: Path) -> dict[str, Any] | None:
    """看板读：没验收过返回 None；验收过返回记录，外加 `stale`（验收后 best 变了）。"""
    run_dir = Path(run_dir)
    path = run_dir / ACCEPT_NAME
    if not path.is_file():
        return None
    record = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(record, dict) or record.get("format_version") != RECORD_FORMAT_VERSION:
        raise ValueError(f"{path} 的 format_version 不是 {RECORD_FORMAT_VERSION}，重新验收")
    state = read_checkpoint(run_dir)
    return {**record, "stale": record.get("best_commit") != state["best_commit"]}
