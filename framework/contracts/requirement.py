"""需求：工作区的根文件 `requirement.md` 与人的确认 `requirement.lock`（纲领 P-19）。

需求是助理和人对话攒出来的一份 markdown，形式开放：库里有模板（通用一份、按学科加），助理照模板
起草，大纲不定死——框架只认两样东西：
  - 一级标题是课题的标题（工作区的 title 就从这儿读，没有就用目录名）；
  - 二级标题各是一格，页面照它们渲染成看板；正文里还剩「待填」的格是空格子。

确认是**唯一内置的门**：没确认任何阶段不开工。lock 记谁、何时、第几版、签的是哪份内容的 sha256；
确认之后再改文件，hash 对不上就是「有改动未确认」——所有阶段照样不开工，页面显示 diff，
人再确认一次成下一版。每版确认时的原文存一份在 `.ai4sci/requirement/v<n>.md`，diff 就是它对现文件。

在契约层：只读写这两个文件与历史目录，不认识阶段、能力、对话。
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

FILE_NAME = "requirement.md"
LOCK_NAME = "requirement.lock"
# 模板里没定的值都写它；确认前看到它就不给签，模板不能被当成需求签走
PLACEHOLDER = "待填"
PLATFORM_DIRNAME = ".ai4sci"
HISTORY_DIRNAME = "requirement"
_H1_RE = re.compile(r"^#\s+(.+?)\s*$", re.MULTILINE)
_H2_RE = re.compile(r"^##\s+(.+?)\s*$", re.MULTILINE)


class NotConfirmed(ValueError):
    """需求没确认（从没确认过，或确认后改了）：任何阶段都不开工。信息里说清怎么办。"""


class ConfirmRefused(ValueError):
    """这份需求现在不能确认：还有「待填」、文件空着、或内容与上一版一样。"""


@dataclass(frozen=True)
class Section:
    heading: str
    body: str
    pending: bool

    def to_dict(self) -> dict[str, Any]:
        return {"heading": self.heading, "body": self.body, "pending": self.pending}


def path(root: Path) -> Path:
    return Path(root) / FILE_NAME


def lock_path(root: Path) -> Path:
    return Path(root) / LOCK_NAME


def history_dir(root: Path) -> Path:
    return Path(root) / PLATFORM_DIRNAME / HISTORY_DIRNAME


def read(root: Path) -> str:
    return path(root).read_text(encoding="utf-8")


def title(text: str, fallback: str) -> str:
    """第一个一级标题；没有就用 fallback（目录名）。"""
    match = _H1_RE.search(text)
    return match.group(1).strip() if match else fallback


def sections(text: str) -> list[Section]:
    """按二级标题切格；标题之前的引言不算格。一格空着或还带「待填」就是 pending。"""
    heads = list(_H2_RE.finditer(text))
    out: list[Section] = []
    for i, match in enumerate(heads):
        end = heads[i + 1].start() if i + 1 < len(heads) else len(text)
        body = text[match.end():end].strip()
        out.append(Section(match.group(1).strip(), body, not body or PLACEHOLDER in body))
    return out


def sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def read_lock(root: Path) -> dict[str, Any] | None:
    lock = lock_path(root)
    if not lock.is_file():
        return None
    doc = json.loads(lock.read_text(encoding="utf-8"))
    for key in ("version", "by", "confirmed_at", "sha256"):
        if key not in doc:
            raise ValueError(f"{lock} 缺 {key}，不是一份确认记录")
    return doc


def status(root: Path) -> dict[str, Any]:
    """页面与 `show workspace` 用的一份状态：confirmed / version / by / at / dirty。

    dirty：确认过、但现在的文件与签的内容不一样——有改动未确认。文件不在也算 dirty 不算 missing：
    lock 还在，说明有人确认过一份现在不见了的需求。"""
    lock = read_lock(root)
    if lock is None:
        return {"confirmed": False, "version": None, "by": None, "at": None, "dirty": False}
    current = sha256(read(root)) if path(root).is_file() else None
    return {"confirmed": True, "version": lock["version"], "by": lock["by"],
            "at": lock["confirmed_at"], "dirty": current != lock["sha256"]}


def confirm(root: Path, *, by: str) -> dict[str, Any]:
    """人确认当前这份需求：写 lock、存一份原文进历史。协调 agent 不该替人做这件事。"""
    by = by.strip()
    if not by:
        raise ConfirmRefused("确认要署名：--by <谁>")
    if not path(root).is_file():
        raise ConfirmRefused(f"没有 {FILE_NAME}，先和助理把需求写出来")
    text = read(root)
    if not text.strip():
        raise ConfirmRefused(f"{FILE_NAME} 是空的，先和助理把需求写出来")
    if PLACEHOLDER in text:
        raise ConfirmRefused(f"{FILE_NAME} 里还有「{PLACEHOLDER}」没填：模板不能当需求确认")
    previous = read_lock(root)
    digest = sha256(text)
    if previous is not None and previous["sha256"] == digest:
        raise ConfirmRefused(f"这份需求已经确认过了（v{previous['version']}），内容没变")
    version = 1 if previous is None else int(previous["version"]) + 1
    record = {"version": version, "by": by,
              "confirmed_at": datetime.now(UTC).isoformat(timespec="seconds"), "sha256": digest}
    history = history_dir(root)
    history.mkdir(parents=True, exist_ok=True)
    (history / f"v{version}.md").write_text(text, encoding="utf-8")
    lock_path(root).write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n",
                               encoding="utf-8")
    return record


def confirmed_text(root: Path) -> str | None:
    """上一次确认时的原文（历史目录里那份）；从没确认过是 None。页面拿它和现文件做 diff。"""
    lock = read_lock(root)
    if lock is None:
        return None
    archived = history_dir(root) / f"v{lock['version']}.md"
    if not archived.is_file():
        raise FileNotFoundError(f"需求 v{lock['version']} 的存档不在：{archived}")
    return archived.read_text(encoding="utf-8")


def require_confirmed(root: Path) -> int:
    """开工前的门：返回确认的版本号；没确认或有改动未确认就抛，信息里说清怎么办。"""
    state = status(root)
    if not state["confirmed"]:
        raise NotConfirmed("需求还没确认：先和研究者把 requirement.md 写好，由研究者在页面上确认"
                           "（终端里是 ai4sci requirement confirm）")
    if state["dirty"]:
        raise NotConfirmed(f"需求 v{state['version']} 确认之后又改过，改动还没确认："
                           "研究者看过 diff 再确认一次，阶段才能开工")
    return int(state["version"])
