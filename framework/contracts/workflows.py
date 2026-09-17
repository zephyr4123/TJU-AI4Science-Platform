"""工作流：一串步骤，有的步骤是能力（助理按），有的是键（人按），有的只是人要做的事。

一个工作流一个 YAML，放在仓根 `workflows/`。它是预装的拼法，不是平台本身：平台是能力清单，
协调 agent 可以照工作流走，也可以自己拼单点。这里只管读文件、查形状、把能力步骤交给
`flow.check_flow` 核对吃吐文件通不通；不跑任何东西。

    name: intake                 # 目录里唯一，等于文件名去掉 .yaml
    title: 接一个新课题
    summary: 一段人话
    assumes: [harness/, code/, run_0/]   # 可选：这条流开始时任务包里已经有的东西
    steps:
      - by: 人 | 助理
        does: 一句人话
        cap: design              # 可选：能力清单里的名字
        key: publish | accept    # 可选：人按的键
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from framework.contracts.capability import Capability
from framework.contracts.flow import check_flow, stage_remarks, stages_of

WORKFLOWS_DIRNAME = "workflows"
ACTORS = ("人", "助理")
KEYS = ("publish", "accept")


class WorkflowInvalid(ValueError):
    """文件形状不对；`str(exc)` 带文件名与原因。"""


@dataclass(frozen=True)
class Step:
    by: str
    does: str
    cap: str | None = None
    key: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {"by": self.by, "does": self.does, "cap": self.cap, "key": self.key}


@dataclass(frozen=True)
class Workflow:
    name: str
    title: str
    summary: str
    steps: tuple[Step, ...] = field(default_factory=tuple)
    assumes: tuple[str, ...] = ()

    @property
    def caps(self) -> list[str]:
        return [step.cap for step in self.steps if step.cap]

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "title": self.title, "summary": self.summary,
                "assumes": list(self.assumes), "steps": [step.to_dict() for step in self.steps]}


def workflows_root(repo_root: Path) -> Path:
    return Path(repo_root) / WORKFLOWS_DIRNAME


def load_workflows(root: Path) -> list[Workflow]:
    """读 `<root>/*.yaml`，按文件名排序。形状不对当场抛，不静默跳过坏文件。"""
    root = Path(root)
    if not root.is_dir():
        return []
    return [load_workflow(path) for path in sorted(root.glob("*.yaml"))]


def load_workflow(path: Path) -> Workflow:
    path = Path(path)
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise WorkflowInvalid(f"{path.name}: YAML 语法错误：{exc}") from exc
    if not isinstance(raw, dict):
        raise WorkflowInvalid(f"{path.name}: 顶层要是映射")
    name = raw.get("name")
    if name != path.stem:
        raise WorkflowInvalid(f"{path.name}: name 要等于文件名 {path.stem!r}，实际 {name!r}")
    title, summary = raw.get("title"), raw.get("summary")
    if not isinstance(title, str) or not title.strip():
        raise WorkflowInvalid(f"{path.name}: 缺 title")
    if not isinstance(summary, str) or not summary.strip():
        raise WorkflowInvalid(f"{path.name}: 缺 summary")
    steps_raw = raw.get("steps")
    if not isinstance(steps_raw, list) or not steps_raw:
        raise WorkflowInvalid(f"{path.name}: steps 要是非空列表")
    assumes = raw.get("assumes") or []
    if not isinstance(assumes, list) or not all(isinstance(a, str) and a for a in assumes):
        raise WorkflowInvalid(f"{path.name}: assumes 要是路径列表")
    return Workflow(name=name, title=title.strip(), summary=" ".join(summary.split()),
                    steps=tuple(_step(path.name, i, s) for i, s in enumerate(steps_raw, start=1)),
                    assumes=tuple(assumes))


def _step(filename: str, index: int, raw: Any) -> Step:
    label = f"{filename}: 第 {index} 步"
    if not isinstance(raw, dict):
        raise WorkflowInvalid(f"{label} 要是映射")
    by, does = raw.get("by"), raw.get("does")
    if by not in ACTORS:
        raise WorkflowInvalid(f"{label} 的 by 只能是 {ACTORS}，实际 {by!r}")
    if not isinstance(does, str) or not does.strip():
        raise WorkflowInvalid(f"{label} 缺 does")
    cap, key = raw.get("cap"), raw.get("key")
    if cap is not None and (not isinstance(cap, str) or not cap):
        raise WorkflowInvalid(f"{label} 的 cap 要是能力名")
    if key is not None and key not in KEYS:
        raise WorkflowInvalid(f"{label} 的 key 只能是 {KEYS}，实际 {key!r}")
    if cap and key:
        raise WorkflowInvalid(f"{label} 不能既是能力又是键")
    if cap and by != "助理":
        raise WorkflowInvalid(f"{label} 是能力 {cap}，by 要是「助理」（能力是给 agent 按的按钮）")
    if key and by != "人":
        raise WorkflowInvalid(f"{label} 是键 {key}，by 要是「人」（键只有人能按）")
    return Step(by=by, does=" ".join(does.split()), cap=cap, key=key)


def workflow_problems(workflow: Workflow, catalog: dict[str, Capability]) -> list[str]:
    """能力名都在清单里、能力步骤按顺序吃吐文件对得上。空清单表示通。"""
    unknown = [cap for cap in workflow.caps if cap not in catalog]
    if unknown:
        return [f"没有这些能力：{unknown}（有的：{sorted(catalog)}）"]
    if not workflow.caps:
        return []
    return check_flow([catalog[cap] for cap in workflow.caps], have=workflow.assumes)


def describe(workflows: Sequence[Workflow], catalog: dict[str, Capability]) -> list[dict[str, Any]]:
    """给页面与 `show workflows` 的响应体：每个工作流带它覆盖的阶段、提醒与问题清单。
    覆盖范围是从能力步骤算出来的，文件里不写。"""
    out: list[dict[str, Any]] = []
    for wf in workflows:
        covers = stages_of([catalog[cap] for cap in wf.caps if cap in catalog])
        out.append({**wf.to_dict(), "covers": covers, "remarks": stage_remarks(covers),
                    "problems": workflow_problems(wf, catalog)})
    return out


def used_by(workflows: Sequence[Workflow]) -> dict[str, list[str]]:
    """能力名 → 用到它的工作流名。反查而不是写在能力上：工作流引用能力，能力不认识工作流。"""
    uses: dict[str, list[str]] = {}
    for wf in workflows:
        for cap in dict.fromkeys(wf.caps):
            uses.setdefault(cap, []).append(wf.name)
    return uses
