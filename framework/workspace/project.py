"""项目：一位助理的地盘（纲领 P-15 改，外层 #136）。

    projects/<p>/
    ├── project.md           目标：有它才算项目（标记就是它）；一级标题是项目名
    ├── materials/           几个工作区共用的原件
    ├── workspaces/<id>/     一份需求的家（root.py）
    └── .ai4sci/chats/       助理的对话（chat 层管里面）

主人 2026-09-22：真实的一个课题要几个工作区支撑——复现某个模块一个、写综述一个、跑实验一个、最后合成
一篇论文——它们的家是项目；一个项目一位助理，工作区是它的工位不是它的边界。
在工作区层：只是磁盘上的位置约定。找当前项目和找工作区一样：从 cwd 往上找 `project.md`，
`AI4SCI_PROJECT` 可以指定；工作区在项目里两级之下，拿着工作区就能找到它的项目（`of`）。
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from framework.workspace import root
from framework.workspace.root import ID_RE, Workspace

LOGGER = logging.getLogger("ai4sci.project")
MARKER = "project.md"
PROJECTS_DIRNAME = "projects"
WORKSPACES_DIRNAME = "workspaces"
MATERIALS_DIRNAME = "materials"
PLATFORM_DIRNAME = root.PLATFORM_DIRNAME
CHATS_DIRNAME = "chats"
PROJECT_ENV = "AI4SCI_PROJECT"


class ProjectNotFound(FileNotFoundError):
    """这里不是项目：没有 project.md。信息里带着怎么办。"""


class ProjectInvalid(ValueError):
    """id 不合规矩、或已经有同名的。"""


@dataclass(frozen=True)
class Project:
    root: Path

    @property
    def id(self) -> str:
        return self.root.name

    @property
    def marker(self) -> Path:
        return self.root / MARKER

    @property
    def materials(self) -> Path:
        return self.root / MATERIALS_DIRNAME

    @property
    def workspaces_dir(self) -> Path:
        return self.root / WORKSPACES_DIRNAME

    @property
    def platform(self) -> Path:
        return self.root / PLATFORM_DIRNAME

    @property
    def chats(self) -> Path:
        return self.platform / CHATS_DIRNAME

    def text(self) -> str:
        return self.marker.read_text(encoding="utf-8")

    def title(self) -> str:
        """project.md 的一级标题；没有就用 id。"""
        for line in self.text().splitlines():
            if line.startswith("# ") and line[2:].strip():
                return line[2:].strip()
        return self.id

    def goal(self) -> str:
        """project.md 一级标题下面第一段的第一行：页面上项目名底下那一句；没写就是空串。"""
        lines = iter(self.text().splitlines())
        for line in lines:
            if line.startswith("# "):
                break
        for line in lines:
            if line.strip():
                return line.strip()
        return ""

    def created_at(self) -> str:
        """什么时候起的：目录的 birthtime（macOS、Windows 与新内核的 Linux 都有）；文件系统不记
        就退到目录的 mtime——起项目之后目录只在加减工作区时变，够用。project.md 里不塞日期
        （P-13：文件就是接口）。"""
        stat = self.root.stat()
        stamp = getattr(stat, "st_birthtime", None) or stat.st_mtime
        return datetime.fromtimestamp(stamp, UTC).isoformat(timespec="seconds")

    def workspaces(self) -> list[Workspace]:
        return root.list_workspaces(self.workspaces_dir)

    def workspace(self, ws_id: str) -> Workspace:
        """按名字取项目里的一个工作区；不在就说清有哪些。名字先过规矩，`..` 之类到不了路径。"""
        if not ID_RE.fullmatch(ws_id):
            raise root.WorkspaceInvalid(f"工作区名只能是小写英文、数字、连字符，得到 {ws_id!r}")
        try:
            return root.load(self.workspaces_dir / ws_id)
        except root.WorkspaceNotFound:
            have = ", ".join(w.id for w in self.workspaces()) or "-"
            raise root.WorkspaceNotFound(
                f"项目 {self.id} 里没有工作区 {ws_id!r}（有：{have}）") from None

    def to_dict(self) -> dict[str, Any]:
        return {"id": self.id, "title": self.title(), "goal": self.goal(), "root": str(self.root),
                "created_at": self.created_at()}


def projects_root(home: Path) -> Path:
    return Path(home) / PROJECTS_DIRNAME


def create(projects_dir: Path, project_id: str, *, title: str = "", goal: str = "") -> Project:
    """起一个项目：建目录、写 project.md（一级标题 + 目标一段）。工作区另起（`new_workspace`）。"""
    if not ID_RE.fullmatch(project_id):
        raise ProjectInvalid(f"项目名只能是小写英文、数字、连字符，得到 {project_id!r}")
    directory = Path(projects_dir) / project_id
    if directory.exists():
        raise ProjectInvalid(f"已经有一个叫 {project_id!r} 的项目：{directory}")
    directory.mkdir(parents=True)
    (directory / MATERIALS_DIRNAME).mkdir()
    (directory / WORKSPACES_DIRNAME).mkdir()
    (directory / PLATFORM_DIRNAME).mkdir()
    body = f"# {title.strip() or project_id}\n"
    if goal.strip():
        body += f"\n{goal.strip()}\n"
    (directory / MARKER).write_text(body, encoding="utf-8")
    LOGGER.info("project_new id=%s root=%s", project_id, directory)
    return Project(directory.resolve())


def new_workspace(project: Project, ws_id: str, *, title: str = "",
                  template: str = "") -> Workspace:
    """在项目里起一个工作区（root.create 同一段代码，只是根定在项目的 workspaces/ 下）。"""
    return root.create(project.workspaces_dir, ws_id, title=title, template=template)


def load(path: Path) -> Project:
    path = Path(path).resolve()
    if not (path / MARKER).is_file():
        raise ProjectNotFound(f"不是项目（没有 {MARKER}）：{path}")
    return Project(path)


def find(start: Path | None = None) -> Project:
    """当前项目：`AI4SCI_PROJECT` 指定的，否则从 cwd 往上找 project.md。找不到就说清怎么办。"""
    override = os.environ.get(PROJECT_ENV)
    if override:
        return load(Path(override))
    origin = (Path.cwd() if start is None else Path(start)).resolve()
    for directory in (origin, *origin.parents):
        if (directory / MARKER).is_file():
            return Project(directory)
    raise ProjectNotFound(
        f"{origin} 不在任何项目里：cd 进 {PROJECTS_DIRNAME}/<id>/ 再跑，"
        f"或者 ai4sci project new <id> 起一个")


def of(workspace: Workspace) -> Project:
    """工作区所在的项目：上两级。老布局（工作区直接在 workspaces/ 下）不在任何项目里，先搬。"""
    try:
        return load(workspace.root.parent.parent)
    except ProjectNotFound:
        raise ProjectNotFound(
            f"工作区 {workspace.root} 不在任何项目里（上两级没有 {MARKER}）：这是搬家前的布局，"
            f"先把它搬进 {PROJECTS_DIRNAME}/<id>/{WORKSPACES_DIRNAME}/") from None


def list_projects(projects_dir: Path) -> list[Project]:
    directory = Path(projects_dir)
    if not directory.is_dir():
        return []
    return [Project(p.resolve()) for p in sorted(directory.iterdir()) if (p / MARKER).is_file()]
