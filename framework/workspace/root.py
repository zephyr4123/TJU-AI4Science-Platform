"""工作区：一份需求的家（纲领 P-15、P-19，外层 #70 #104 #136）。

    projects/<p>/workspaces/<id>/
    ├── requirement.md       需求：有它才算工作区（标记就是它）；一级标题是课题标题
    ├── requirement.lock     人的确认（contracts.requirement）
    ├── materials/           原件：PDF / 数据 / 代码，只增不改
    ├── flows/               流程实例：从库里取来、按这份需求改过的 <name>.yaml，几条都行
    ├── literature/ hypothesis/ design/ experiment/ analysis/ writing/ verification/
    │                        七个阶段各一个目录（英文 slug），每次产出一个子目录 <stage>/<n>/；
    流程没走的阶段没有目录
    └── .ai4sci/             平台自己的记录，不是研究产物：jobs/ logs/ requirement/
    （每版确认的存档）。对话不在这儿：对话归项目（project.py）

在工作区层：它只是磁盘上的位置约定，不认识能力、不认识对话——上面各层拿着它找自己的目录。
工作区总在一个项目里（一个项目一位助理，工作区是它的工位）；助理站在项目里，工作区级的命令带
`--ws <id>` 点名；人在终端、执行层在产出目录里则和 git 找 `.git` 一样从 cwd 往上找
`requirement.md`（`find`）。
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from framework.contracts import requirement
from framework.contracts.stages import STAGE_SLUGS

LOGGER = logging.getLogger("ai4sci.workspace")
MARKER = requirement.FILE_NAME
MATERIALS_DIRNAME = "materials"
FLOWS_DIRNAME = "flows"
PLATFORM_DIRNAME = requirement.PLATFORM_DIRNAME
JOBS_DIRNAME = "jobs"
LOGS_DIRNAME = "logs"
# 目录名就是 id：小写英文、数字、连字符（与流程名同一规矩）
ID_RE = re.compile(r"[a-z][a-z0-9-]*")


class WorkspaceNotFound(FileNotFoundError):
    """这里不是工作区：没有 requirement.md。信息里带着怎么办。"""


class WorkspaceInvalid(ValueError):
    """id 不合规矩、或已经有同名的。"""


@dataclass(frozen=True)
class Workspace:
    root: Path

    @property
    def id(self) -> str:
        return self.root.name

    @property
    def requirement(self) -> Path:
        return requirement.path(self.root)

    @property
    def materials(self) -> Path:
        return self.root / MATERIALS_DIRNAME

    @property
    def flows(self) -> Path:
        return self.root / FLOWS_DIRNAME

    @property
    def platform(self) -> Path:
        return self.root / PLATFORM_DIRNAME

    @property
    def jobs(self) -> Path:
        return self.platform / JOBS_DIRNAME

    @property
    def logs(self) -> Path:
        return self.platform / LOGS_DIRNAME

    def stage_dir(self, slug: str) -> Path:
        assert slug in STAGE_SLUGS, f"不是阶段目录：{slug!r}"
        return self.root / slug

    def stage_dirs(self) -> list[Path]:
        """七个阶段里盘上已经有目录的那几个，按固定序（P-19：流程没走的阶段没有目录）。"""
        return [self.root / slug for slug in STAGE_SLUGS if (self.root / slug).is_dir()]

    def title(self) -> str:
        return requirement.title(requirement.read(self.root), self.id)

    def to_dict(self) -> dict[str, Any]:
        return {"id": self.id, "title": self.title(), "root": str(self.root),
                "requirement": requirement.status(self.root)}


def create(root: Path, ws_id: str, *, title: str = "", template: str = "") -> Workspace:
    """起一个工作区：建目录、写需求的初稿（模板 + 标题）。阶段目录等流程走到再建。
    `root` 是项目的 workspaces/ 目录（project.new_workspace 传进来）。

    `template` 是模板原文（`templates/<name>.md`），第一个一级标题换成课题标题；没给模板就只写标题。
    """
    if not ID_RE.fullmatch(ws_id):
        raise WorkspaceInvalid(f"工作区名只能是小写英文、数字、连字符，得到 {ws_id!r}")
    directory = Path(root) / ws_id
    if directory.exists():
        raise WorkspaceInvalid(f"已经有一个叫 {ws_id!r} 的工作区：{directory}")
    directory.mkdir(parents=True)
    (directory / MATERIALS_DIRNAME).mkdir()
    (directory / FLOWS_DIRNAME).mkdir()
    (directory / PLATFORM_DIRNAME).mkdir()
    (directory / MARKER).write_text(_first_draft(title.strip() or ws_id, template),
                                    encoding="utf-8")
    LOGGER.info("workspace_new id=%s root=%s", ws_id, directory)
    return Workspace(directory.resolve())


def _first_draft(title: str, template: str) -> str:
    """模板的一级标题换成课题标题；模板没有一级标题就在开头加一个。"""
    text = template.strip()
    if not text:
        return f"# {title}\n"
    lines = text.split("\n")
    for i, line in enumerate(lines):
        if line.startswith("# "):
            lines[i] = f"# {title}"
            return "\n".join(lines) + "\n"
    return f"# {title}\n\n" + text + "\n"


def load(root: Path) -> Workspace:
    root = Path(root).resolve()
    if not (root / MARKER).is_file():
        raise WorkspaceNotFound(f"不是工作区（没有 {MARKER}）：{root}")
    return Workspace(root)


def find(start: Path | None = None) -> Workspace:
    """当前工作区：从 cwd 往上找 requirement.md（人在终端、执行层在产出目录里）。找不到就说清
    怎么办；
    站在项目里的助理不靠这个，靠命令上的 `--ws`（cli._common.current_workspace）。"""
    origin = (Path.cwd() if start is None else Path(start)).resolve()
    for directory in (origin, *origin.parents):
        if (directory / MARKER).is_file():
            return Workspace(directory)
    raise WorkspaceNotFound(
        f"{origin} 不在任何工作区里：命令上带 --ws <工作区名>，或 cd 进 workspaces/<id>/ 再跑")


def list_workspaces(root: Path) -> list[Workspace]:
    root = Path(root)
    if not root.is_dir():
        return []
    return [Workspace(p.resolve()) for p in sorted(root.iterdir()) if (p / MARKER).is_file()]
