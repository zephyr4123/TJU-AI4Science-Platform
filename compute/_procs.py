"""杀进程树：本地算力后端自己的一份。

为什么不 import `backends.claude_code.kill_tree`：依赖只指向一个方向，
`compute/` 与 `backends/` 是两根正交的轴，互不 import（CLAUDE.md 目录约定）。
逻辑是同一套（R-1 spike 的教训）：harness 里的 `launcher.sh` 会再起
python / mpirun 之类的子进程，它们可能自成进程组；只 killpg 顶上那一组会留下
PPID=1 的孤儿继续烧算力。所以先趟树、叶子的组先杀、最后杀自己那一组。
"""

from __future__ import annotations

import os
import signal
import subprocess


def _pgids_below(pid: int) -> list[int]:
    """自顶向下趟出后代进程所在的进程组 id（叶子在前）。"""
    pgids: list[int] = []
    frontier = [pid]
    while frontier:
        proc = subprocess.run(["pgrep", "-P", str(frontier.pop())], capture_output=True, text=True)
        # pgrep 无匹配时退出码是 1，这是"没有子进程"不是故障；别的非零码才要炸（不吞异常）
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


def kill_tree(pid: int, pgid: int) -> list[int]:
    """杀干净：后代的进程组先杀，最后杀 `pgid`。返回实际下手的 pgid 列表。

    `pgid` 由调用方从 Job 里带进来而不是现查：进程已经死了时 `os.getpgid(pid)`
    会抛 ProcessLookupError，而这正是收尸路径最常见的状态。
    """
    own = os.getpgid(0)
    try:
        groups = [*_pgids_below(pid), pgid]
    except ProcessLookupError:
        groups = [pgid]
    killed: list[int] = []
    for group in dict.fromkeys(groups):
        if group <= 1 or group == own:  # 护栏：绝不把框架自己那一组带走
            continue
        try:
            os.killpg(group, signal.SIGKILL)
        except ProcessLookupError:
            continue  # 已经死了
        killed.append(group)
    return killed


def group_alive(pgid: int) -> bool:
    """进程组里还有**活着**的成员吗。僵尸（stat 以 Z 开头）不算活着。

    为什么不用 `os.killpg(pgid, 0)`：那个只问"这个组存在吗"，而一具还没被父进程收走的
    僵尸照样让组存在。续跑收尸时这会把"早就跑完了"读成"还在跑"，接着去 killpg 一具
    尸体，实测在 macOS 上直接 EPERM 炸出来。ps 一次全表，问的是"有没有非僵尸成员"。
    """
    if pgid <= 1:
        return False
    proc = subprocess.run(["ps", "-A", "-o", "pgid=,stat="], capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"ps 失败（退出码 {proc.returncode}）：{proc.stderr.strip()}")
    for line in proc.stdout.splitlines():
        parts = line.split()
        if len(parts) < 2 or not parts[0].isdigit():
            continue
        if int(parts[0]) == pgid and not parts[1].startswith("Z"):
            return True
    return False
