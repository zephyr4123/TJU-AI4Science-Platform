"""run 照的那条流与走到第几步——那张便条（外层 #63 等待状态）。

`cap start --workflow <name>` 把那条流的文件原样快照进 `runs/<id>/workflow/<name>.yaml`
（之后仓里的流改了不影响这个 run），`flow.json` 记 `step`：最近一次按的按钮落在流的第几步
（从 1 数，0 是还没按）。

推进步序是记录不是决策（P-10）：按哪颗仍是协调 agent 定；框架只在一颗 run 级能力跑成之后，从当前步
往后找第一个 cap 相同的步，找到就记到那儿，找不到（按了流外的按钮）就不动。「在等谁」不存、现算：
有作业在跑 → 等作业；下一步是键 → 等人按键；下一步是纯人的事 → 等人；流走完 → done；否则轮到助理。
存的越少，越不会和盘上别的东西打架。
"""

from __future__ import annotations

import json
import logging
import shutil
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from framework.contracts import workflows
from framework.run import jobs

LOGGER = logging.getLogger("ai4sci.flow")
FLOW_STATE_NAME = "flow.json"
SNAPSHOT_DIRNAME = "workflow"


def attach(run_dir: Path, workflow_path: Path) -> dict[str, Any]:
    """开 run 时照一条流：快照文件、记 step。流里有 `start` 就算已经按过它。"""
    run_dir = Path(run_dir)
    workflow = workflows.load_workflow(workflow_path)  # 快照前先读一遍：坏文件不进 run
    snapshot_dir = run_dir / SNAPSHOT_DIRNAME
    snapshot_dir.mkdir(exist_ok=True)
    shutil.copy2(workflow_path, snapshot_dir / workflow_path.name)
    step = next((i for i, s in enumerate(workflow.steps, start=1) if s.cap == "start"), 0)
    state = _save(run_dir, {"workflow": workflow.name, "step": step})
    LOGGER.info("flow_attach run=%s workflow=%s step=%d", run_dir.name, workflow.name, step)
    return state


def record_press(run_dir: Path, cap: str) -> dict[str, Any] | None:
    """一颗 run 级能力跑成了：步序推到从当前步往后第一个同名的步；没照流或流里没有它就不动。"""
    run_dir = Path(run_dir)
    state = _load(run_dir)
    if state is None:
        return None
    workflow = _snapshot(run_dir, state["workflow"])
    for i in range(state["step"] + 1, len(workflow.steps) + 1):
        if workflow.steps[i - 1].cap == cap:
            state = _save(run_dir, {**state, "step": i})
            LOGGER.info("flow_step run=%s workflow=%s cap=%s step=%d",
                        run_dir.name, workflow.name, cap, i)
            return state
    LOGGER.info("flow_offpath run=%s workflow=%s cap=%s step=%d",
                run_dir.name, workflow.name, cap, state["step"])
    return state


def status(run_dir: Path, runs_root: Path) -> dict[str, Any] | None:
    """便条的完整读法：哪条流、第几步、下一步是什么、在等谁。没照流就是 None。"""
    run_dir = Path(run_dir)
    state = _load(run_dir)
    if state is None:
        return None
    workflow = _snapshot(run_dir, state["workflow"])
    step = state["step"]
    following = workflow.steps[step] if step < len(workflow.steps) else None
    job = jobs.running_for(runs_root, run_dir.name)
    if job is not None:
        waiting = f"job:{job.job_id}"
    elif following is None:
        waiting = "done"
    elif following.key:
        waiting = f"key:{following.key}"
    elif following.cap is None:
        waiting = "human"
    else:
        waiting = "assistant"
    return {"workflow": workflow.name, "title": workflow.title, "step": step,
            "total": len(workflow.steps), "steps": [s.to_dict() for s in workflow.steps],
            "next": None if following is None else following.to_dict(), "waiting": waiting,
            "updated_at": state.get("updated_at")}


def _snapshot(run_dir: Path, name: str) -> workflows.Workflow:
    path = run_dir / SNAPSHOT_DIRNAME / f"{name}.yaml"
    if not path.is_file():
        raise FileNotFoundError(f"run 说照的是流 {name!r}，快照却不在：{path}")
    return workflows.load_workflow(path)


def _load(run_dir: Path) -> dict[str, Any] | None:
    path = run_dir / FLOW_STATE_NAME
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _save(run_dir: Path, state: dict[str, Any]) -> dict[str, Any]:
    state = {**state, "updated_at": datetime.now(UTC).isoformat(timespec="seconds")}
    (run_dir / FLOW_STATE_NAME).write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n",
                                           encoding="utf-8")
    return state
