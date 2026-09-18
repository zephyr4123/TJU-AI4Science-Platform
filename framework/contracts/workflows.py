"""工作流：一串步骤，有的步骤是能力（助理按），有的是键（人按），有的只是人要做的事。

一个工作流一个 YAML。库在仓根 `workflows/`（通用，编辑台的造流助理改），工作区 `flows/` 里的是取来
改过参数的实例（研究助理用），两处同一套形状检查。它是预装的拼法，不是平台本身：平台是能力清单。这里只管读文件、查形状、把能力步骤交给
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

import re
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from framework.contracts.capability import PARAM_TYPES, Capability
from framework.contracts.flow import check_flow, stage_remarks, stages_of

ACTORS = ("人", "助理")
KEYS = ("publish", "accept")
# 文件名就是流的名字（P-13）：小写英文加连字符，页面存流时也按这个拒
NAME_RE = re.compile(r"[a-z][a-z0-9-]*")


class WorkflowInvalid(ValueError):
    """文件形状不对；`str(exc)` 带文件名与原因。"""


@dataclass(frozen=True)
class Step:
    by: str
    does: str
    cap: str | None = None
    key: str | None = None
    # 能力步骤的参数（`with: {max_iters: 3}`），键是描述符里的 Param 名：agent 照着按，页面照着画
    with_: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {"by": self.by, "does": self.does, "cap": self.cap, "key": self.key,
                "with": dict(self.with_)}


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


def load_workflows(root: Path) -> list[Workflow]:
    """读 `<root>/*.yaml`，按文件名排序。形状不对当场抛，不静默跳过坏文件。"""
    root = Path(root)
    if not root.is_dir():
        return []
    return [load_workflow(path) for path in sorted(root.glob("*.yaml"))]


def load_valid(root: Path) -> list[Workflow]:
    """读得出来的那些；坏文件跳过。坏在哪不在这里说，`describe_dir` 会把它当一条问题摆出来，
    所以这里的跳过不是静默——用在只要"能用的流"的地方（反查 used_by）。"""
    out: list[Workflow] = []
    for path in sorted(Path(root).glob("*.yaml")) if Path(root).is_dir() else []:
        try:
            out.append(load_workflow(path))
        except WorkflowInvalid:
            continue
    return out


def load_workflow(path: Path) -> Workflow:
    path = Path(path)
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise WorkflowInvalid(f"{path.name}: YAML 语法错误：{exc}") from exc
    return parse_workflow(path.name, raw)


def parse_workflow(filename: str, raw: Any) -> Workflow:
    """一份工作流的形状检查，读文件与页面存流走同一处；`filename` 只用来报错与核对 name。"""
    stem = filename[:-5] if filename.endswith(".yaml") else filename
    if not isinstance(raw, dict):
        raise WorkflowInvalid(f"{filename}: 顶层要是映射")
    name = raw.get("name")
    if name != stem:
        raise WorkflowInvalid(f"{filename}: name 要等于文件名 {stem!r}，实际 {name!r}")
    if not NAME_RE.fullmatch(str(name)):
        raise WorkflowInvalid(f"{filename}: name 只能是小写英文、数字、连字符，实际 {name!r}")
    path = Path(filename)
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
    params = raw.get("with") or {}
    if not isinstance(params, dict) or not all(isinstance(k, str) and k for k in params):
        raise WorkflowInvalid(f"{label} 的 with 要是「参数名: 值」的映射")
    if params and not cap:
        raise WorkflowInvalid(f"{label} 不是能力步骤，不该有 with")
    return Step(by=by, does=" ".join(does.split()), cap=cap, key=key, with_=dict(params))


def save_workflow(root: Path, raw: dict[str, Any], catalog: dict[str, Capability], *,
                  overwrite: bool = False) -> Workflow:
    """编辑台存一条流：形状与通不通都过了才写 `<root>/<name>.yaml`；已有同名不覆盖，除非明说。

    存的是页面交来的原样映射（只留认识的键），YAML 里中文原样、键序照给。
    """
    workflow = parse_workflow(f"{raw.get('name')}.yaml", raw)
    problems = workflow_problems(workflow, catalog)
    if problems:
        raise WorkflowInvalid(f"{workflow.name}.yaml: " + "；".join(problems))
    path = Path(root) / f"{workflow.name}.yaml"
    if path.exists() and not overwrite:
        raise FileExistsError(
            f"已经有一条叫 {workflow.name!r} 的流：{path}；换个名字，或者明说覆盖")
    doc: dict[str, Any] = {"name": workflow.name, "title": workflow.title,
                           "summary": workflow.summary}
    if workflow.assumes:
        doc["assumes"] = list(workflow.assumes)
    doc["steps"] = [_step_doc(step) for step in workflow.steps]
    Path(root).mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(doc, allow_unicode=True, sort_keys=False, width=100),
                    encoding="utf-8")
    return workflow


def _step_doc(step: Step) -> dict[str, Any]:
    doc: dict[str, Any] = {"by": step.by, "does": step.does}
    if step.cap:
        doc["cap"] = step.cap
    if step.key:
        doc["key"] = step.key
    if step.with_:
        doc["with"] = dict(step.with_)
    return doc


def workflow_problems(workflow: Workflow, catalog: dict[str, Capability]) -> list[str]:
    """能力名都在清单里、能力步骤按顺序吃吐文件对得上。空清单表示通。"""
    unknown = [cap for cap in workflow.caps if cap not in catalog]
    if unknown:
        return [f"没有这些能力：{unknown}（有的：{sorted(catalog)}）"]
    problems = [p for i, step in enumerate(workflow.steps, start=1) if step.cap
                for p in _with_problems(f"第 {i} 步 {step.cap}", step.with_, catalog[step.cap])]
    if not workflow.caps:
        return problems
    return problems + check_flow([catalog[cap] for cap in workflow.caps], have=workflow.assumes)


def _with_problems(label: str, params: dict[str, Any], cap: Capability) -> list[str]:
    """步骤参数按描述符核对：名字要在 Param 表里，值要是那个类型（int 可以当 float）。"""
    known = {p.name: p for p in cap.params}
    out: list[str] = []
    for name, value in params.items():
        param = known.get(name)
        if param is None:
            out.append(f"{label} 的 with 有描述符里没有的参数 {name!r}（有的：{sorted(known)}）")
            continue
        expected = PARAM_TYPES[param.type]
        ok = (isinstance(value, expected) and not (expected is not bool and isinstance(value, bool))
              or (expected is float and isinstance(value, int) and not isinstance(value, bool)))
        if not ok:
            out.append(f"{label} 的 with.{name} 要是 {param.type}，实际 {value!r}")
    return out


def describe_dir(root: Path, catalog: dict[str, Capability]) -> list[dict[str, Any]]:
    """目录里每个文件一条：读得出来的带 covers / remarks / problems；读不出来的（形状不对、YAML 坏）
    也占一条，名字是文件名，problems 里是那句原因。一个坏文件不能让整张清单打不开——研究助理
    在工作区 flows/ 里随手写个只有一行的文件，主页面就整个「Failed to fetch」，实测撞过。"""
    out: list[dict[str, Any]] = []
    for path in sorted(Path(root).glob("*.yaml")) if Path(root).is_dir() else []:
        try:
            wf = load_workflow(path)
        except WorkflowInvalid as exc:
            out.append({"name": path.stem, "title": path.stem, "summary": "", "assumes": [],
                        "steps": [], "covers": [], "remarks": [], "problems": [str(exc)]})
            continue
        out += describe([wf], catalog)
    return out


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
