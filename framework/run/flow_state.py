"""run 照的那条流与走到第几间——那张便条（外层 #63 等待状态，P-18 改成按房间记）。

开 run 的那颗能力（auto-research）带 `--workflow <name>` 时把那条流的文件原样快照进
`runs/<id>/workflow/<name>.yaml`（之后仓里的流改了不影响这个 run），`flow.json` 记 `step`：
最近一次调用的能力落在流的第几项（从 1 数，项包括房间与断点；0 是还没调用过）。

推进步序是记录不是决策（P-10）：调用哪颗仍是协调 agent 定；框架只在一颗能力跑成之后，从当前项往后找
第一间对得上的房间——点了名就看名字，没点名就看这颗能力属于哪一间——找到就记到那儿，找不到（调了流外的
能力）就不动。中间跳过的断点算人放行了：助理只在人点头之后才调用下一颗，这是它的纪律，机器不替它守
（出厂的「发布」「验收」两个断点各有确认记录，能力自己查）。「在等谁」不存、现算：
有作业在跑 → 等作业；
下一项是断点 → 等人确认（出厂的两个说是发布还是验收）；下一项是房间 → 轮到助理；流走完 → done。
"""

from __future__ import annotations

import json
import logging
import shutil
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from framework.contracts import workflows
from framework.contracts.workflows import Room, Stop
from framework.run import jobs

LOGGER = logging.getLogger("ai4sci.flow")
FLOW_STATE_NAME = "flow.json"
SNAPSHOT_DIRNAME = "workflow"


def attach(run_dir: Path, workflow_path: Path, *, cap: str, stage: str) -> dict[str, Any]:
    """开 run 时照一条流：快照文件，step 记到开 run 的那颗能力所在的房间**之前**——它正跑着，
    下一项就是它那一间；跑成之后它自己 `record_press` 推进去。流里没有它就记 0。"""
    run_dir = Path(run_dir)
    workflow = workflows.load_workflow(workflow_path)  # 快照前先读一遍：坏文件不进 run
    snapshot_dir = run_dir / SNAPSHOT_DIRNAME
    snapshot_dir.mkdir(exist_ok=True)
    shutil.copy2(workflow_path, snapshot_dir / workflow_path.name)
    step = next((i for i, item in enumerate(workflow.rooms) if _matches(item, cap, stage)), 0)
    state = _save(run_dir, {"workflow": workflow.name, "step": step})
    LOGGER.info("flow_attach run=%s workflow=%s step=%d", run_dir.name, workflow.name, step)
    return state


def record_press(run_dir: Path, cap: str, stage: str) -> dict[str, Any] | None:
    """一颗能力跑成了：步序推到从当前项往后第一间对得上的房间；没照流或流里没有它就不动。"""
    run_dir = Path(run_dir)
    state = _load(run_dir)
    if state is None:
        return None
    workflow = _snapshot(run_dir, state["workflow"])
    for i in range(state["step"] + 1, len(workflow.rooms) + 1):
        if _matches(workflow.rooms[i - 1], cap, stage):
            state = _save(run_dir, {**state, "step": i})
            LOGGER.info("flow_step run=%s workflow=%s cap=%s step=%d",
                        run_dir.name, workflow.name, cap, i)
            return state
    LOGGER.info("flow_offpath run=%s workflow=%s cap=%s step=%d",
                run_dir.name, workflow.name, cap, state["step"])
    return state


def _matches(item: Room | Stop, cap: str, stage: str) -> bool:
    if not isinstance(item, Room):
        return False
    if item.picks:
        return any(p.cap == cap for p in item.picks)
    return item.stage == stage


def status(run_dir: Path, jobs_dir: Path) -> dict[str, Any] | None:
    """便条的完整读法：哪条流、第几项、下一项是什么、在等谁。没照流就是 None。"""
    run_dir = Path(run_dir)
    state = _load(run_dir)
    if state is None:
        return None
    workflow = _snapshot(run_dir, state["workflow"])
    step = state["step"]
    following = workflow.rooms[step] if step < len(workflow.rooms) else None
    job = jobs.running_for(jobs_dir, run_dir.name)
    if job is not None:
        waiting = f"job:{job.job_id}"
    elif following is None:
        waiting = "done"
    elif isinstance(following, Stop):
        waiting = f"key:{following.key}" if following.key else "human"
    else:
        waiting = "assistant"
    return {"workflow": workflow.name, "title": workflow.title, "step": step,
            "total": len(workflow.rooms), "rooms": [r.to_dict() for r in workflow.rooms],
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
