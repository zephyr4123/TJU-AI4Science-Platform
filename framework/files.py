"""状态文件的原子写，全框架只此一处（`framework/README.md`「原子写与锁」）。

作业记录、对话的 meta、产出的 meta.yaml 与签字、需求的锁、库里的流程文件，都是一边写、另一边在
读：作业是子进程写、父进程与页面轮询着读；对话一轮跑着时页面在列对话。`write_text` 是先清空再写，
读的一方正好碰上就读到空的或半截的（外层 #204：发布门禁里真读到过空的作业记录）。这里先写同目录下
的临时文件，再 `os.replace` 换过去——同一个文件系统上是原子的，读的一方任何时候看到的都是完整的
旧版或新版；写到一半出错，临时文件删掉，原文件不动。

在 framework 顶层、不属于任何一层：哪一层写状态文件都用它，它只依赖标准库。
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path


def write_atomic(path: Path, text: str) -> None:
    """把 text 原子地写成 path。临时文件以点开头、`.tmp` 结尾：按扩展名扫目录的（`*.json`）
    不会扫到它。"""
    path = Path(path)
    # mkstemp 建的是 0600；换过去之前照原文件的权限（新文件按常见的 0644），不让写一次就改了权限
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
