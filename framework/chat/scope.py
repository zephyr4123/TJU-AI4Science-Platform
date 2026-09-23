"""一段对话属于一个域：项目（研究助理）或编辑台（流程助理）（纲领 P-16，外层 #73 #136）。

域定五样东西：agent 的工作目录、对话存哪、能写哪些目录、工作目录之外能读哪些目录、读哪份指南。
分权靠的是这里的白名单，不靠指南里的一句「请不要」：研究助理站在项目里，可写目录是整个项目（共用原件、
每个工作区的需求、原件、流程实例、七个阶段的产出），库在它工作目录之外、只读（它要看着库里的流程与模板
才能取来改成自己这份需求的）；流程助理站在数据根的 `studio/` 里，只能写人存的那层库
`studio/workflows/`，出厂的 `workflows/` 对它也只读（外层 #149）。服务端点按域分前缀，CLI 的 `chat`
按 `--studio` 或当前项目选域；conversation.py 不认识域，只拿到目录。
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from backends import Chat
from framework import paths
from framework.chat import guide
from framework.workspace.project import Project

CHATS_DIRNAME = "chats"


@dataclass(frozen=True)
class Scope:
    kind: str
    cwd: Path
    chats: Path
    allowed_paths: tuple[Path, ...]
    readable_paths: tuple[Path, ...] = ()
    project: Project | None = None

    def system_prompt(self, chat: Chat | None = None) -> str:
        """这个域的指南；给了适配器就带上它自己的「工具怎么用」那段。"""
        tool = chat.tool_guide(guide.bash_rules(self.kind)) if chat is not None else ""
        return guide.system_prompt(self.kind, tool_guide=tool)


def for_project(project: Project) -> Scope:
    """研究助理：工作目录就是项目，能写整个项目（全部工作区）；流程库的两层与需求模板的库能读不能写。"""
    return Scope(guide.PROJECT, project.root, project.chats, (project.root,),
                 (paths.workflows_root(), paths.user_workflows_root(), paths.templates_root()),
                 project)


def studio(home: Path) -> Scope:
    """流程助理：工作目录是数据根的 studio/，只能写里面的 workflows/（人存的流程）；出厂的库只读；
    对话存在旁边的 studio/chats/。"""
    mine = paths.user_workflows_root(home)
    return Scope(guide.STUDIO, mine.parent, mine.parent / CHATS_DIRNAME, (mine,),
                 (paths.workflows_root(),))
