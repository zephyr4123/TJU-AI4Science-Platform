"""看板读盘：工作区（需求 = 任务包、run 清单）与 run 的细节。纯读盘、零模型。

页面是 `ai4sci serve` 的客户端（`ui/README.md`）：这里每个函数就是一个端点的响应体，
server 只做路由；换一种 UI（TUI）读的也是同一份东西。每个响应体都是能直接 `json.dumps`
的字典——NaN 在这里就换成 None，浏览器的 JSON.parse 不认 NaN。
"""

from __future__ import annotations

import json
import math
from dataclasses import asdict
from pathlib import Path
from typing import Any

import yaml

from framework.contracts import headroom, packs, publish
from framework.contracts.report import read_report
from framework.memory import ledger
from framework.run import accept, flow_state, jobs, layout
from framework.run.checkpoint import read_checkpoint
from framework.run.context import load_manifest, primary_metric
from framework.run.workspace import Workspace

# 任务包走到哪一步。看板按它决定该亮哪颗键、说哪句「下一步」。
STAGES = ("drafting", "published", "designed", "baselined")


# ── 工作区 ───────────────────────────────────────────────────────────────
def workspace_summary(workspace: Workspace) -> dict[str, Any]:
    """顶栏切换用的一行：标题、任务包走到哪、几个 run。还没起任务包时 task 是 None。"""
    has_task = (workspace.task / packs.MANIFEST_NAME).is_file()
    return {**workspace.to_dict(), "task": task_summary(workspace.task) if has_task else None,
            "runs": len(_run_dirs(workspace))}


def workspace_detail(workspace: Workspace) -> dict[str, Any]:
    """主页面要的一整份：任务包的细节 + 全部 run 的摘要；流实例由 server 从 cli 注入的函数补。"""
    summary = workspace_summary(workspace)
    task = task_detail(workspace.task) if summary["task"] is not None else None
    return {**summary, "task": task, "runs": list_runs(workspace)}


# ── 需求 ─────────────────────────────────────────────────────────────────
def task_summary(task_dir: Path) -> dict[str, Any]:
    task_dir = Path(task_dir)
    manifest = _read_manifest(task_dir)
    return {
        "id": packs.task_id_of(task_dir),
        "title": manifest.get("title") or task_dir.name,
        "question": manifest.get("question") or "",
        "domain": manifest.get("domain") or packs.DEFAULT_DOMAIN,
        "metric": _primary(manifest),
        "stage": stage(task_dir),
        "publish": publish_state(task_dir),
    }


def task_detail(task_dir: Path) -> dict[str, Any]:
    task_dir = Path(task_dir)
    brief = task_dir / packs.BRIEF_NAME
    return {
        **task_summary(task_dir),
        "manifest": _read_manifest(task_dir),
        "design": brief.read_text(encoding="utf-8") if brief.is_file() else "",
        "intake_problems": packs.intake_problems(task_dir),
        "headroom": headroom_state(task_dir),
    }


def publish_state(task_dir: Path) -> dict[str, Any]:
    """钥匙现在是否有效。`state`：ok / missing（从没发布过，看板用自己的话说）/ invalid
    （发布过但签的文件改了或记录坏了，`reason` 是 `require_published` 那句话，原样给人看）。"""
    try:
        record = publish.require_published(task_dir)
    except publish.NotPublished as exc:
        missing = not (Path(task_dir) / publish.PUBLISH_NAME).is_file()
        return {"ok": False, "state": "missing" if missing else "invalid",
                "by": None, "at": None, "reason": str(exc)}
    return {"ok": True, "state": "ok", "by": record["by"], "at": record["published_at"],
            "reason": None}


def stage(task_dir: Path) -> str:
    """drafting（需求还在聊）→ published（发布了，等接任务）→ designed（harness/ code/ 有了）
    → baselined（run_0 有了，`run new` 可以开）。只看目录，不跑校验。"""
    task_dir = Path(task_dir)
    if not publish_state(task_dir)["ok"]:
        return "drafting"
    if not ((task_dir / "harness").is_dir() and (task_dir / "code").is_dir()):
        return "published"
    if not (task_dir / "run_0" / "results.json").is_file():
        return "designed"
    return "baselined"


def headroom_state(task_dir: Path) -> dict[str, Any] | None:
    """基线跑完才有预检；跑完但算不出来（manifest 缺字段、results 不合约）把原因当数据给看板。"""
    task_dir = Path(task_dir)
    run0 = task_dir / "run_0"
    if not ((run0 / "results.json").is_file() and (run0 / "sigma.json").is_file()):
        return None
    try:
        found = headroom.assess(task_dir)
    except (KeyError, ValueError, TypeError) as exc:
        return {"problems": [f"预检算不出来：{exc!s}"], "summary": None}
    gates = None
    if found.room is not None:
        gates = math.inf if found.gate <= 0 else found.room / found.gate
    return {
        "metric": found.metric, "direction": found.direction, "baseline": found.baseline,
        "sigma": found.sigma, "gate": found.gate, "attainable": found.attainable,
        "room": found.room, "gates": gates, "problems": found.problems(),
        "summary": found.summary(),
    }


# ── 结果验收 ─────────────────────────────────────────────────────────────
def list_runs(workspace: Workspace) -> list[dict[str, Any]]:
    return [run_summary(workspace, run_dir) for run_dir in _run_dirs(workspace)]


def _run_dirs(workspace: Workspace) -> list[Path]:
    """有 checkpoint 的才算 run；`runs/design/`（接任务的执行层日志）不是。"""
    if not workspace.runs.is_dir():
        return []
    return [p for p in sorted(workspace.runs.iterdir()) if layout.checkpoint(p).is_file()]


def run_summary(workspace: Workspace, run_dir: Path) -> dict[str, Any]:
    run_dir = Path(run_dir)
    state = read_checkpoint(run_dir)
    manifest = load_manifest(run_dir)
    metric = primary_metric(manifest)
    return {
        "run_id": state["run_id"],
        "task": manifest.get("id"),
        "title": manifest.get("title") or manifest.get("id"),
        "metric": {"name": metric["name"], "direction": metric["direction"]},
        "baseline": _baseline(run_dir, metric["name"]),
        "best_metric": state["best_metric"],
        "best_iter": state["best_iter"],
        "last_iter": state["last_iter"],
        "stop_reason": state.get("stop_reason"),
        "updated_at": state.get("updated_at"),
        "cost_usd": ledger.total_cost(layout.ledger(run_dir)),
        "running": layout.inflight(run_dir).is_file(),
        # 哪段对话开的（老 run 没有）：页面靠它知道当前对话最近碰的是哪条流
        "chat_id": state.get("chat_id"),
        "job": _job_dict(jobs.running_for(workspace.jobs, state["run_id"])),
        "flow": flow_state.status(run_dir, workspace.jobs),
        "analysis": layout.analysis_doc(run_dir).is_file(),
        "verify": verify_state(run_dir),
        "accept": accept.read_acceptance(run_dir),
    }


def run_detail(workspace: Workspace, run_dir: Path) -> dict[str, Any]:
    run_dir = Path(run_dir)
    analysis = layout.analysis_doc(run_dir)
    journal = layout.journal(run_dir)
    summary = run_summary(workspace, run_dir)
    return {
        **summary,
        "ledger": [asdict(row) for row in ledger.read(layout.ledger(run_dir))],
        "jobs": [job.to_dict() for job in jobs.jobs_for(workspace.jobs, summary["run_id"])],
        "journal": journal.read_text(encoding="utf-8") if journal.is_file() else "",
        "analysis_text": analysis.read_text(encoding="utf-8") if analysis.is_file() else None,
    }


def _job_dict(job: jobs.Job | None) -> dict[str, Any] | None:
    return None if job is None else job.to_dict()


def verify_state(run_dir: Path) -> dict[str, Any] | None:
    """没报告 None；报告不合约不当没有——`status: invalid` 带原因，看板要把它亮出来。"""
    report = layout.verify_report(run_dir)
    if not report.is_file():
        return None
    try:
        doc = read_report(report)
    except ValueError as exc:
        return {"status": "invalid", "error": str(exc)}
    return doc


# ── 内部 ─────────────────────────────────────────────────────────────────
def _read_manifest(task_dir: Path) -> dict[str, Any]:
    raw = yaml.safe_load((task_dir / packs.MANIFEST_NAME).read_text(encoding="utf-8"))
    return raw if isinstance(raw, dict) else {}


def _primary(manifest: dict[str, Any]) -> dict[str, Any] | None:
    """主指标；manifest 还没写好（需求还在聊）时是 None，不是报错。"""
    metrics = manifest.get("metrics")
    if not isinstance(metrics, list):
        return None
    for metric in metrics:
        if isinstance(metric, dict) and metric.get("primary"):
            return {"name": metric.get("name"), "direction": metric.get("direction"),
                    "attainable": metric.get("attainable")}
    return None


def _baseline(run_dir: Path, metric_name: str) -> float | None:
    path = layout.work(run_dir) / "run_0" / "results.json"
    if not path.is_file():
        return None
    metrics = json.loads(path.read_text(encoding="utf-8")).get("metrics") or {}
    value = metrics.get(metric_name)
    return float(value) if isinstance(value, int | float) else None


def jsonable(value: Any) -> Any:
    """递归把 NaN / ±inf 换成 None：账本里「未知」的耗时与成本就是 NaN（不是 0），
    但 JSON 标准没有 NaN，浏览器解析会直接炸。"""
    if isinstance(value, float):
        return None if math.isnan(value) or math.isinf(value) else value
    if isinstance(value, dict):
        return {k: jsonable(v) for k, v in value.items()}
    if isinstance(value, list | tuple):
        return [jsonable(v) for v in value]
    return value
