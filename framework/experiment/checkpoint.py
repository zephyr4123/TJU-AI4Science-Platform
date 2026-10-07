"""checkpoint：续跑唯一认的那份状态，原子写。

单独一个模块的理由：读它的人（CLI 的 status、内环、续跑对账）比写它的人多得多，
跟建 run 的生命周期放在一起会让"只想看一眼状态"的调用方顺带拖进 shutil 与 yaml。

在实验族的共享层，只依赖 layout。
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from framework.experiment import layout
from framework.files import read_text, write_atomic


def read_checkpoint(run_dir: Path) -> dict[str, Any]:
    return json.loads(read_text(layout.checkpoint(run_dir)))


def write_checkpoint(run_dir: Path, data: dict[str, Any]) -> None:
    """原子写（`framework/files.py`）：断电时要么是旧的完整版本，要么是新的，没有半截。"""
    data = {**data, "updated_at": datetime.now(UTC).isoformat()}
    write_atomic(layout.checkpoint(run_dir), json.dumps(data, ensure_ascii=False, indent=2))
