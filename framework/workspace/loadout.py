"""一个项目装载哪些能力（纲领 P-26）：读取点只在这里。

项目里的会话——研究助理、执行层——装的是同一套：本项目各工作区流程实例（`flows/*.yaml`）上挂的能力，
加平台自带的常驻 skill。不按阶段、工作区再往里切，也不往外放到整个库。

- **skill**：常驻的，加流程格子上点了名、在三处库里找得到的。挂着却不可用的（不合格、重名）进
  `unavailable` 带原因，清单里单列一行——不静默丢。
- **步骤**：流程格子上点了名的，或流程里有一格这个阶段没点名任何步骤（只挂 skill、或什么都没挂：
  「这个阶段用什么由助理看着办」）时这个阶段的步骤。步骤的名字与阶段在能力层（描述符），这一层不
  认识：判定（`allows_step`）与拼错的名字（`strays`，既不是 skill 也不是步骤）都要调用方给出步骤
  名集——知道它的是 cli 与研究助理的清单；执行层的清单不摆拼错的名字（改流程不是它的事）。
- **站在哪**：`around` 按路径所在的项目算（盘上的事实，不看 `AI4SCI_PROJECT`，执行层的清单就按
  它）；`here` 是命令站的地方——cwd 在项目里就按它，不在才看环境变量，都不在是 None（看全库）。

每次现算，不缓存：流程实例改了，下一条命令就按新的来。读不出来的流程文件进 `unavailable`，
它点名的东西不装——坏在哪由 `show flows` 报。
"""

from __future__ import annotations

import logging
from collections.abc import Collection
from dataclasses import dataclass
from pathlib import Path

from framework.contracts import workflows
from framework.contracts.workflows import Stage
from framework.skills import library
from framework.skills.library import Skill
from framework.workspace import project as project_mod
from framework.workspace.project import Project, ProjectNotFound

LOGGER = logging.getLogger("ai4sci.loadout")
STRAY = ("流程上挂着，可库里没有这个 skill、也没有这个步骤：拼错了？"
         "ai4sci show skills <词> 查，改 flows/<流程>.yaml")


@dataclass(frozen=True)
class Loadout:
    skills: tuple[Skill, ...]
    unavailable: tuple[tuple[str, str], ...]  # (名字, 原因)：挂着却用不了的、读不出来的流程
    cells: tuple[tuple[str, frozenset[str]], ...]  # 每一格：(阶段, 点了名的非 skill 名字)

    def has_skill(self, name: str) -> bool:
        return any(s.name == name for s in self.skills)

    def allows_step(self, name: str, stage: str, steps: Collection[str]) -> bool:
        """点了名，或这个阶段有一格没点名任何步骤（拼错的名字不算点名，不把阶段关上）。"""
        return any(name in names for _, names in self.cells) or any(
            cell == stage and not any(n in steps for n in names) for cell, names in self.cells)

    def strays(self, steps: Collection[str]) -> tuple[tuple[str, str], ...]:
        """格子上既不是 skill 也不是步骤的名字，与 `unavailable` 同形（名字, 原因）。"""
        names = sorted({n for _, names in self.cells for n in names} - set(steps))
        return tuple((name, STRAY) for name in names)


def around(path: Path) -> Loadout:
    """路径（产出目录、工作区）所在的项目装载的那套：执行层的会话按它拼清单。"""
    return of(project_mod.containing(path))


def here() -> Loadout | None:
    """命令站的地方装载的那套：cwd 所在的项目（与执行层的清单同一口径），cwd 不在项目里才看
    `AI4SCI_PROJECT`；都没有是 None——不在任何项目里，看全库。"""
    for locate in (lambda: project_mod.containing(Path.cwd()), project_mod.find):
        try:
            return of(locate())
        except ProjectNotFound:
            continue
    return None


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
    cells = tuple((item.stage, frozenset(p.cap for p in item.picks if not is_skill[p.cap]))
                  for item in stages)
    loadout = Loadout(tuple(skills), tuple(unavailable), cells)
    LOGGER.debug("loadout project=%s skills=%d unavailable=%d", project.id, len(skills),
                  len(unavailable))
    return loadout
