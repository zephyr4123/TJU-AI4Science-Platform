"""与后端无关的文件改动取证：调用前后各拍一次快照，diff 说话。

为什么不用 CLI 自报的 tool_use 事件：那是执行层自己的说法，而执行层正是被审的对象
（P-2）。它可以经 Bash 改文件、可以改完再改回去、也可以在事件流里少报一条。
sha256 快照是确定性的、与后端无关的，换成 Codex 也照用。
"""

from __future__ import annotations

import hashlib
from pathlib import Path

# 快照忽略的目录：`.git` 是状态载体（runner 自己在提交，不算执行层改的），
# `.ai4sci` 是本适配器自己写的事件流日志——不排掉的话每次 run 都会把自己的日志报成改动。
IGNORED_DIRS = frozenset({".git", ".ai4sci", "__pycache__"})

_CHUNK = 1 << 20


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        while chunk := fh.read(_CHUNK):
            digest.update(chunk)
    return digest.hexdigest()


def snapshot(root: Path) -> dict[str, str]:
    """root 下所有普通文件的 {相对路径: sha256}。

    符号链接按 `is_file()` 会跟随，这里显式跳过：跟随会让指向 root 外的链接混进快照，
    也会在坏链接上抛 OSError。链接本身变没变不在本次取证范围内。
    """
    out: dict[str, str] = {}
    for path in sorted(root.rglob("*")):
        if any(part in IGNORED_DIRS for part in path.relative_to(root).parts):
            continue
        if path.is_symlink() or not path.is_file():
            continue
        out[path.relative_to(root).as_posix()] = _sha256(path)
    return out


def diff(before: dict[str, str], after: dict[str, str]) -> list[str]:
    """新增、删除、内容变了的相对路径，排序返回。

    删除也算改动：执行层把 harness 删掉和把 harness 改掉一样要判 crash。
    """
    changed = {p for p in before.keys() | after.keys() if before.get(p) != after.get(p)}
    return sorted(changed)
