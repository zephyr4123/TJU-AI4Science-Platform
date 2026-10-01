"""一个项目装载哪些能力（纲领 P-26）：读取点只在这里。

项目里的会话——研究助理、执行层——装的是同一套：本项目各工作区流程实例（`flows/*.yaml`）上挂的能力，
加平台自带的常驻 skill。不按阶段、工作区再往里切，也不往外放到整个库。

- **skill**：常驻的，加流程格子上点了名、在三处库里找得到的。挂着却不可用的（不合格、重名）进
  `unavailable` 带原因，清单里单列一行——不静默丢。
- **步骤**：流程格子上点了名的，或流程里出现了这个阶段而没点名（「这个阶段用什么由助理看着办」）时
  这个阶段的步骤。步骤的名字与阶段在能力层（描述符），这一层不认识，只给出名字集与敞开的阶段，
  判定在 `allows_step`。

每次现算，不缓存：流程实例改了，下一条命令就按新的来。读不出来的流程文件进 `unavailable`，
它点名的东西不装——坏在哪由 `show flows` 报。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

from framework.contracts import workflows
from framework.contracts.workflows import Stage
from framework.skills import library
from framework.skills.library import Skill
from framework.workspace import project as project_mod
from framework.workspace.project import Project

LOGGER = logging.getLogger("ai4sci.loadout")


@dataclass(frozen=True)
class Loadout:
    skills: tuple[Skill, ...]
    unavailable: tuple[tuple[str, str], ...]  # (名字, 原因)：挂着却用不了的、读不出来的流程
    named: frozenset[str]  # 流程格子上点了名的全部名字（步骤与 skill 混在一起，按名字分辨）
    open_stages: frozenset[str]  # 流程里出现过、没点名的阶段：这些阶段的步骤都装载

    def has_skill(self, name: str) -> bool:
        return any(s.name == name for s in self.skills)

    def allows_step(self, name: str, stage: str) -> bool:
        return name in self.named or stage in self.open_stages


def around(path: Path) -> Loadout:
    """路径（产出目录、工作区）所在的项目装载的那套：执行层的会话按它拼清单。"""
    return of(project_mod.containing(path))


def of(project: Project) -> Loadout:
    stages: list[Stage] = []
    unavailable: list[tuple[str, str]] = []
    for ws in project.workspaces():
        for path in sorted(ws.flows.glob("*.yaml")) if ws.flows.is_dir() else []:
            try:
                flow = workflows.load_workflow(path)
            except workflows.WorkflowInvalid as exc:
                unavailable.append((f"{ws.id}/flows/{path.name}", f"流程文件读不出来：{exc}"))
                continue
            stages += [item for item in flow.stages if isinstance(item, Stage)]
    resident = library.resident()
    skills = list(resident.skills)
    unavailable += [(bad.name, "；".join(bad.problems)) for bad in resident.invalid]
    # 格子上的名字是不是 skill 看库里有没有这个目录（合格不合格都算）：不是 skill 的就是步骤的名字，
    # 形状对不对由 show flows 查
    is_skill: dict[str, bool] = {s.name: True for s in skills}
    for name in dict.fromkeys(p.cap for item in stages for p in item.picks):
        if name in is_skill:
            continue
        try:
            skills.append(library.find(name))
            is_skill[name] = True
        except library.SkillNotFound:
            is_skill[name] = False
        except library.SkillInvalid as exc:
            unavailable.append((name, str(exc).replace("\n", "；")))
            is_skill[name] = True
    # 一格只挂了 skill 不算点名步骤（那是这一步推荐的工具，`workflows.matching_step` 同一个口径）：
    # 这个阶段照样敞开
    open_stages = {item.stage for item in stages
                   if not any(not is_skill[p.cap] for p in item.picks)}
    named = frozenset(p.cap for item in stages for p in item.picks)
    loadout = Loadout(tuple(skills), tuple(unavailable), named, frozenset(open_stages))
    LOGGER.debug("loadout project=%s skills=%d unavailable=%d", project.id, len(skills),
                  len(unavailable))
    return loadout
