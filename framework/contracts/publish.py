"""发布记录：人在需求看板上确认「发布」以后留在盘上的东西，也是后面每颗能力开门前查的记录。

为什么要有它（外层 vision「产品形态：两个发布键、一次验收」）：流程往下走的许可在人手里，
不在 agent 手里。只改网页上的显示是假的——agent 调用的是命令，不看网页。所以发布
必须落到框架看得见的地方：发布负责写，框架负责查，查只写一次、所有能力共用。

签什么：`manifest.yaml` 与 `design.md`——人和 agent 聊出来的两个文件，目标、指标、预算、
「怎么算好」全在里面。任一文件在发布后改过，记录就失效，得重新发布；这样"发布"签的是
内容不是时间戳。不签 `data/`：数据改了 evaluate.py 重算出来的就是新数，那归 harness 的契约管。

在 contracts 层：只读写一个 JSON，不认识 run、不认识能力。
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from framework.contracts import packs

PUBLISH_NAME = "publish.json"
# 记录自己的版本：以后签的文件变了走迁移，不让旧记录静默失效（红线 6）
RECORD_FORMAT_VERSION = 1
SIGNED_FILES = (packs.MANIFEST_NAME, packs.BRIEF_NAME)


class PublishRefused(ValueError):
    """需求还没到能发布的样子：manifest 不合 schema、design.md 没写。信息给协调层看。"""


class NotPublished(ValueError):
    """能力开门前查记录没查到：没发布过，或发布后需求改了。信息里带着怎么办。"""


def publish_task(task_dir: Path, *, by: str) -> dict[str, Any]:
    """写 `<task_dir>/publish.json`，返回记录。人的确认；协调 agent 不该替人签（README 写明）。"""
    task_dir = Path(task_dir).resolve()
    if not by.strip():
        raise PublishRefused("发布要署名：--by <谁>，记在发布记录上")
    problems = packs.intake_problems(task_dir)
    if problems:
        raise PublishRefused("需求还不能发布：\n" + "\n".join(problems))
    return write_record(task_dir, by=by.strip())


def write_record(task_dir: Path, *, by: str) -> dict[str, Any]:
    """只写发布记录，不做检查：`publish_task` 检查完调它；测试夹具造"已发布的坏包"也调它。"""
    task_dir = Path(task_dir).resolve()
    record = {
        "format_version": RECORD_FORMAT_VERSION,
        "published_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "by": by,
        "files": {name: _sha256(task_dir / name) for name in SIGNED_FILES},
    }
    (task_dir / PUBLISH_NAME).write_text(
        json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return record


def require_published(task_dir: Path) -> dict[str, Any]:
    """能力的门：记录在、版本认得、签的文件一个都没改过。否则抛 `NotPublished`。"""
    task_dir = Path(task_dir).resolve()
    path = task_dir / PUBLISH_NAME
    how = f"ai4sci sign task {task_dir} --by <谁>"
    if not path.is_file():
        raise NotPublished(
            f"需求还没发布，不开：人看过需求看板（manifest.yaml、design.md）后 {how}")
    try:
        record = json.loads(path.read_text(encoding="utf-8"))
    except ValueError as exc:
        raise NotPublished(f"{PUBLISH_NAME} 不是合法 JSON（{exc}），重新发布：{how}") from exc
    if not isinstance(record, dict) or record.get("format_version") != RECORD_FORMAT_VERSION:
        raise NotPublished(
            f"{PUBLISH_NAME} 的 format_version 不是 {RECORD_FORMAT_VERSION}，重新发布：{how}")
    files = record.get("files")
    if not isinstance(files, dict):
        raise NotPublished(f"{PUBLISH_NAME} 缺 files，重新发布：{how}")
    for name in SIGNED_FILES:
        target = task_dir / name
        if not target.is_file():
            raise NotPublished(f"发布后 {name} 没了，重新发布：{how}")
        if files.get(name) != _sha256(target):
            raise NotPublished(
                f"发布后 {name} 改过了（发布记录里的校验和对不上）："
                f"需求变了就要人重新看一遍，{how}")
    return record


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()
