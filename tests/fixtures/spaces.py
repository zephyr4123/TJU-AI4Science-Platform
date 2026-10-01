"""测试里造项目与工作区：每个工作区都在项目里（纲领 P-15 改，外层 #136），缺省项目叫 `p`。

为什么不直接 `root.create(tmp_path / "workspaces", …)`：那是搬家前的布局，`project.of` 找不到项目，
对话、叫醒、跨工作区引用都走不通；测试要造的是真实的形状。
"""

from __future__ import annotations

from pathlib import Path

from framework.contracts.stages import STAGE_NAMES
from framework.workspace import project as project_mod
from framework.workspace.project import Project
from framework.workspace.root import Workspace

DEFAULT_PROJECT = "p"


def make_project(tmp_path: Path, project_id: str = DEFAULT_PROJECT, **kw) -> Project:
    """`<tmp_path>/projects/<id>/`；已经有就直接取。"""
    root = project_mod.projects_root(tmp_path)
    if (root / project_id / project_mod.MARKER).is_file():
        return project_mod.load(root / project_id)
    return project_mod.create(root, project_id, **kw)


def make_workspace(tmp_path: Path, ws_id: str = "w", *, project_id: str = DEFAULT_PROJECT,
                   **kw) -> Workspace:
    """项目 `p` 里的一个工作区（kw 原样递给 root.create：title / template）。"""
    return project_mod.new_workspace(make_project(tmp_path, project_id), ws_id, **kw)


def workspace_dir(tmp_path: Path, ws_id: str, project_id: str = DEFAULT_PROJECT) -> Path:
    """一个工作区在盘上的位置（不建）。"""
    return (tmp_path / project_mod.PROJECTS_DIRNAME / project_id / project_mod.WORKSPACES_DIRNAME
            / ws_id)


def give_flow(ws: Workspace, stages: str, name: str = "f") -> Path:
    """给工作区放一条流程实例：项目只装载流程上挂的能力（纲领 P-26），测试要跑步骤、要领域
    skill 进清单，就得先有流程。`stages` 是 YAML 的 stages 列表原文，
    如 `"  - 设计\n  - 实验: [petab]\n"`。"""
    ws.flows.mkdir(exist_ok=True)
    path = ws.flows / f"{name}.yaml"
    path.write_text(f"name: {name}\ntitle: 夹具\nsummary: 夹具\nstages:\n{stages}",
                    encoding="utf-8")
    return path


# 七个阶段都敞开、一个断点没有的流程：只为让步骤装载上（纲领 P-26），不测流程本身的测试用它
OPEN_STAGES = "".join(f"  - {name}\n" for name in STAGE_NAMES)


def open_flow(ws: Workspace) -> Path:
    return give_flow(ws, OPEN_STAGES, name="open")
