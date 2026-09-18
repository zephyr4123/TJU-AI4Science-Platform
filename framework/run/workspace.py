"""工作区：一份需求的家（纲领 P-15，外层 #70 #72）。

    workspaces/<id>/
    ├── workspace.yaml     标记：id、title、created_at；有它才算工作区
    ├── task/              需求 = 任务包（packs 管它合不合约；manifest 的 id 就是工作区名）
    ├── flows/             流实例：从库里取来、按这份需求改过的 <name>.yaml
    ├── chats/             主页面的对话
    ├── runs/              跑出来的 run
    └── jobs/              后台作业的记录与日志

在 run 层：它只是磁盘上的位置约定，不认识能力、不认识对话——上面各层拿着它找自己的目录。
找当前工作区的办法和 git 找 `.git` 一样：从 cwd 往上找标记文件，`AI4SCI_WORKSPACE` 可以指定。
agent 的工作目录就是工作区，所以它敲的命令一个路径都不带（P-14）。
"""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

LOGGER = logging.getLogger("ai4sci.workspace")
MARKER = "workspace.yaml"
WORKSPACES_DIRNAME = "workspaces"
TASK_DIRNAME = "task"
FLOWS_DIRNAME = "flows"
CHATS_DIRNAME = "chats"
RUNS_DIRNAME = "runs"
JOBS_DIRNAME = "jobs"
WORKSPACE_ENV = "AI4SCI_WORKSPACE"
# 目录名就是 id，也是 manifest 的 id：小写英文、数字、连字符（与工作流名同一规矩）
ID_RE = re.compile(r"[a-z][a-z0-9-]*")


class WorkspaceNotFound(FileNotFoundError):
    """这里不是工作区：没有标记文件。信息里带着怎么办。"""


class WorkspaceInvalid(ValueError):
    """id 不合规矩、或已经有同名的。"""


@dataclass(frozen=True)
class Workspace:
    root: Path

    @property
    def id(self) -> str:
        return self.root.name

    @property
    def task(self) -> Path:
        return self.root / TASK_DIRNAME

    @property
    def flows(self) -> Path:
        return self.root / FLOWS_DIRNAME

    @property
    def chats(self) -> Path:
        return self.root / CHATS_DIRNAME

    @property
    def runs(self) -> Path:
        return self.root / RUNS_DIRNAME

    @property
    def jobs(self) -> Path:
        return self.root / JOBS_DIRNAME

    def meta(self) -> dict[str, Any]:
        raw = yaml.safe_load((self.root / MARKER).read_text(encoding="utf-8"))
        assert isinstance(raw, dict) and raw.get("id") == self.id, (
            f"{self.root / MARKER} 的 id 与目录名对不上：{raw!r}")
        return raw

    def to_dict(self) -> dict[str, Any]:
        meta = self.meta()
        return {"id": self.id, "title": meta.get("title") or self.id,
                "created_at": meta.get("created_at"), "root": str(self.root)}


def workspaces_root(home: Path) -> Path:
    return Path(home) / WORKSPACES_DIRNAME


def create(root: Path, ws_id: str, *, title: str = "") -> Workspace:
    """起一个工作区：建目录、写标记。任务包由 `cap init` 之后再放，这里不动它。"""
    if not ID_RE.fullmatch(ws_id):
        raise WorkspaceInvalid(f"工作区名只能是小写英文、数字、连字符，得到 {ws_id!r}")
    directory = Path(root) / ws_id
    if directory.exists():
        raise WorkspaceInvalid(f"已经有一个叫 {ws_id!r} 的工作区：{directory}")
    directory.mkdir(parents=True)
    doc = {"id": ws_id, "title": title.strip() or ws_id,
           "created_at": datetime.now(UTC).isoformat(timespec="seconds")}
    (directory / MARKER).write_text(yaml.safe_dump(doc, allow_unicode=True, sort_keys=False),
                                    encoding="utf-8")
    LOGGER.info("workspace_new id=%s root=%s", ws_id, directory)
    return Workspace(directory.resolve())


def load(root: Path) -> Workspace:
    root = Path(root).resolve()
    if not (root / MARKER).is_file():
        raise WorkspaceNotFound(f"不是工作区（没有 {MARKER}）：{root}")
    return Workspace(root)


def find(start: Path | None = None) -> Workspace:
    """当前工作区：`AI4SCI_WORKSPACE` 指定的，否则从 cwd 往上找标记文件。找不到就说清怎么办。"""
    override = os.environ.get(WORKSPACE_ENV)
    if override:
        return load(Path(override))
    origin = (Path.cwd() if start is None else Path(start)).resolve()
    for directory in (origin, *origin.parents):
        if (directory / MARKER).is_file():
            return Workspace(directory)
    raise WorkspaceNotFound(
        f"{origin} 不在任何工作区里：cd 进 {WORKSPACES_DIRNAME}/<id>/ 再跑，"
        f"或者 ai4sci workspace new <id> 起一个")


def list_workspaces(root: Path) -> list[Workspace]:
    root = Path(root)
    if not root.is_dir():
        return []
    return [Workspace(p.resolve()) for p in sorted(root.iterdir()) if (p / MARKER).is_file()]
