"""一段对话属于一个域：工作区（研究助理）或编辑台（流程助理）（纲领 P-16，外层 #73）。

域定六样东西：agent 的工作目录、对话存哪、能写哪些目录、工作目录之外能读哪些目录、平台自己要写的目录
（`paths.runtime_paths`，有沙箱的 CLI 要放行）、读哪份指南。
分权靠的是这里的白名单，不靠指南里的一句「请不要」：研究助理的可写目录是整个工作区（需求、原件、流程实例、
七个阶段的产出），库在它工作目录之外、只读（它要看着库里的流程与模板才能取来改成自己这份需求的）；
流程助理只能写库。服务端点按域分前缀，CLI 的 `chat` 按 `--studio` 或当前工作区选域；conversation.py
不认识域，只拿到目录。
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from framework import paths
from framework.chat import guide
from framework.workspace.root import Workspace

STUDIO_DIRNAME = "studio"
CHATS_DIRNAME = "chats"


@dataclass(frozen=True)
class Scope:
    kind: str
    cwd: Path
    chats: Path
    allowed_paths: tuple[Path, ...]
    readable_paths: tuple[Path, ...] = ()
    workspace: Workspace | None = None

    @property
    def runtime_paths(self) -> tuple[Path, ...]:
        return tuple(paths.runtime_paths())

    def system_prompt(self) -> str:
        return guide.system_prompt(self.kind)


def for_workspace(workspace: Workspace) -> Scope:
    """研究助理：工作目录就是工作区，能写整个工作区；流程的库与需求模板的库能读不能写。"""
    return Scope(guide.WORKSPACE, workspace.root, workspace.chats, (workspace.root,),
                 (paths.workflows_root(), paths.templates_root()), workspace)


def studio(home: Path) -> Scope:
    """流程助理：工作目录是库的上级，只能写库；对话存在数据根的 studio/ 下。"""
    library = paths.workflows_root()
    return Scope(guide.STUDIO, library.parent, Path(home) / STUDIO_DIRNAME / CHATS_DIRNAME,
                 (library,))
