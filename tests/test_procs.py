"""进程树（`procs/`）：起、查、杀，macOS / Linux 与 Windows 同一套断言（外层 #210）。

树全用 Python 搭（不靠 sh、pgrep），在两边一样跑：根起一个中间层，中间层起一个孙子、把孙子的 pid
写进文件。Windows 上 venv 的 python.exe 是启动器、会再起一个真解释器，所以 pid 一律由脚本自己报。
"""

from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

import procs

SLEEP = "import time; time.sleep(120)"


def _until(check, limit_s: float = 10.0) -> bool:
    deadline = time.monotonic() + limit_s
    while time.monotonic() < deadline:
        if check():
            return True
        time.sleep(0.05)
    return False


def _tree(tmp_path: Path, *, middle_exits: bool, own_group: bool) -> tuple[subprocess.Popen, int]:
    """根 → 中间层 → 孙子。`middle_exits`：中间层起完孙子就退（孙子成了孤儿）；`own_group`：孙子
    自成一组（Claude Code 的 Bash 工具就这样起命令）。返回根与孙子的 pid。"""
    marker = tmp_path / "grandchild.pid"
    grandchild = (f"import os, subprocess, sys, time\n"
                  f"p = subprocess.Popen([sys.executable, '-c', {SLEEP!r}],"
                  f" start_new_session={own_group})\n"
                  f"open({str(marker)!r}, 'w', encoding='utf-8').write(str(p.pid))\n"
                  f"{'' if middle_exits else 'time.sleep(120)'}\n")
    root = procs.spawn([sys.executable, "-c",
                        f"import subprocess, sys, time\n"
                        f"subprocess.Popen([sys.executable, '-c', {grandchild!r}])\n"
                        f"time.sleep(120)\n"],
                       stdin=subprocess.DEVNULL)
    assert _until(marker.exists), "孙子没起来，测试前提不成立"
    time.sleep(0.3)  # 等它把 pid 写完、真的睡上
    return root, int(marker.read_text(encoding="utf-8"))


def test_asking_whether_a_process_lives_does_not_disturb_it():
    """Windows 上 `os.kill(pid, 0)` 是给它发 Ctrl+C：问两遍「还在吗」它就没了。"""
    proc = procs.spawn([sys.executable, "-c", SLEEP], stdin=subprocess.DEVNULL)
    try:
        assert procs.pid_alive(proc.pid) and procs.pid_alive(proc.pid)
        time.sleep(0.5)
        assert proc.poll() is None and procs.pid_alive(proc.pid)
    finally:
        procs.kill_tree(proc.pid, procs.group_of(proc.pid))
    proc.wait(timeout=10)
    assert _until(lambda: not procs.pid_alive(proc.pid))


def test_kill_tree_takes_an_orphan_whose_parent_already_left(tmp_path):
    """中间层先退了，孙子顺着父子关系已经找不到；照样要连它一起杀。"""
    root, grandchild = _tree(tmp_path, middle_exits=True, own_group=False)
    group = procs.group_of(root.pid)
    assert procs.pid_alive(grandchild) and procs.tree_alive(group)
    assert procs.kill_tree(root.pid, group)
    root.wait(timeout=10)
    assert _until(lambda: not procs.pid_alive(grandchild)), "孤儿还活着"
    assert _until(lambda: not procs.tree_alive(group))


def test_kill_tree_takes_a_grandchild_in_its_own_group(tmp_path):
    """复刻实测的形态：CLI 的 Bash 工具把子进程起在另一个进程组里，只杀根那一组会留下孤儿
    （R-1）。"""
    root, grandchild = _tree(tmp_path, middle_exits=False, own_group=True)
    procs.kill_tree(root.pid, procs.group_of(root.pid))
    root.wait(timeout=10)
    assert _until(lambda: not procs.pid_alive(grandchild)), "另起一组的孙子还活着"


def test_a_finished_tree_is_not_alive_and_killing_it_is_harmless():
    proc = procs.spawn([sys.executable, "-c", "pass"], stdin=subprocess.DEVNULL)
    group = procs.group_of(proc.pid)
    proc.wait(timeout=30)
    assert _until(lambda: not procs.tree_alive(group))
    assert not procs.pid_alive(proc.pid)
    procs.kill_tree(proc.pid, group)  # 收尸路径：对着跑完的树叫停不炸
