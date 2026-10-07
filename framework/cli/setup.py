"""`ai4sci setup [--no-serve] [--host] [--port]`：装好平台以后接着做的事（外层 #277 onboarding）。

一行命令的 `install/install.sh` 只装 uv 与平台，然后交给这里：查 git → 两家 CLI 没有或版本不够就从
国内镜像装进平台的家（`framework/toolchain.py`）→ 助理与执行层用的那家能不能说话，不能就在终端里问
DeepSeek 的 key、当场问一句试通 → 起服务、开浏览器。主人 2026-10-07：全程国内源、装过就跳过、尽量
不让人去页面上点。每一项先查，所以重跑无害，也是修复与升级 CLI 的命令；`make up`、以后的 Windows
安装、桌面包第一次打开都接这一份。

按系统分的只有 git 怎么补（`git_ready`）：Mac 弹苹果的安装框，Linux 让人用包管理器装，Windows 从
npmmirror 装 Git for Windows 的便携版进平台的家（外层 #210）。只给人：助理的会话里拒（要填 key、要下
几百 MB）。
"""

from __future__ import annotations

import argparse
import getpass
import shutil
import socket
import subprocess
import sys
import threading
import time
import webbrowser

import procs
from backends import (
    INSTALLED_ITEM,
    TITLES,
    VERSION_ITEM,
    AgentProbe,
    available_backends,
    install_of,
)
from framework import agents, keys, paths, toolchain
from framework.cli import serve
from framework.cli._common import EXIT_INVALID, EXIT_OK, refuse_if_assistant

# 新用户唯一可能会的，就是去 DeepSeek 后台申请一个 key（主人 2026-10-07）；别的供应商在设置页换
SETUP_PROVIDER = "deepseek"
KEY_SITE = "platform.deepseek.com"
KEY_ATTEMPTS = 3
LABEL_WIDTH = 14
SERVE_WAIT_S = 30.0
MAC_GIT_STUB = "/usr/bin/git"  # 没装命令行工具时它只会弹安装框


def interactive() -> bool:
    return sys.stdin.isatty()


def ask_secret(prompt: str) -> str:
    """粘贴时不回显；没有输入（Ctrl-D）当回车。"""
    try:
        return getpass.getpass(prompt)
    except EOFError:
        return ""


def git_ready() -> tuple[bool, str]:
    """跑实验要 git（`framework/experiment/gitwork.py`），Windows 上 Claude Code 的 Bash 工具与
    harness 的脚本还要它带的 bash。Mac、Linux 上是系统组件；Windows 上没有就装进平台的家
    （`toolchain`）。"""
    found = shutil.which("git")
    if sys.platform == "darwin":
        tools = subprocess.run(["xcode-select", "-p"], capture_output=True, check=False)
        if tools.returncode == 0 or (found and found != MAC_GIT_STUB):
            return True, "已装，跳过"
        subprocess.run(["xcode-select", "--install"], capture_output=True, check=False)
        return False, "系统弹出了苹果的安装框，点「安装」，装完再跑一次 ai4sci setup"
    if sys.platform == "win32":
        try:
            procs.bash()  # 有 git 还得带 bash（MinGit 不带）
            return True, "已装，跳过"
        except FileNotFoundError:
            pass
        try:
            toolchain.install_git(progress=_progress("git"))
        except toolchain.ToolchainError as exc:
            return False, str(exc)
        toolchain.use_private_git()
        return True, f"Git for Windows {toolchain.GIT_TAG.lstrip('v')}，下载完成"
    if found:
        return True, "已装，跳过"
    return False, "没装：用系统的包管理器装 git"


def cmd_setup(args: argparse.Namespace) -> int:
    refused = refuse_if_assistant("装平台、填 key ")
    if refused is not None:
        return refused
    git_ok, note = git_ready()
    _line(git_ok, "git", note)
    clis_ok = all([_cli(name) for name in available_backends()])
    model_ok = _model()
    done = git_ok and clis_ok and model_ok
    if args.no_serve:
        return EXIT_OK if done else EXIT_INVALID
    return _serve(args.host, args.port)


def _cli(name: str) -> bool:
    """这家 CLI：够版本就跳过，否则从国内镜像装进平台的家。"""
    title = TITLES[name]
    found = toolchain.find(name)
    if found is not None and found.ok:
        _line(True, title, f"{_short(name, found.version)}，已装，跳过")
        return True
    try:
        got = toolchain.install(name, progress=_progress(title))
    except toolchain.ToolchainError as exc:
        _line(False, title, str(exc))
        return False
    _line(True, title, f"{_short(name, got.version)}，下载完成")
    return True


def _model() -> bool:
    """助理与执行层用的那家能不能说话（真问一句，`ai4sci agent check` 那四项）；不能就问 key。"""
    fresh = not agents.path().exists()  # 新家：填进来的 key 两家都用上
    try:
        registry = agents.load()
    except agents.AgentsInvalid as exc:
        print(f"  ✗ {exc}")
        return False
    failing: list[str] = []
    for name in dict.fromkeys((registry.chat, registry.executor)):
        got = _probe(name)
        if got.ok:
            _say(True, name, f"能用（{_provider_title(name)}），跳过")
        elif _first_failure(got)[0] in (INSTALLED_ITEM, VERSION_ITEM):
            _say(False, name, _first_failure(got)[1])  # 装的那一步已经报过为什么
            return False
        else:
            failing.append(name)
    if not failing:
        return True
    if not interactive():
        print("  ✗ 没有终端，不问 key：页面「设置 → AI」里填")
        return False
    return _ask_key(failing, list(available_backends()) if fresh else failing)


def _ask_key(failing: list[str], switch: list[str]) -> bool:
    """问 DeepSeek 的 key、切过去、再问一句；不通再问，回车跳过。key 不上屏。"""
    key_name = agents.provider_of(failing[0], SETUP_PROVIDER).key
    title = agents.provider_of(failing[0], SETUP_PROVIDER).title
    assert key_name is not None, f"{SETUP_PROVIDER} 要 key 才能接"
    print()
    for _ in range(KEY_ATTEMPTS):
        typed = ask_secret(f"粘贴 {title} 的 key（{KEY_SITE} 申请，粘贴时不显示；回车跳过）：")
        if not typed.strip():
            print("  ✗ 跳过了：之后在页面「设置 → AI」里填")
            return False
        keys.put(key_name, typed)
        for name in switch:
            agents.use(name, provider=SETUP_PROVIDER)
        results = {name: _probe(name) for name in failing}
        if all(got.ok for got in results.values()):
            for name, got in results.items():
                _say(True, name, f"问了一句，通了（{title}，{got.spoke_s:.1f} 秒）")
            return True
        for name, got in results.items():
            if not got.ok:
                _say(False, name, f"没通：{_first_failure(got)[1]}")
    print(f"  ✗ 试了 {KEY_ATTEMPTS} 次都没通：之后在页面「设置 → AI」里改")
    return False


def _probe(name: str) -> AgentProbe:
    got = agents.probe(name)
    agents.record_check(name, got)
    return got


def _first_failure(got: AgentProbe) -> tuple[str, str]:
    return next(((item, note) for item, ok, note in got.items if not ok), ("", "没有结果"))


def _provider_title(name: str) -> str:
    return agents.provider_of(name, agents.load().get(name).provider).title


def _short(name: str, version: str) -> str:
    """`2.1.292 (Claude Code)`、`codex-cli 0.160.1` 只留版本号。"""
    parsed = install_of(name).parse_version(version)
    return ".".join(map(str, parsed)) if parsed else version


def _line(ok: bool, label: str, note: str) -> None:
    clear = "\r\x1b[2K" if sys.stdout.isatty() else ""
    print(f"{clear}  {'✓' if ok else '✗'} {label:<{LABEL_WIDTH}}{note}", flush=True)


def _say(ok: bool, name: str, sentence: str) -> None:
    print(f"  {'✓' if ok else '✗'} {TITLES[name]} {sentence}", flush=True)


def _progress(title: str) -> toolchain.Progress | None:
    """下载进度画在同一行；不是终端就不画（日志里不要几百行进度）。"""
    if not sys.stdout.isatty():
        return None

    def draw(done: int, total: int | None) -> None:
        size = f"{done / 1e6:.0f}/{total / 1e6:.0f} MB" if total else f"{done / 1e6:.0f} MB"
        print(f"\r  ↓ {title:<{LABEL_WIDTH}}下载中 {size}", end="", flush=True)

    return draw


def _serve(host: str, port: int) -> int:
    """起服务、等它能连上就开浏览器；已经有一个在跑就只开浏览器。"""
    url = f"http://{host}:{port}"
    if _listening(host, port):
        webbrowser.open(url)
        print(f"\n服务已经在跑，浏览器已打开 {url}")
        return EXIT_OK
    threading.Thread(target=_open_when_up, args=(host, port, url), daemon=True).start()
    print(f"\n浏览器马上打开 {url}\n关掉这个窗口服务就停；下次启动：{paths.cli()} serve\n",
          flush=True)
    return serve.cmd_serve(argparse.Namespace(host=host, port=port, ui=None))


def _open_when_up(host: str, port: int, url: str) -> None:
    deadline = time.monotonic() + SERVE_WAIT_S
    while time.monotonic() < deadline:
        if _listening(host, port):
            webbrowser.open(url)
            return
        time.sleep(0.2)


def _listening(host: str, port: int) -> bool:
    try:
        with socket.create_connection((host, port), timeout=0.5):
            return True
    except OSError:
        return False


def add_parser(groups: argparse._SubParsersAction) -> None:
    group = groups.add_parser("setup", help="装好平台以后接着做：查 git、装两家 CLI、填 key、"
                                            "起服务；装过的跳过，重跑无害")
    group.add_argument("--no-serve", action="store_true", help="做完不起服务（make up、测试用）")
    group.add_argument("--host", default="127.0.0.1")
    group.add_argument("--port", type=int, default=8765)
    group.set_defaults(func=cmd_setup)
