"""与后端无关的杀树：超时时把 CLI 与它派生的整棵进程树一起带走。两家适配器共用，互不 import。"""

from __future__ import annotations

import os
import signal
import subprocess


def _pgids_below(pid: int) -> list[int]:
    """自顶向下趟出后代进程所在的进程组 id（叶子在前）。

    为什么不能只 killpg 自己那一组：实测 Claude Code 的 Bash 工具把 shell 起在**新的进程组**里，
    `sleep 300` 的 PGID 与 CLI 的 PGID 不同（还会被 run_in_background 放到后台），
    只杀 CLI 那一组会留下 PPID=1 的孤儿 sleep。必须趁父进程还活着把树趟完。
    """
    pgids: list[int] = []
    frontier = [pid]
    while frontier:
        proc = subprocess.run(["pgrep", "-P", str(frontier.pop())], capture_output=True, text=True)
        # pgrep 无匹配时退出码是 1，这是"没有子进程"不是故障；别的非零码才要炸
        if proc.returncode not in (0, 1):
            raise RuntimeError(f"pgrep 失败（退出码 {proc.returncode}）：{proc.stderr.strip()}")
        for token in proc.stdout.split():
            child = int(token)
            frontier.append(child)
            try:
                pgids.append(os.getpgid(child))
            except ProcessLookupError:
                continue  # 趟树期间自己退了，不是错误
    return pgids


def kill_tree(pid: int) -> list[int]:
    """杀干净：后代的进程组先杀，最后杀 pid 自己那一组。返回实际下手的 pgid 列表。"""
    own = os.getpgid(0)
    groups = [*_pgids_below(pid), os.getpgid(pid)]
    killed: list[int] = []
    for pgid in dict.fromkeys(groups):
        if pgid <= 1 or pgid == own:  # 护栏：绝不把框架自己那一组带走
            continue
        try:
            os.killpg(pgid, signal.SIGKILL)
        except ProcessLookupError:
            continue  # 已经死了
        killed.append(pgid)
    return killed
