"""checkpoint：续跑唯一认的那份状态，原子写。

单独一个模块的理由：读它的人（CLI 的 status、内环、续跑对账）比写它的人多得多，
跟建 run 的生命周期放在一起会让"只想看一眼状态"的调用方顺带拖进 shutil 与 yaml。

在 run 层，只依赖 layout。
"""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from framework.run import layout


def read_checkpoint(run_dir: Path) -> dict[str, Any]:
    return json.loads(layout.checkpoint(run_dir).read_text(encoding="utf-8"))


def write_checkpoint(run_dir: Path, data: dict[str, Any]) -> None:
    """先写 tmp 再 os.replace：断电时要么是旧的完整版本，要么是新的，没有半截。"""
    data = {**data, "updated_at": datetime.now(UTC).isoformat()}
    path = layout.checkpoint(run_dir)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, path)
