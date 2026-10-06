"""状态文件的原子写，全框架只此一处（`framework/README.md`「原子写与锁」）。

作业记录、对话的 meta、产出的 meta.yaml 与签字、需求的锁、库里的流程文件，都是一边写、另一边在
读：作业是子进程写、父进程与页面轮询着读；对话一轮跑着时页面在列对话。`write_text` 是先清空再写，
读的一方正好碰上就读到空的或半截的（外层 #204：发布门禁里真读到过空的作业记录）。这里先写同目录下
的临时文件，再 `os.replace` 换过去——同一个文件系统上是原子的，读的一方任何时候看到的都是完整的
旧版或新版；写到一半出错，临时文件删掉，原文件不动。

边跑边追加的进度（能力的 `progress.jsonl`，外层 #242）也在这里：一行一个事件，能力的 Python 程序
在它本来就打日志的地方顺手写一行，页面边跑边读、照这个能力自己的面板画。只追加、不改写，所以不走
临时文件：整行一次写进去，进程内一把锁挡住几个线程交错；读的一方碰上正在写的最后一行，丢掉它就是。

在 framework 顶层、不属于任何一层：哪一层写状态文件都用它，它只依赖标准库。
"""

from __future__ import annotations

import json
import os
import tempfile
import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

_APPEND = threading.Lock()


def write_atomic(path: Path, text: str, mode: int | None = None) -> None:
    """把 text 原子地写成 path。临时文件以点开头、`.tmp` 结尾：按扩展名扫目录的（`*.json`）
    不会扫到它。`mode` 给了就用它（key 文件 0600，外层 #263），不给照原文件。"""
    path = Path(path)
    # mkstemp 建的是 0600；换过去之前照原文件的权限（新文件按常见的 0644），不让写一次就改了权限
    if mode is None:
        mode = path.stat().st_mode & 0o777 if path.exists() else 0o644
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(text)
        os.chmod(tmp, mode)
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def append_event(path: Path, **fields: Any) -> None:
    """往 path 末尾追加一行事件：`at` 是此刻（UTC，到秒），其余是调用方给的字段。"""
    line = json.dumps({"at": datetime.now(UTC).isoformat(timespec="seconds"), **fields},
                      ensure_ascii=False) + "\n"
    with _APPEND, Path(path).open("a", encoding="utf-8") as handle:
        handle.write(line)
