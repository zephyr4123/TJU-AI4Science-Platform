"""正文从 stdin 喂给 CLI：两家适配器共用（外层 #210）。

不放命令行：Windows 一条命令行最多 32767 个字符，执行层的任务说明、协调层的话都可能比这长。
"""

from __future__ import annotations

import subprocess
import threading


def feed(proc: subprocess.Popen, text: str) -> None:
    """另起线程写、写完关——大段正文撑满管道时不能卡住读 stdout 的主线程。"""
    def _pump() -> None:
        try:
            proc.stdin.write(text)
        except BrokenPipeError:
            pass  # CLI 没读完就退了（参数错、没登录）：退出码与 stderr 会说明，这里不是失败点
        finally:
            proc.stdin.close()
    threading.Thread(target=_pump, daemon=True).start()
