"""一条流程走到哪：不另存记录，从产出的 meta（在哪条流程第几项下产的）与签字现算（纲领 P-19）。

每个产出记 `flow` / `step`，所以「这条流程的第 k 项」有哪几次产出、成没成、签没签，扫一遍就知道。
「在等谁」也现算：作业在跑 → 等作业；下一项是断点而前一项的产出没签 → 等人签；下一项是阶段 →
轮到助理；
走完 → done。同一条流程走两遍就是同一项下两次产出，都列出来，页面按 from 链分辨。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from framework.contracts import output, workflows
from framework.contracts.output import Meta
from framework.workspace import jobs
from framework.workspace.root import Workspace

WAITING_JOB = "job"
WAITING_SIGN = "sign"
WAITING_ASSISTANT = "assistant"
DONE = "done"


def flow_progress(workspace: Workspace, workflow: workflows.Workflow,
                  outputs: list[tuple[Path, Meta]],
                  kinds: dict[str, str] | None = None) -> dict[str, Any]:
    """一条流程实例的进度：每一项下有哪几次产出、走到第几项、在等谁。`kinds` 是名字 → 步骤 / skill，
    给了就格子上每个名字标上（看板按 tag 分两行画）。"""
    mine = [(d, m) for d, m in outputs if m.flow == workflow.name and m.step is not None]
    items: list[dict[str, Any]] = []
    for i, item in enumerate(workflow.stages):
        here = [(d, m) for d, m in mine if m.step == i]
        doc = item.to_dict(kinds) if isinstance(item, workflows.Stage) else item.to_dict()
        entry = {**doc, "index": i,
                 "outputs": [_brief(d, m) for d, m in here]}
        if isinstance(item, workflows.Stop):
            # 断点管的是前一项的产出：签了没
            previous = [e for e in items if e["kind"] == "stage"]
            done = previous[-1]["outputs"] if previous else []
            entry["signed"] = any(o["signed"] and not o["signed_stale"] for o in done)
        items.append(entry)
    stage_items = [e for e in items if e["kind"] == "stage"]
    reached = [e["index"] for e in stage_items if any(o["status"] == "ok" for o in e["outputs"])]
    step = max(reached) if reached else -1
    running = jobs.running_flow(workspace.jobs, workflow.name)
    if running is not None:
        waiting = WAITING_JOB
    elif step + 1 >= len(items):
        waiting = DONE
    elif items[step + 1]["kind"] == "stop":
        waiting = WAITING_SIGN if not items[step + 1]["signed"] else (
            DONE if step + 2 >= len(items) else WAITING_ASSISTANT)
    else:
        waiting = WAITING_ASSISTANT
    return {"name": workflow.name, "title": workflow.title, "summary": workflow.summary,
            "items": items, "step": step, "total": len(items), "waiting": waiting,
            "job": None if running is None else running.to_dict()}


def _brief(directory: Path, meta: Meta) -> dict[str, Any]:
    signed = output.signature_state(directory)
    return {"id": meta.id, "title": meta.title, "status": meta.status, "by": meta.by,
            "from": meta.input_ids, "signed": signed is not None,
            "signed_stale": bool(signed and signed["stale"])}
