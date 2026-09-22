"""测试里造项目与工作区：每个工作区都在项目里（纲领 P-15 改，外层 #136），缺省项目叫 `p`。

为什么不直接 `root.create(tmp_path / "workspaces", …)`：那是搬家前的布局，`project.of` 找不到项目，
对话、叫醒、跨工作区引用都走不通；测试要造的是真实的形状。
"""

from __future__ import annotations

from pathlib import Path

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
