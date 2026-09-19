"""工作流：经过几个阶段、按什么顺序，哪几个阶段完了要人签（纲领 P-18、P-19）。

一个工作流一个 YAML。库在仓根 `workflows/`（通用，编辑台的造流助理改），工作区 `flows/` 里的是取来
改过参数的实例（研究助理用），两处同一套检查。它是预装的走法，不是平台本身：平台是七个研究阶段和每个阶段里的能力。

    name: research               # 目录里唯一，等于文件名去掉 .yaml
    title: 从课题到验证
    summary: 一段人话
    stages:
      - 设计                                     # 一个阶段：这个阶段用哪些能力由助理看着办
      - 断点: 核对评分脚本算的是不是你要的数         # 前一个阶段的产出要人签了下游才能读；
      写一句要人确认什么
      - 实验: {auto-research: {max_iters: 3}}   # 点名用哪颗能力、带什么参数（参数名是描述符里的
      Param）
      - 分析: [analysis]                         # 点名但不带参数也行
      - 验证
      - 断点: 验收
    layout:                      # 可选：画布上每一项的坐标，与 stages 一样长；框架只原样存取
      - [0, 0]
      - [264, 0]

断点是开放的：几个、放哪由流定——端到端全自动的流一个没有，步步确认的流每步一个。含义只有一个：
前一个阶段的产出要人签（产出目录里的 signed.json）了，下游能力才能 `--from` 它。
阶段之间没有显式的输入输出接口：检查只看阶段名对不对、点名的能力在不在那个阶段、参数名与类型对不对、断点位置合不合法
（不能开头就是断点、不能两个断点挨着）。一个阶段里要的东西盘上有没有，是那颗能力开始执行时自己查的（P-7）。
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from framework.contracts.capability import PARAM_TYPES, Capability
from framework.contracts.stages import STAGE_NAMES as STAGES

STOP = "断点"
# 文件名就是流的名字（P-13）：小写英文加连字符，页面存流时也按这个拒
NAME_RE = re.compile(r"[a-z][a-z0-9-]*")


class WorkflowInvalid(ValueError):
    """文件形状不对；`str(exc)` 带文件名与原因。"""


@dataclass(frozen=True)
class Pick:
    """一个阶段里点名用的一颗能力，可带参数（`with`），键是描述符里的 Param 名：agent 照着调用，
    页面照着画。"""

    cap: str
    with_: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {"cap": self.cap, "with": dict(self.with_)}


@dataclass(frozen=True)
class Stage:
    """走进入一个阶段。`picks` 空着就是这个阶段用什么由助理看着办。"""

    stage: str
    picks: tuple[Pick, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {"kind": "stage", "stage": self.stage, "caps": [p.to_dict() for p in self.picks]}


@dataclass(frozen=True)
class Stop:
    """前一个阶段的产出要人签了下游才能读。`note` 是要人确认什么（可空）。"""

    note: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {"kind": "stop", "note": self.note}


@dataclass(frozen=True)
class Workflow:
    name: str
    title: str
    summary: str
    stages: tuple[Stage | Stop, ...] = ()
    """页面画布上每一项的坐标（与 stages 一样长），人摆过才有；框架不读它。"""
    layout: tuple[tuple[float, float], ...] | None = None

    @property
    def caps(self) -> list[str]:
        """点名用到的能力，按出现顺序。"""
        return [p.cap for r in self.stages if isinstance(r, Stage) for p in r.picks]

    @property
    def covered(self) -> list[str]:
        """经过哪几个阶段，按出现顺序、去重：给卡片说一句「从哪儿到哪儿」。"""
        out: list[str] = []
        for r in self.stages:
            if isinstance(r, Stage) and r.stage not in out:
                out.append(r.stage)
        return out

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "title": self.title, "summary": self.summary,
                "stages": [r.to_dict() for r in self.stages],
                "layout": [list(xy) for xy in self.layout] if self.layout else None}


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
    title, summary = raw.get("title"), raw.get("summary")
    if not isinstance(title, str) or not title.strip():
        raise WorkflowInvalid(f"{filename}: 缺 title")
    if not isinstance(summary, str) or not summary.strip():
        raise WorkflowInvalid(f"{filename}: 缺 summary")
    stages_raw = raw.get("stages")
    if not isinstance(stages_raw, list) or not stages_raw:
        raise WorkflowInvalid(f"{filename}: stages 要是非空列表")
    stages = tuple(_item(filename, i, item) for i, item in enumerate(stages_raw, start=1))
    if isinstance(stages[0], Stop):
        raise WorkflowInvalid(f"{filename}: 第 1 项就是断点：还什么都没做，没有东西可确认")
    for i in range(1, len(stages)):
        if isinstance(stages[i], Stop) and isinstance(stages[i - 1], Stop):
            raise WorkflowInvalid(
                f"{filename}: 第 {i} 项与第 {i + 1} 项都是断点：两个断点挨着等于一个")
    return Workflow(name=name, title=title.strip(), summary=" ".join(summary.split()),
                    stages=stages, layout=_layout(filename, raw.get("layout"), len(stages)))


def _layout(filename: str, raw: Any, count: int) -> tuple[tuple[float, float], ...] | None:
    """页面的坐标块：没有就没有；有就得是与 stages 一样长的 [x, y] 列表。"""
    if raw is None:
        return None
    ok = (isinstance(raw, list) and len(raw) == count
          and all(isinstance(xy, list) and len(xy) == 2
                  and all(isinstance(v, int | float) and not isinstance(v, bool) for v in xy)
                  for xy in raw))
    if not ok:
        raise WorkflowInvalid(f"{filename}: layout 要是与 stages 一样长的 [x, y] 列表")
    return tuple((float(x), float(y)) for x, y in raw)


def _item(filename: str, index: int, raw: Any) -> Stage | Stop:
    label = f"{filename}: 第 {index} 项"
    if isinstance(raw, str):
        if raw == STOP:
            return Stop()
        if raw in STAGES:
            return Stage(raw)
        raise WorkflowInvalid(
            f"{label} {raw!r} 不是阶段也不是断点（阶段：{STAGES}；断点写「{STOP}」）")
    if not isinstance(raw, dict) or len(raw) != 1:
        raise WorkflowInvalid(
            f"{label} 要是阶段名、「{STOP}」，或「阶段名: 能力」「{STOP}: 一句话」的单键映射")
    [(key, value)] = raw.items()
    if key == STOP:
        if value is None:
            return Stop()
        if not isinstance(value, str) or not value.strip():
            raise WorkflowInvalid(f"{label} 的断点后面要是一句话（要人确认什么）")
        return Stop(note=" ".join(value.split()))
    if key not in STAGES:
        raise WorkflowInvalid(f"{label} 的 {key!r} 不是阶段（阶段：{STAGES}）")
    return Stage(key, _picks(label, value))


def _picks(label: str, raw: Any) -> tuple[Pick, ...]:
    """一个阶段里点名的能力：`[a, b]` 或 `{a: {参数}, b: null}`；空就是不点名。"""
    if raw is None:
        return ()
    if isinstance(raw, list):
        if not all(isinstance(c, str) and c for c in raw):
            raise WorkflowInvalid(f"{label} 的能力清单要是名字的列表")
        return tuple(Pick(c) for c in raw)
    if isinstance(raw, dict):
        out: list[Pick] = []
        for cap, params in raw.items():
            if not isinstance(cap, str) or not cap:
                raise WorkflowInvalid(f"{label} 的能力名要是字符串")
            if params is None:
                params = {}
            if not isinstance(params, dict) or not all(isinstance(k, str) and k for k in params):
                raise WorkflowInvalid(f"{label} 的 {cap} 后面要是「参数名: 值」的映射")
            out.append(Pick(cap, dict(params)))
        return tuple(out)
    raise WorkflowInvalid(f"{label} 的阶段后面要是能力名列表、「能力: 参数」映射，或空着")


def save_workflow(root: Path, raw: dict[str, Any], catalog: dict[str, Capability], *,
                  overwrite: bool = False) -> Workflow:
    """编辑台存一条流：形状与检查都过了才写 `<root>/<name>.yaml`；已有同名不覆盖，除非明说。

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
                           "summary": workflow.summary,
                           "stages": [_item_doc(item) for item in workflow.stages]}
    if workflow.layout:
        doc["layout"] = [_Row((round(x), round(y))) for x, y in workflow.layout]
    Path(root).mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(doc, allow_unicode=True, sort_keys=False, width=100),
                    encoding="utf-8")
    return workflow


class _Row(list):
    """layout 里的一对坐标：写成一行 `[x, y]`，不拆成两行。"""


def _represent_row(dumper: yaml.SafeDumper, data: _Row) -> yaml.Node:
    return dumper.represent_sequence("tag:yaml.org,2002:seq", list(data), flow_style=True)


yaml.SafeDumper.add_representer(_Row, _represent_row)


def _item_doc(item: Stage | Stop) -> Any:
    """写回文件时用最短的写法：不点名的阶段一个名字，不带参数的点名一个列表，断点一个词。"""
    if isinstance(item, Stop):
        return {STOP: item.note} if item.note else STOP
    if not item.picks:
        return item.stage
    if all(not p.with_ for p in item.picks):
        return {item.stage: [p.cap for p in item.picks]}
    return {item.stage: {p.cap: (dict(p.with_) or None) for p in item.picks}}


def workflow_problems(workflow: Workflow, catalog: dict[str, Capability]) -> list[str]:
    """点名的能力都在清单里、都属于那个阶段、参数对得上描述符。空清单表示通。"""
    problems: list[str] = []
    for i, item in enumerate(workflow.stages, start=1):
        if not isinstance(item, Stage):
            continue
        for pick in item.picks:
            cap = catalog.get(pick.cap)
            label = f"第 {i} 项「{item.stage}」里的 {pick.cap}"
            if cap is None:
                problems.append(f"{label}：没有这颗能力（有的：{sorted(catalog)}）")
                continue
            if cap.stage != item.stage:
                problems.append(
                    f"{label} 属于「{cap.stage}」阶段，不能放在「{item.stage}」阶段里")
            problems += _with_problems(label, pick.with_, cap)
    return problems


def _with_problems(label: str, params: dict[str, Any], cap: Capability) -> list[str]:
    """参数按描述符核对：名字要在 Param 表里、得是流里能写的（in_flow），值要是那个类型
    （int 可以当 float）。"""
    known = {p.name: p for p in cap.params}
    out: list[str] = []
    for name, value in params.items():
        param = known.get(name)
        if param is None:
            out.append(f"{label} 带了描述符里没有的参数 {name!r}（有的：{sorted(known)}）")
            continue
        if not param.in_flow:
            out.append(f"{label} 的 {name} 是每次调用时才定的，不写进流")
            continue
        expected = PARAM_TYPES[param.type]
        ok = (isinstance(value, expected) and not (expected is not bool and isinstance(value, bool))
              or (expected is float and isinstance(value, int) and not isinstance(value, bool)))
        if not ok:
            out.append(f"{label} 的 {name} 要是 {param.type}，实际 {value!r}")
    return out


def remarks(workflow: Workflow) -> list[str]:
    """给人看的提醒，不是问题、不拦流。机器能说的一句：有实验或分析却没有验证，数字没人回溯。"""
    covered = workflow.covered
    if ("实验" in covered or "分析" in covered) and "验证" not in covered:
        return ["有实验或分析、没有验证：数字没人回溯，结果不能算可信"]
    return []


def stop_after(workflow: Workflow, index: int) -> Stop | None:
    """第 index 项（0 起）是阶段时，它后面紧跟的断点；没有就是 None——
    这个阶段的产出要不要人签就看它。"""
    following = index + 1
    if following < len(workflow.stages) and isinstance(workflow.stages[following], Stop):
        return workflow.stages[following]
    return None


def matching_step(workflow: Workflow, cap: str, stage: str, after: int = -1) -> int | None:
    """一颗能力跑在这条流的第几项（0 起）：`after` 之后第一个阶段对得上的项——点了名看名字，
    没点名看阶段。
    流里没有它就是 None。"""
    for i in range(after + 1, len(workflow.stages)):
        item = workflow.stages[i]
        if not isinstance(item, Stage):
            continue
        if (any(p.cap == cap for p in item.picks) if item.picks else item.stage == stage):
            return i
    return None


def describe_dir(root: Path, catalog: dict[str, Capability]) -> list[dict[str, Any]]:
    """目录里每个文件一条：读得出来的带 covers / remarks / problems；读不出来的（形状不对、YAML 坏）
    也占一条，名字是文件名，problems 里是那句原因。一个坏文件不能让整张清单打不开——研究助理
    在工作区 flows/ 里随手写个只有一行的文件，主页面就整个「Failed to fetch」，实测撞过。"""
    out: list[dict[str, Any]] = []
    for path in sorted(Path(root).glob("*.yaml")) if Path(root).is_dir() else []:
        try:
            wf = load_workflow(path)
        except WorkflowInvalid as exc:
            out.append({"name": path.stem, "title": path.stem, "summary": "", "stages": [],
                        "covers": [], "remarks": [], "problems": [str(exc)]})
            continue
        out += describe([wf], catalog)
    return out


def describe(workflows: Sequence[Workflow], catalog: dict[str, Capability]) -> list[dict[str, Any]]:
    """给页面与 `show workflows` 的响应体：每条流带它走过的阶段、提醒与问题清单。"""
    return [{**wf.to_dict(), "covers": wf.covered, "remarks": remarks(wf),
             "problems": workflow_problems(wf, catalog)} for wf in workflows]


def used_by(workflows: Sequence[Workflow]) -> dict[str, list[str]]:
    """能力名 → 点名用到它的工作流名。反查而不是写在能力上：工作流引用能力，能力不认识工作流。"""
    uses: dict[str, list[str]] = {}
    for wf in workflows:
        for cap in dict.fromkeys(wf.caps):
            uses.setdefault(cap, []).append(wf.name)
    return uses
