"""一段对话属于一个域：工作区（研究助理）或编辑台（造流助理）（纲领 P-16，外层 #73）。

域定四样东西：agent 的工作目录、对话存哪、能写哪些目录、读哪份指南。分权靠的是这里的白名单，
不靠指南里的一句「请不要」：研究助理的可写目录全在工作区里，库在它工作目录之外；造流助理只能
写库。
服务端点按域分前缀，CLI 的 `chat` 按 `--studio` 或当前工作区选域；conversation.py 不认识域，
只拿到目录。
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from framework import paths
from framework.chat import guide
from framework.run.workspace import Workspace

STUDIO_DIRNAME = "studio"
CHATS_DIRNAME = "chats"


@dataclass(frozen=True)
class Scope:
    kind: str
    cwd: Path
    chats: Path
    allowed_paths: tuple[Path, ...]
    workspace: Workspace | None = None

    def system_prompt(self) -> str:
        return guide.system_prompt(self.kind)


def for_workspace(workspace: Workspace) -> Scope:
    """研究助理：工作目录就是工作区，能写需求、流实例与 run（journal），库在它够不着的地方。"""
    return Scope(guide.WORKSPACE, workspace.root, workspace.chats,
                 (workspace.task, workspace.flows, workspace.runs), workspace)


def studio(home: Path) -> Scope:
    """造流助理：工作目录是库的上级，只能写库；对话存在数据根的 studio/ 下。"""
    library = paths.workflows_root()
    return Scope(guide.STUDIO, library.parent, Path(home) / STUDIO_DIRNAME / CHATS_DIRNAME,
                 (library,))
