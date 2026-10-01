"""流程库：两层、起名、血缘、查重（纲领 P-15、P-16）。形状与检查在 `workflows.py`，这里只管
「库」。

- **两层**：出厂的（`workflows/`，随代码走、只读；平台的底，不能改不能删——主人 2026-09-22）
  与人自己存的（数据根 `studio/workflows/`，编辑台写它；外层 #149）。名字全库唯一、以出厂的
  为准：存与出厂重名的拒，手搬进用户库的在清单里标成问题。用户库可以还不存在，读到的就是空。
- **名字是机器名，平台起**（外层 #199）：人只写中文 `title`。从一条派生的叫
  `<家族名>-<序号>`——家族名是顺着 `from` 走到底的那条（`reproduce` → `reproduce-2`、
  `reproduce-3`，从 `reproduce-2` 再派生也是 `reproduce-<n>`）；序号取家族里最大的加一，删掉的
  名字记在用户库的 `.removed` 里不再发（工作区实例的 `from` 还指着它）。从零拼的由流程助理起
  英文名，页面存的按标题里的英文词起，撞了加 `-b`、`-c`；`<库里已有的名字>-<数字>` 留给派生，
  从零起的不许用。
- **血缘**：文件里的 `from` 记直接父流程与派生那一刻它的结构 hash。差异不进名字：阶段、挂的
  能力、参数、断点的增删现算（`diff`）；父流程之后改过（hash 对不上）要提醒。
- **查重**：存进库时，结构（阶段、点名的能力与参数、断点位置）与库里已有某条完全一样的拒；
  参数不同算不同，标题、说明、断点那句话、画布坐标不算。
"""

from __future__ import annotations

import difflib
import re
import unicodedata
from collections.abc import Collection
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from framework.contracts.capability import Capability
from framework.contracts.workflows import (
    STOP,
    Origin,
    Stage,
    Stop,
    Workflow,
    WorkflowInvalid,
    describe_dir,
    load_valid,
    load_workflow,
    parse_workflow,
    save_workflow,
)

NAME_MAX = 40  # 从标题起的名字最长几个字符（不算序号）
FRESH = "flow"  # 标题里没有英文词时的名字
REMOVED_FILE = ".removed"  # 用户库里删掉过的名字，一行一个：平台不再把它们发给新流程
SEQ_RE = re.compile(r"^(?P<family>.+)-(?P<seq>\d+)$")


class DuplicateWorkflow(FileExistsError):
    """结构与库里已有的某条一模一样：同一个走法不存两份（409，与同名同一种拒法）。"""


@dataclass(frozen=True)
class Library:
    shipped: Path
    user: Path

    def shipped_names(self) -> frozenset[str]:
        return frozenset(_stems(self.shipped))

    def names(self) -> list[str]:
        return sorted({*_stems(self.shipped), *_stems(self.user)})

    def find(self, name: str) -> Path | None:
        """一条流程的文件，出厂的在前；没有就是 None。"""
        for root in (self.shipped, self.user):
            path = root / f"{name}.yaml"
            if path.is_file():
                return path
        return None

    def load(self, name: str) -> Workflow | None:
        """读得出来的那条；没有或读不出来都是 None（读不出来的由 describe 当问题摆出来）。"""
        path = self.find(name)
        if path is None:
            return None
        try:
            return load_workflow(path)
        except WorkflowInvalid:
            return None

    def load_valid(self) -> list[Workflow]:
        """两层里读得出来的流程，出厂在前；用户库里与出厂重名的不算（反查 used_by 用）。"""
        taken = self.shipped_names()
        mine = [wf for wf in load_valid(self.user) if wf.name not in taken]
        return load_valid(self.shipped) + mine

    # ── 起名与血缘 ──────────────────────────────────────────────────────────
    def family(self, name: str) -> str:
        """家族名：顺着 `from` 走到底；父流程不在库里了、或绕成了圈，就停在走到的那条。"""
        seen = {name}
        current = name
        while True:
            workflow = self.load(current)
            if workflow is None or workflow.origin is None or workflow.origin.name in seen \
                    or self.find(workflow.origin.name) is None:
                return current
            current = workflow.origin.name
            seen.add(current)

    def next_name(self, family: str) -> str:
        """`<家族名>-<序号>`：家族里最大的序号加一——库里在的、删掉过的、被 `from` 指着的都算，
        不发一个曾经指过别的流程的名字。"""
        seqs = [int(m["seq"]) for name in self._ever_named()
                if (m := SEQ_RE.match(name)) and m["family"] == family]
        return f"{family}-{max(seqs, default=1) + 1}"

    def suggest_name(self, title: str) -> str:
        """从零拼、又没给名字的（页面存的）：标题里的英文词连起来，没有就是 flow；占了加 -b、-c……
        （数字序号留给派生，不让它看着像谁的后代）。"""
        plain = unicodedata.normalize("NFKD", title)
        plain = "".join(c for c in plain if not unicodedata.combining(c)).lower()
        base = "-".join(re.findall(r"[a-z0-9]+", plain))[:NAME_MAX].strip("-") or FRESH
        if not base[0].isalpha():
            base = f"{FRESH}-{base}"
        if SEQ_RE.match(base):
            base = f"{base}-flow"
        taken = self._ever_named()
        for name in (base, *(f"{base}-{c}" for c in "bcdefghijklmnopqrstuvwxyz")):
            if name not in taken:
                return name
        raise FileExistsError(f"从标题起的名字 {base}-b … {base}-z 都占了：换个标题")

    def _ever_named(self) -> set[str]:
        """发过的名字：两层库里在的、用户库删掉过的、库里被 `from` 指着的。"""
        removed = self.user / REMOVED_FILE
        gone = removed.read_text(encoding="utf-8").split() if removed.is_file() else []
        parents = {wf.origin.name for wf in self.load_valid() if wf.origin}
        return {*self.names(), *gone, *parents}

    def derive(self, parent: str) -> dict[str, Any]:
        """从库里的一条派生：照抄它（标题、说明、阶段、画布坐标），名字与 `from` 由平台填。"""
        workflow = self.load(parent)
        if workflow is None:
            raise FileNotFoundError(
                f"库里没有叫 {parent!r} 的流程（有：{', '.join(self.names())}）")
        doc = yaml.safe_load(self.find(parent).read_text(encoding="utf-8"))
        doc["name"] = self.next_name(self.family(parent))
        doc["from"] = Origin(parent, workflow.content_hash()).to_dict()
        return doc

    def twin(self, workflow: Workflow) -> Workflow | None:
        """库里与它结构一模一样的另一条（不算它自己）；没有就是 None。"""
        mine = workflow.structure()
        for other in self.load_valid():
            if other.name != workflow.name and other.structure() == mine:
                return other
        return None

    # ── 给页面与终端 ────────────────────────────────────────────────────────
    def describe(self, catalog: dict[str, Capability],
                 skills: Collection[str] = ()) -> list[dict[str, Any]]:
        """清单：出厂在前、每条标 `shipped`；重名的、与另一条一模一样的带一句问题；每条带家族名，
        派生的带与父流程的差异。"""
        rows = describe_dir(self.shipped, catalog, skills, shipped=True)
        taken = self.shipped_names()
        for row in describe_dir(self.user, catalog, skills):
            if row["name"] in taken:
                row["problems"].append(f"与出厂的流程 {row['name']} 重名：改名或删掉这份")
            rows.append(row)
        by_name = {wf.name: wf for wf in self.load_valid()}
        for row in rows:
            workflow = by_name.get(row["name"])
            row["family"] = self.family(row["name"]) if workflow else row["name"]
            if workflow is None:
                continue
            twin = self.twin(workflow)
            # 一对一模一样的只报后到的那条：出厂的不报；有血缘的报子流程，没有的报后写的那条
            if twin and not row["shipped"] and (twin.name in taken or self._later(workflow, twin)):
                row["problems"].append(f"与 {twin.name} 一模一样（阶段、能力、参数、断点都相同）："
                                       "删掉一条")
            row.update(lineage(workflow, self, catalog))
        return rows

    def save(self, raw: dict[str, Any], catalog: dict[str, Capability], *,
             skills: Collection[str] = (), overwrite: bool = False,
             draft: bool = False) -> Workflow:
        """存进用户库。名字不给就由平台起：带 `from`（父流程的名字）是派生，叫 `<家族名>-<序号>`；
        都不带按标题起。名字是出厂的拒、结构与库里另一条一样的拒（FileExistsError 一族，409）。
        `draft`：流程助理 `workflow new` 先落盘一个起点（派生的照抄父流程、从零起的只有一个设计
        阶段）、再改文件——起点必然与库里某条一模一样，这一步不查重；没改出不同之前 `describe`
        一直把它标成问题（`show workflows` 退 1）。"""
        raw = dict(raw)
        origin = raw.get("from")
        if isinstance(origin, str):  # 页面只给父流程的名字：hash 由平台按它现在的样子填
            parent = self.load(origin)
            if parent is None:
                raise WorkflowInvalid(f"from {origin!r} 不在库里")
            raw["from"] = Origin(origin, parent.content_hash()).to_dict()
        if not raw.get("name"):
            raw["name"] = (self.next_name(self.family(raw["from"]["name"])) if raw.get("from")
                           else self.suggest_name(str(raw.get("title") or "")))
        name = raw["name"]
        if name in self.shipped_names():
            raise FileExistsError(f"{name} 是出厂的流程，不能改：换个名字另存")
        family = SEQ_RE.match(str(name))
        if not raw.get("from") and family and family["family"] in self._ever_named():
            raise WorkflowInvalid(
                f"{name} 看着像是 {family['family']} 派生的（<家族名>-<序号> 留给派生）："
                f"从零起的换个名字；要在 {family['family']} 上改，用 --from {family['family']}")
        twin = None if draft else self.twin(_shape(raw))
        if twin:
            raise DuplicateWorkflow(f"库里的 {twin.name} 和这条一模一样"
                                    "（阶段、能力、参数、断点都相同）：直接用它，或改一处再存")
        return save_workflow(self.user, raw, catalog, skills=skills, overwrite=overwrite)

    def _later(self, workflow: Workflow, other: Workflow) -> bool:
        """一对一模一样的里，`workflow` 是不是后到的那条：有血缘的子流程后到；没有的看文件谁后写
        （刚抄出来、刚改过的那条才是要动的），同时写的按名字。"""
        if workflow.origin and workflow.origin.name == other.name:
            return True
        if other.origin and other.origin.name == workflow.name:
            return False
        mine, theirs = self.find(workflow.name), self.find(other.name)
        stamp = (mine.stat().st_mtime_ns if mine else 0, workflow.name)
        return stamp > (theirs.stat().st_mtime_ns if theirs else 0, other.name)

    def remove(self, name: str) -> Path:
        """删用户库里的一条：出厂的拒（WorkflowInvalid），没有的 FileNotFoundError。
        取到工作区的实例是拷贝，不受影响。"""
        if name in self.shipped_names():
            raise WorkflowInvalid(
                f"{name} 是出厂的流程，不能删（出厂的：{sorted(self.shipped_names())}）")
        path = self.user / f"{name}.yaml"
        if not path.is_file():
            raise FileNotFoundError(f"库里没有叫 {name!r} 的流程")
        path.unlink()
        with (self.user / REMOVED_FILE).open("a", encoding="utf-8") as fh:
            fh.write(f"{name}\n")
        return path


def lineage(workflow: Workflow, library: Library,
            catalog: dict[str, Capability]) -> dict[str, Any]:
    """派生的流程（库里的、工作区的实例都一样）与父流程现在的样子比：差异几行人话、父流程在派生
    之后改过没有。从零拼的、父流程不在库里了的，差异为空。"""
    if workflow.origin is None:
        return {"diff": [], "parent_changed": False}
    parent = library.load(workflow.origin.name)
    if parent is None:
        return {"diff": [f"父流程 {workflow.origin.name} 不在库里了"], "parent_changed": False}
    return {"diff": diff(parent, workflow, catalog),
            "parent_changed": parent.content_hash() != workflow.origin.hash}


def diff(parent: Workflow, child: Workflow, catalog: dict[str, Capability]) -> list[str]:
    """两条流程的差异，一行一句人话：阶段与断点的增删按顺序对齐，同一个阶段里比挂的能力与参数。
    步骤用描述符的标题、参数用 label（P-21：机器名不上屏）；skill 的名字就是它的标题。"""
    def key(item: Stage | Stop) -> str:
        return item.stage if isinstance(item, Stage) else STOP

    def show(item: Stage | Stop) -> str:
        if isinstance(item, Stop):
            return f"断点「{item.note}」" if item.note else "断点"
        return f"阶段「{item.stage}」"

    out: list[str] = []
    a, b = parent.stages, child.stages
    matcher = difflib.SequenceMatcher(a=[key(x) for x in a], b=[key(x) for x in b], autojunk=False)
    for op, i1, i2, j1, j2 in matcher.get_opcodes():
        if op == "equal":
            for old, new in zip(a[i1:i2], b[j1:j2], strict=True):
                if isinstance(old, Stage) and isinstance(new, Stage):
                    out += _picks_diff(old, new, catalog)
            continue
        out += [f"去掉{show(x)}" for x in a[i1:i2]]
        out += [f"加了{show(x)}" for x in b[j1:j2]]
    return out


def _picks_diff(old: Stage, new: Stage, catalog: dict[str, Capability]) -> list[str]:
    def title(cap: str) -> str:
        return catalog[cap].title if cap in catalog else cap

    before = {p.cap: p.with_ for p in old.picks}
    after = {p.cap: p.with_ for p in new.picks}
    out = [f"「{new.stage}」加挂 {title(c)}" for c in after if c not in before]
    out += [f"「{new.stage}」不再挂 {title(c)}" for c in before if c not in after]
    for cap in (c for c in after if c in before and after[c] != before[c]):
        labels = {p.name: p.label for p in catalog[cap].params} if cap in catalog else {}
        for name in sorted({*before[cap], *after[cap]}):
            was, now = before[cap].get(name, "缺省"), after[cap].get(name, "缺省")
            if was != now:
                out.append(f"「{new.stage}」{title(cap)} 的{labels.get(name, name)}：{was} → {now}")
    return out


def _shape(raw: dict[str, Any]) -> Workflow:
    """查重只看结构：页面交来的映射先过一遍形状；坏的给一条空结构（对不上任何流程），原因交给
    save_workflow 报。"""
    try:
        return parse_workflow(f"{raw.get('name')}.yaml", raw)
    except WorkflowInvalid:
        return Workflow(name=str(raw.get("name")), title="", summary="")


def _stems(root: Path) -> list[str]:
    return sorted(p.stem for p in Path(root).glob("*.yaml")) if Path(root).is_dir() else []

