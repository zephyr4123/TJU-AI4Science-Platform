"""进程树：起、查、杀。两个端口（`backends/` 起 agent 的 CLI、`compute/` 起本机的 harness）与框架
（`--detach` 的作业、对话锁）共用这一份；它不 import 仓里任何别的包（`tests/test_layering.py`）。

为什么是「树」不是「进程」：实测 Claude Code 的 Bash 工具把命令起在新的进程组里（还会挪到
后台），harness 的 `launcher.sh` 再起 python、mpirun；只杀顶上那一个，会留下继续占着算力的孤儿
（R-1 spike）。

- **POSIX**：起的时候自成会话（新进程组）；杀的时候先趟树（`pgrep -P`）把后代所在的组都找出来，叶子
  先杀，最后杀自己那一组——必须趁父进程还活着趟完。组号由调用方记着带进来：进程死了以后
  `os.getpgid` 就查不到了，而收尸恰恰发生在进程可能已经半死不活的时候。
- **Windows**（外层 #210）：没有进程组，也没有孤儿被 1 号进程收养那一套，父进程一死顺着父子关系就找
  不到孙进程了。所以起的时候把根放进一个按根 pid 命名的 Job Object（先挂起、放进去、再放行，它派生的
  一律在里面），杀就是把整个 Job 结束掉，查就是 Job 里还有没有活着的进程；别的进程（页面叫停
  `--detach` 起的作业）按名字再打开它。「组号」就是根的 pid。

两边的语义一样：`spawn` 起的进程不跟着起它的控制台走（关终端、Ctrl+C 都不波及），`kill_tree` 绝不把
调用者自己所在的那棵带走。
"""

from __future__ import annotations

import os
import signal
import subprocess
import sys
from typing import Any

WINDOWS = sys.platform == "win32"
if WINDOWS:
    from procs import _win

__all__ = ["spawn", "group_of", "kill_tree", "tree_alive", "pid_alive", "bash"]


def spawn(argv: list[str], *, detach: bool = False, **popen: Any) -> subprocess.Popen:
    """起一棵新树的根，其余参数原样交给 `Popen`。`detach`：起它的进程退出、它照跑（作业）。

    POSIX 上 `start_new_session` 两件事都管了；Windows 上另给一个看不见的控制台（它派生的 git、bash
    不弹黑窗口）、单独一个 Ctrl+C 组，作业再试着脱离起它的那个 Job（终端或 ssh 会把会话里的进程放进
    「关了就全杀」的 Job，允许脱离才脱离得了）。"""
    if not WINDOWS:
        return subprocess.Popen(argv, start_new_session=True, **popen)
    return _win.spawn(argv, detach=detach, **popen)


def group_of(pid: int) -> int:
    """刚起的这个进程的组号，交给 `kill_tree` / `tree_alive` 用；Windows 上就是它自己的 pid。"""
    return pid if WINDOWS else os.getpgid(pid)


def kill_tree(pid: int, pgid: int | None = None) -> list[int]:
    """杀干净 `pid` 那棵树，返回实际下手的组号。`pgid` 不给就现查（进程得还活着）。"""
    if WINDOWS:
        return _win.kill_tree(pid if pgid is None else pgid)
    own = os.getpgid(0)
    if pgid is None:
        pgid = os.getpgid(pid)
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


def tree_alive(pgid: int) -> bool:
    """那棵树里还有**活着**的进程吗。

    POSIX 上为什么不用 `os.killpg(pgid, 0)`：那个只问「这个组存在吗」，而一具还没被父进程收走的僵尸
    照样让组存在。续跑收尸时这会把「早就跑完了」读成「还在跑」，接着去 killpg 一具尸体，实测在 macOS
    上直接 EPERM 炸出来。ps 一次全表，问的是「有没有非僵尸成员」。"""
    if WINDOWS:
        return _win.tree_alive(pgid)
    if pgid <= 1:
        return False
    proc = subprocess.run(["ps", "-A", "-o", "pgid=,stat="], capture_output=True, text=True,
                          encoding="utf-8", errors="replace")
    if proc.returncode != 0:
        raise RuntimeError(f"ps 失败（退出码 {proc.returncode}）：{proc.stderr.strip()}")
    for line in proc.stdout.splitlines():
        parts = line.split()
        if len(parts) < 2 or not parts[0].isdigit():
            continue
        if int(parts[0]) == pgid and not parts[1].startswith("Z"):
            return True
    return False


def pid_alive(pid: int) -> bool:
    """这个进程还在不在。Windows 上不能用 `os.kill(pid, 0)`：信号 0 恰好是 `CTRL_C_EVENT`，Python 会
    向那个进程组发 Ctrl+C，把正在跑的打断（外层 #210）。"""
    if WINDOWS:
        return _win.pid_alive(pid)
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def bash() -> str:
    """跑 shell 脚本（harness 的 `launcher.sh`、`make_run0.sh`）用哪个 bash。

    Windows 上是 Git for Windows 带的那个（从 PATH 上的 git 推出来），不用光秃秃的 `bash`：起进程时
    先找 System32，装过 WSL 的机器上那是 WSL 的入口，脚本会跑进 Linux 里、找不到 Windows 这边的
    Python 与任务环境（windows-adaptation.md §3.8）。没有就抛 FileNotFoundError，说清装什么。"""
    return _win.git_bash() if WINDOWS else "bash"


def _pgids_below(pid: int) -> list[int]:
    """自顶向下趟出后代进程所在的进程组 id（叶子在前）。"""
    pgids: list[int] = []
    frontier = [pid]
    while frontier:
        proc = subprocess.run(["pgrep", "-P", str(frontier.pop())], capture_output=True, text=True,
                              encoding="utf-8", errors="replace")
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
