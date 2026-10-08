"""进程树（`procs/`）：起、查、杀，macOS / Linux 与 Windows 同一套断言（外层 #210）。

树全用 Python 搭（不靠 sh、pgrep），在两边一样跑：根起一个中间层，中间层起一个孙子、把孙子的 pid
写进文件。Windows 上 venv 的 python.exe 是启动器、会再起一个真解释器，所以 pid 一律由脚本自己报。
"""

from __future__ import annotations

import json
import os
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


# ── 登记：本进程起的树，退出时一并收拾（外层 #285）────────────────────────────
REPO_ROOT = Path(__file__).resolve().parent.parent
# 一棵树的根：起一个自成一组的孙子（像 CLI 的 Bash 工具起命令），把孙子的 pid 写进 argv[1] 再睡
ROOT = ("import subprocess, sys, time\n"
        "child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(120)'],"
        " start_new_session=True)\n"
        "open(sys.argv[1], 'w', encoding='utf-8').write(str(child.pid))\n"
        "time.sleep(120)\n")
# 登记是进程级的：在另起的 Python 里试，不动测试进程自己的那份
HELPER = ("import json, os, pathlib, subprocess, sys, time\n"
          "import procs\n"
          "out = pathlib.Path(sys.argv[1])\n"
          "def tree(n):\n"
          "    marker = out / f'g{n}.pid'\n"
          f"    procs.spawn([sys.executable, '-c', {ROOT!r}, str(marker)],"
          " stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)\n"
          "    while not marker.exists():\n"
          "        time.sleep(0.05)\n"
          "    time.sleep(0.3)\n"
          "    return int(marker.read_text(encoding='utf-8'))\n")


def _helper(out: Path, body: str) -> subprocess.Popen:
    out.mkdir(parents=True, exist_ok=True)
    return subprocess.Popen([sys.executable, "-c", HELPER + body, str(out)], cwd=REPO_ROOT,
                            env={**os.environ, "PYTHONPATH": str(REPO_ROOT)},
                            stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, text=True, encoding="utf-8")


def test_kill_all_takes_every_running_tree_and_refuses_new_ones(tmp_path):
    """serve 退出时（外层 #285）：登记着的树逐棵杀干净，连另起一组的孙子；根已经被收走的那棵不在登记
    里（它的 pid 可能被别人用了）；杀完以后再起的当场杀掉、抛错；落盘的那份删掉。"""
    helper = _helper(tmp_path, (
        "procs.keep_in(out / 'trees.json')\n"
        "grandchildren = [tree(1), tree(2)]\n"
        "procs.spawn([sys.executable, '-c', 'pass'], stdin=subprocess.DEVNULL).wait()\n"
        "listed = json.loads((out / 'trees.json').read_text(encoding='utf-8'))\n"
        "killed = procs.kill_all()\n"
        "try:\n"
        "    procs.spawn([sys.executable, '-c', 'import time; time.sleep(60)'],"
        " stdin=subprocess.DEVNULL)\n"
        "    late = 'spawned'\n"
        "except RuntimeError as exc:\n"
        "    late = str(exc)\n"
        "print(json.dumps({'grandchildren': grandchildren, 'listed': listed, 'killed': killed,"
        " 'late': late, 'left': (out / 'trees.json').exists(), 'me': os.getpid()}))\n"))
    out, err = helper.communicate(timeout=60)
    assert helper.returncode == 0, err
    doc = json.loads(out)
    assert doc["listed"]["pid"] == doc["me"] and len(doc["listed"]["trees"]) == 2
    assert all(tree["birth"] for tree in doc["listed"]["trees"])
    assert len(doc["killed"]) >= 2 and "正在退出" in doc["late"] and not doc["left"]
    for grandchild in doc["grandchildren"]:
        assert _until(lambda g=grandchild: not procs.pid_alive(g)), "另起一组的孙子还活着"


def test_a_dead_owners_trees_are_reaped_and_nothing_else(tmp_path):
    """serve 自己崩了、被杀了（外层 #285）：下一个起来时按它落盘的登记把树收掉。只收确实是当时那一棵
    的（pid 被别的进程复用了不碰），主人还活着的登记不动，认不出的登记删掉。"""
    crashed = _helper(tmp_path / "crashed", (
        "procs.keep_in(out / 'trees.json')\n"
        "print(tree(1), flush=True)\n"
        "os._exit(0)\n"))  # 崩了：没 kill_all、没删登记
    out, err = crashed.communicate(timeout=60)
    assert crashed.returncode == 0, err
    orphan = int(out)
    registry = tmp_path / "crashed" / "trees.json"
    assert procs.pid_alive(orphan) and registry.is_file()
    # 同一份登记里再记一棵 pid 还活着、启动时间对不上的：那是 pid 被复用了，不是当时那一棵
    stranger = subprocess.Popen([sys.executable, "-c", SLEEP], stdin=subprocess.DEVNULL)
    try:
        doc = json.loads(registry.read_text(encoding="utf-8"))
        doc["trees"].append({"pid": stranger.pid, "birth": "Thu Jan  1 00:00:00 1970"})
        registry.write_text(json.dumps(doc), encoding="utf-8")
        assert procs.reap(registry)
        assert _until(lambda: not procs.pid_alive(orphan)), "死掉的主人留下的孙子还活着"
        assert stranger.poll() is None, "pid 被复用的那个进程被杀了"
        assert not registry.exists()
    finally:
        stranger.kill()
        stranger.wait(timeout=10)

    alive = _helper(tmp_path / "alive", (
        "procs.keep_in(out / 'trees.json')\n"
        "print(tree(1), flush=True)\n"
        "time.sleep(120)\n"))
    try:
        grandchild = int(alive.stdout.readline())
        assert procs.reap(tmp_path / "alive" / "trees.json") == []
        assert procs.pid_alive(grandchild) and (tmp_path / "alive" / "trees.json").is_file()
    finally:
        alive.kill()
        alive.wait(timeout=10)
        procs.reap(tmp_path / "alive" / "trees.json")  # 主人刚死：这回就收
    assert _until(lambda: not procs.pid_alive(grandchild))
    broken = tmp_path / "broken.json"
    broken.write_text("{坏", encoding="utf-8")
    assert procs.reap(broken) == [] and not broken.exists()


# ── 作业：不是起它的进程的后代（外层 #284）──────────────────────────────────
def test_a_detached_job_is_nobodys_descendant(tmp_path):
    """起作业的那条 `ai4sci cap --detach` 还在等它开产出时，那一轮被杀（顺后代往下杀）也杀不到它：
    作业经中间进程起（Windows 上以 explorer 为父进程起）。Windows 上没有 explorer（SSH、服务里跑的，
    CI 就是）才照旧起、说清楚为什么；桌面会话里有 explorer 就必须借上——Windows 11 的 explorer 自己
    就在一个许脱离的 Job 里（外层 #282 真机），不能当成用不了。"""
    marker = tmp_path / "job.json"
    launcher = ("import json, subprocess, sys, time\n"
                "import procs\n"
                f"job = procs.spawn_detached([sys.executable, '-c', {SLEEP!r}])\n"
                f"open({str(marker)!r}, 'w', encoding='utf-8').write(json.dumps(job._asdict()))\n"
                "time.sleep(120)\n")
    root = procs.spawn([sys.executable, "-c", launcher], stdin=subprocess.DEVNULL,
                       env={**os.environ, "PYTHONPATH": str(REPO_ROOT)})
    assert _until(marker.exists, 30), "作业没起来，测试前提不成立"
    job = json.loads(marker.read_text(encoding="utf-8"))
    try:
        procs.kill_tree(root.pid, procs.group_of(root.pid))
        root.wait(timeout=10)
        if job["warning"]:
            assert procs.WINDOWS and "没有 explorer" in job["warning"], job["warning"]
        else:
            time.sleep(0.5)
            assert procs.pid_alive(job["pid"]), "作业跟着起它的那棵树一起死了"
    finally:
        procs.kill_tree(job["pid"], job["pid"])
