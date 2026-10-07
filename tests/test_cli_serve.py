"""`ai4sci serve` 的起与停（外层 #285）：真起一个服务进程，对话用的 CLI 是装在家里的假 CLI。

退出（标准输入关了、Ctrl-C、SIGTERM）要先停掉在跑的那几轮、连它们另起一组的孙子，后台作业不碰；
上一个服务崩了留下的轮次，下一个服务起来时收掉；端口用不了一句话退 3（外壳拿它换端口），刚关掉的
端口马上能再用（沿用端口，页面的主题等存在 localStorage，按端口分）。
"""

from __future__ import annotations

import json
import os
import signal
import socket
import subprocess
import sys
import threading
import time
import urllib.request
from pathlib import Path

import pytest

import procs
from framework import paths, toolchain
from tests.fixtures.fake_cli import fake_cli

REPO_ROOT = Path(__file__).resolve().parent.parent
SLEEP = "import time; time.sleep(120)"


def _until(check, limit_s: float = 15.0) -> bool:
    deadline = time.monotonic() + limit_s
    while time.monotonic() < deadline:
        if check():
            return True
        time.sleep(0.1)
    return False


def _home(tmp_path: Path) -> tuple[Path, Path]:
    """一个家，对话用的 Claude Code 装在家里：假 CLI 读完这一轮的话，起一个自成一组的孙子（像 CLI 的
    Bash 工具起命令）、一个后台作业（像助理按的 `cap --detach`），把两个 pid 写到 `marks/`，吐 init
    事件以后一直不回完。"""
    home, marks = tmp_path / "home", tmp_path / "marks"
    tools = home / paths.TOOLS_DIRNAME / "claude_code"
    tools.mkdir(parents=True)
    marks.mkdir()
    exe = Path(fake_cli(tools / "claude", (
        "import json, pathlib, subprocess, sys, time\n"
        "import procs\n"
        "sys.stdin.read()\n"
        f"marks = pathlib.Path({str(marks)!r})\n"
        f"grandchild = subprocess.Popen([sys.executable, '-c', {SLEEP!r}], start_new_session=True,"
        " creationflags=0x200 if sys.platform == 'win32' else 0)\n"
        "(marks / 'grandchild.pid').write_text(str(grandchild.pid), encoding='utf-8')\n"
        f"job = procs.spawn_detached([sys.executable, '-c', {SLEEP!r}])\n"
        "(marks / 'job.json').write_text(json.dumps(job._asdict()), encoding='utf-8')\n"
        "print(json.dumps({'type': 'system', 'subtype': 'init', 'session_id': 's1'}), flush=True)\n"
        "time.sleep(120)\n")))
    (tools / toolchain.RECEIPT).write_text(json.dumps({"entry": exe.name}), encoding="utf-8")
    return home, marks


def _serve(home: Path, *args: str, port: str = "0") -> subprocess.Popen:
    """起服务：标准输入接管道（外壳就是这么起的），日志落在家旁边的文件里。"""
    with (home.parent / "serve.log").open("ab") as log:
        return subprocess.Popen(
            [sys.executable, "-m", "framework.cli", "serve", "--port", port, *args],
            cwd=REPO_ROOT, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=log, text=True,
            encoding="utf-8",
            env={**os.environ, paths.HOME_ENV: str(home), "PYTHONPATH": str(REPO_ROOT)})


def _base(serve: subprocess.Popen) -> str:
    line = serve.stdout.readline()
    assert line.startswith("ok http://127.0.0.1:"), line
    return line.split("\t")[0].removeprefix("ok ")


def _call(base: str, path: str, body: dict | None = None) -> dict:
    data = None if body is None else json.dumps(body).encode("utf-8")
    req = urllib.request.Request(base + path, data=data,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _start_turn(base: str, marks: Path) -> tuple[int, dict]:
    """开项目、开对话、发一句（这一轮回不完，另起线程读流），等假 CLI 把孙子与作业起好。"""
    _call(base, "/projects", {"id": "p"})
    chat_id = _call(base, "/projects/p/chats", {})["chat_id"]

    def send() -> None:
        req = urllib.request.Request(f"{base}/projects/p/chats/{chat_id}/messages",
                                     data=json.dumps({"text": "你好"}).encode("utf-8"),
                                     headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                resp.read()
        except OSError:
            pass  # 服务退出时这条流被掐断：这正是要测的

    threading.Thread(target=send, daemon=True).start()
    assert _until(lambda: (marks / "job.json").is_file()), "假 CLI 没起来，测试前提不成立"
    time.sleep(0.3)
    return (int((marks / "grandchild.pid").read_text(encoding="utf-8")),
            json.loads((marks / "job.json").read_text(encoding="utf-8")))


def _job_survived(job: dict) -> bool:
    """后台作业还活着；Windows 上没有 explorer（SSH 里跑的）作业脱离不了那一轮，照旧起、说清楚。"""
    time.sleep(0.5)
    if job["warning"]:
        return procs.WINDOWS and "explorer" in job["warning"]
    return procs.pid_alive(job["pid"])


def _stop_job(marks: Path) -> None:
    if (marks / "job.json").is_file():
        pid = json.loads((marks / "job.json").read_text(encoding="utf-8"))["pid"]
        procs.kill_tree(pid, pid)


def test_closing_stdin_stops_serve_and_its_turns_but_not_jobs(tmp_path):
    """外壳退出时关掉 serve 的标准输入：服务停掉在跑的那一轮（连另起一组的孙子）、退出码 0，
    几秒内就走；助理起的后台作业照跑。`/health` 的 turns 说着此刻在跑几轮（外壳据此问一句）。"""
    home, marks = _home(tmp_path)
    serve = _serve(home, "--until-stdin-closes")
    try:
        base = _base(serve)
        assert _call(base, "/health")["turns"] == 0
        grandchild, job = _start_turn(base, marks)
        assert _call(base, "/health")["turns"] == 1
        assert list((home / "run").glob("serve-*.json")), "服务没把在跑的轮次登记到盘上"
        serve.stdin.close()
        assert serve.wait(timeout=15) == 0
        assert _until(lambda: not procs.pid_alive(grandchild)), "这一轮的孙子还活着"
        assert _job_survived(job), "后台作业跟着服务一起死了"
        assert not list((home / "run").glob("serve-*.json")), "干净退出还留着登记"
    finally:
        serve.kill()
        _stop_job(marks)


@pytest.mark.skipif(os.name == "nt", reason="SIGTERM / SIGINT 只在 POSIX 上能从外面发")
@pytest.mark.parametrize("sig", [signal.SIGTERM, signal.SIGINT])
def test_sigterm_and_ctrl_c_take_the_same_way_out(tmp_path, sig):
    """POSIX 上 SIGTERM（launchd、kill）与 Ctrl-C 走同一条退出：先停掉在跑的那一轮，再退 0。"""
    home, marks = _home(tmp_path)
    serve = _serve(home)
    try:
        base = _base(serve)
        grandchild, job = _start_turn(base, marks)
        serve.send_signal(sig)
        assert serve.wait(timeout=15) == 0
        assert _until(lambda: not procs.pid_alive(grandchild)), "这一轮的孙子还活着"
        assert _job_survived(job)
    finally:
        serve.kill()
        _stop_job(marks)


def test_a_serve_that_died_has_its_turns_reaped_by_the_next_one(tmp_path):
    """服务自己崩了、被杀了，标准输入那条线救不了：它登记在盘上的轮次由下一个起来的服务收掉。"""
    home = tmp_path / "home"
    home.mkdir()
    marker = tmp_path / "grandchild.pid"
    root = tmp_path / "root.py"  # 一轮对话的根：起一个自成一组的孙子，写下它的 pid
    root.write_text("import subprocess, sys, time\n"
                    f"g = subprocess.Popen([sys.executable, '-c', {SLEEP!r}],"
                    " start_new_session=True)\n"
                    f"open({str(marker)!r}, 'w', encoding='utf-8').write(str(g.pid))\n"
                    "time.sleep(120)\n", encoding="utf-8")
    dying = tmp_path / "dying.py"  # 像 serve 那样登记到家里，起了这一轮就崩（不收拾、不删登记）
    dying.write_text("import os, pathlib, subprocess, sys, time\n"
                     "import procs\n"
                     f"run = pathlib.Path({str(home / 'run')!r})\n"
                     "procs.keep_in(run / f'serve-{os.getpid()}.json')\n"
                     f"procs.spawn([sys.executable, {str(root)!r}], stdin=subprocess.DEVNULL,"
                     " stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)\n"
                     f"while not pathlib.Path({str(marker)!r}).exists():\n"
                     "    time.sleep(0.05)\n"
                     "time.sleep(0.3)\n"
                     "os._exit(0)\n", encoding="utf-8")
    crashed = subprocess.run([sys.executable, str(dying)], cwd=REPO_ROOT, capture_output=True,
                             text=True, timeout=60,
                             env={**os.environ, "PYTHONPATH": str(REPO_ROOT)})
    assert crashed.returncode == 0, crashed.stderr
    grandchild = int(marker.read_text(encoding="utf-8"))
    left = {p.name for p in (home / "run").glob("serve-*.json")}
    assert procs.pid_alive(grandchild) and len(left) == 1
    serve = _serve(home, "--until-stdin-closes")
    try:
        _base(serve)
        assert _until(lambda: not procs.pid_alive(grandchild)), "上一个服务留下的轮次没收掉"
        # 只剩新服务自己那一份（Windows 上 venv 的 python.exe 是启动器，服务的 pid 由它自己定名）
        now = {p.name for p in (home / "run").glob("serve-*.json")}
        assert len(now) == 1 and not now & left
        serve.stdin.close()
        assert serve.wait(timeout=15) == 0
    finally:
        serve.kill()
        procs.kill_tree(grandchild, grandchild)


def test_a_port_in_use_is_one_line_and_exit_3(tmp_path):
    """端口被占：一句话、退出码 3，外壳拿它换一个空闲端口（外层 #282 §3）。Windows 上不许复用地址：
    不然第二个服务悄悄绑上同一个端口、抢走一半请求。"""
    home = tmp_path / "home"
    home.mkdir()
    taken = socket.socket()
    taken.bind(("127.0.0.1", 0))
    taken.listen()
    try:
        port = taken.getsockname()[1]
        done = subprocess.run([sys.executable, "-m", "framework.cli", "serve", "--port", str(port)],
                              cwd=REPO_ROOT, capture_output=True, text=True, encoding="utf-8",
                              timeout=60, stdin=subprocess.DEVNULL,
                              env={**os.environ, paths.HOME_ENV: str(home),
                                   "PYTHONPATH": str(REPO_ROOT)})
    finally:
        taken.close()
    assert done.returncode == 3, done.stderr
    said = [line for line in done.stderr.splitlines() if str(port) in line]
    assert len(said) == 1 and "用不了" in said[0] and "Traceback" not in done.stderr
    assert done.stdout == ""


def test_the_port_is_free_again_right_after_serve_closes(tmp_path):
    """退出后马上重开要拿回同一个端口（主题等存在页面的 localStorage，按端口分）：服务自己关掉的
    连接在它的端口上留下一串 TIME_WAIT，不能因此绑不上。"""
    home = tmp_path / "home"
    home.mkdir()
    first = _serve(home, "--until-stdin-closes")
    try:
        base = _base(first)
        for _ in range(5):
            assert _call(base, "/health")["ok"]
        first.stdin.close()
        assert first.wait(timeout=15) == 0
    finally:
        first.kill()
    again = _serve(home, "--until-stdin-closes", port=base.rsplit(":", 1)[1])
    try:
        assert _base(again) == base
        assert _call(base, "/health")["ok"]
        again.stdin.close()
        assert again.wait(timeout=15) == 0
    finally:
        again.kill()
