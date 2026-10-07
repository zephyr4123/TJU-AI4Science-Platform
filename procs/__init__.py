"""进程树：起、查、杀，外加本进程起的树的登记。两个端口（`backends/` 起 agent 的 CLI、`compute/`
起本机的 harness）与框架（`--detach` 的作业、对话锁、serve 退出时收拾）共用这一份；它不 import 仓里
任何别的包（`tests/test_layering.py`）。

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

**登记**（外层 #285）：`spawn` 起的树（一轮对话的 CLI、执行层、harness）记在本进程的登记里，调用方
wait / poll 到根的退出码就摘掉（根被收走以后它的 pid 可能被别人用，不能再按它杀）。`kill_all` 逐棵
杀掉、之后再起的当场杀掉：serve 退出（标准输入关了、Ctrl-C、SIGTERM）靠它不留孤儿。`keep_in(文件)`
让登记同时落盘，放哪由调用方定（serve 用平台的家里的 `run/serve-<pid>.json`）：serve 自己崩了、
被杀了，下一个 serve 起来 `reap` 那份文件，只杀还活着、而且确实是当时那一棵的树（pid 与启动时间都
对得上；pid 被别的进程复用了不碰）。

**作业**（`spawn_detached`，外层 #284）：活过起它的进程，不进登记，谁退出都不碰它。POSIX 上经一个
中间进程起（自成会话），中间进程马上退出，作业生来就归 1 号进程、不是任何人的后代——不然起它的那条
`ai4sci cap --detach` 还在等它开产出的那几秒里，顺后代往下杀的 `kill_tree`（那一轮超时、serve
退出）会杀到它。Windows 上以当前会话的 explorer 为父进程起（`_win.spawn_detached`）。三个标准流都
不接，作业自己按路径打开日志：Windows 上指定了父进程，句柄就从 explorer 继承，传不过去；两边用同一个
办法。
"""

from __future__ import annotations

import json
import logging
import os
import signal
import subprocess
import sys
import threading
from pathlib import Path
from typing import Any, NamedTuple

WINDOWS = sys.platform == "win32"
if WINDOWS:
    from procs import _win

__all__ = ["spawn", "spawn_detached", "Detached", "group_of", "kill_tree", "tree_alive",
           "pid_alive", "bash", "keep_in", "kill_all", "reap"]

LOGGER = logging.getLogger("ai4sci.procs")
# 中间进程：起作业（自成会话、三个标准流都不接）、把它的 pid 打出来就退出
_LAUNCH = ("import subprocess, sys\n"
           "job = subprocess.Popen(sys.argv[1:], start_new_session=True, stdin=subprocess.DEVNULL,"
           " stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)\n"
           "print(job.pid)\n")
LAUNCH_TIMEOUT_S = 30


class Detached(NamedTuple):
    """`spawn_detached` 起的作业：根的 pid，与要人知道的一句（没能脱离起它的进程时说为什么；空是
    没事）。"""

    pid: int
    warning: str


class _Tree(subprocess.Popen):
    """`spawn` 起的根：调用方 wait / poll 到它的退出码，就从登记里摘掉。"""

    def wait(self, timeout: float | None = None) -> int:
        code = super().wait(timeout)
        _TREES.drop(self)
        return code

    def poll(self) -> int | None:
        code = super().poll()
        if code is not None:
            _TREES.drop(self)
        return code


def spawn(argv: list[str], **popen: Any) -> subprocess.Popen:
    """起一棵新树的根并登记，其余参数原样交给 `Popen`。起它的进程退出时这棵树该跟着结束（登记里的
    由 `kill_all` 收拾）；要活过它的是作业，走 `spawn_detached`。

    POSIX 上自成会话；Windows 上另给一个看不见的控制台（它派生的 git、bash 不弹黑窗口）、单独一个
    Ctrl+C 组，挂起起、放进它的 Job 再放行。"""
    if WINDOWS:
        flags = popen.pop("creationflags", 0) | _win.TREE_FLAGS
        proc = _Tree(argv, creationflags=flags, **popen)
        _win.adopt(proc)
    else:
        proc = _Tree(argv, start_new_session=True, **popen)
    _TREES.add(proc)
    return proc


def spawn_detached(argv: list[str], *, env: dict[str, str] | None = None,
                   cwd: str | None = None) -> Detached:
    """起一个作业的根：不是起它的进程的后代、不进登记、三个标准流都不接（作业自己按路径开日志）。"""
    if WINDOWS:
        return Detached(*_win.spawn_detached(argv, env=env, cwd=cwd))
    done = subprocess.run([sys.executable, "-I", "-c", _LAUNCH, *argv], capture_output=True,
                          text=True, encoding="utf-8", errors="replace", env=env, cwd=cwd,
                          stdin=subprocess.DEVNULL, timeout=LAUNCH_TIMEOUT_S, check=False)
    said = done.stdout.strip()
    if done.returncode != 0 or not said.isdigit():
        raise OSError(f"起作业失败（退出码 {done.returncode}）：{done.stderr.strip()[-500:]}")
    return Detached(int(said), "")


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


def keep_in(path: Path) -> None:
    """登记从此同时写到 `path`（先写临时文件再换过去，崩在半路也不留半份）：本进程死了，下一个进程
    `reap` 它。"""
    _TREES.keep_in(Path(path))


def kill_all() -> list[int]:
    """杀掉登记着的每一棵树，返回下手的组号；之后再 `spawn` 的当场杀掉、抛 RuntimeError。都杀成了就
    删掉落盘的那份；有没杀成的（记 ERROR）留着它，下一个进程起来 `reap` 时再试。"""
    return _TREES.kill_all()


def reap(path: Path) -> list[int]:
    """`path` 是别的进程 `keep_in` 写下的登记。它的主人已经不在了（pid 没了，或这个 pid 已经是别的
    进程：启动时间对不上），就杀掉里面还活着、而且确实是当时那一棵的树，删掉这份登记，返回下手的
    组号；主人还活着什么都不动。认不出的登记记一行 WARNING、删掉。"""
    path = Path(path)
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
        owner, born = int(doc["pid"]), str(doc["birth"])
        trees = [(int(tree["pid"]), str(tree["birth"])) for tree in doc["trees"]]
    except FileNotFoundError:
        return []
    except (ValueError, KeyError, TypeError) as exc:
        LOGGER.warning("trees_file_unreadable path=%s why=%s", path, exc)
        path.unlink(missing_ok=True)
        return []
    if owner == os.getpid() or (pid_alive(owner) and (not born or _birth(owner) == born)):
        return []  # 主人还在（认不出是不是它时也当它在）：它自己的树它自己收
    killed: list[int] = []
    failed = False
    for pid, birth in trees:
        if not birth or _birth(pid) != birth:
            continue  # 早没了，或 pid 已经是别人的
        try:
            killed += kill_tree(pid, pid)
        except (OSError, RuntimeError) as exc:
            failed = True
            LOGGER.error("reap_tree_failed path=%s pid=%d why=%s", path, pid, exc)
    if not failed:
        path.unlink(missing_ok=True)
    LOGGER.info("trees_reaped path=%s owner=%d killed=%s", path, owner, killed)
    return killed


class _Registry:
    """本进程 `spawn` 起、根还没被收走的树。线程安全：serve 里每一轮对话在各自的线程里起。"""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._trees: dict[int, tuple[subprocess.Popen, str]] = {}  # 根的 pid → (根, 启动时间)
        self._file: Path | None = None
        self._birth = ""
        self._closed = False

    def add(self, proc: subprocess.Popen) -> None:
        birth = _birth(proc.pid) if self._file is not None else ""
        with self._lock:
            closed = self._closed
            if not closed:
                self._trees[proc.pid] = (proc, birth)
                self._save()
        if closed:  # kill_all 之后才起的：不让它活过这次退出
            kill_tree(proc.pid, proc.pid)
            proc.wait()
            raise RuntimeError("正在退出，不再起新的进程树")

    def drop(self, proc: subprocess.Popen) -> None:
        with self._lock:
            if self._trees.get(proc.pid, (None, ""))[0] is proc:
                del self._trees[proc.pid]
                self._save()

    def keep_in(self, path: Path) -> None:
        with self._lock:
            self._file = path
            self._birth = _birth(os.getpid())
            self._trees = {pid: (proc, birth or _birth(pid))
                           for pid, (proc, birth) in self._trees.items()}
            self._save()

    def kill_all(self) -> list[int]:
        with self._lock:
            self._closed = True
            roots = [proc for proc, _ in self._trees.values()]
        killed: list[int] = []
        failed = False
        for proc in roots:
            if proc.poll() is not None:
                continue  # 根已经收走了：它的 pid 可能被别人用了，不按它杀
            try:
                killed += kill_tree(proc.pid, proc.pid)
            except (OSError, RuntimeError) as exc:  # 一棵没杀成不挡别的
                failed = True
                LOGGER.error("kill_all_tree_failed pid=%d why=%s", proc.pid, exc)
        with self._lock:
            if self._file is not None and not failed:
                self._file.unlink(missing_ok=True)
                self._file = None
        LOGGER.info("kill_all trees=%d killed=%s", len(roots), killed)
        return killed

    def _save(self) -> None:
        """登记落盘（持着锁调）。写不进去记 WARNING、不抛：落盘只是给崩溃之后收尾用的，不该让起进程
        的那一轮因此失败。"""
        if self._file is None:
            return
        doc = {"pid": os.getpid(), "birth": self._birth,
               "trees": [{"pid": pid, "birth": birth} for pid, (_, birth) in self._trees.items()]}
        tmp = self._file.with_name(f".{self._file.name}.tmp")
        try:
            self._file.parent.mkdir(parents=True, exist_ok=True)
            tmp.write_text(json.dumps(doc) + "\n", encoding="utf-8")
            os.replace(tmp, self._file)
        except OSError as exc:
            LOGGER.warning("trees_file_unwritable path=%s why=%s", self._file, exc)


_TREES = _Registry()


def _birth(pid: int) -> str:
    """进程的启动时间：认人用，pid 会被复用、pid 加启动时间不会。进程不在（或查不出）是空串。
    POSIX 上问 ps（秒级；钉死区域与时区，几次问出来的写法才一样），Windows 上是 GetProcessTimes。"""
    if WINDOWS:
        return _win.birth(pid)
    done = subprocess.run(["ps", "-o", "lstart=", "-p", str(pid)], capture_output=True, text=True,
                          encoding="utf-8", errors="replace", check=False,
                          env={**os.environ, "LC_ALL": "C", "TZ": "UTC0"})
    return done.stdout.strip() if done.returncode == 0 else ""


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
