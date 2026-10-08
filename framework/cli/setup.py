"""`ai4sci setup [--no-serve] [--no-input] [--host] [--port]`：装好平台以后接着做的事（外层 #277
onboarding）。

一行命令的 `install/install.sh` 只装 uv 与平台，然后交给这里：查 git → 两家 CLI 没有或版本不够就从
国内镜像装进平台的家（`framework/toolchain.py`）→ 助理与执行层用的那家能不能说话，不能就在终端里问
DeepSeek 的 key、当场问一句试通 → 起服务、开浏览器。主人 2026-10-07：全程国内源、装过就跳过、尽量
不让人去页面上点。每一项先查，所以重跑无害，也是修复与升级 CLI 的命令；`make up`、Windows 的一行
命令、桌面 App 第一次打开都接这一份。

`--no-input` 是桌面 App 起的那一种（外层 #282，`docs/specs/desktop.md` §3 的约定）：不问 key、不探
模型、不开浏览器（能不能说话由页面读 `/settings` 的助理状态再弹框）；不认 PATH 上的两家 CLI，一律装
进家里（外壳拿到的 PATH 时有时没有）；输出一项一行 `  ✓ / ✗ / ! 标签 说明`，不接终端时下载先说一句
`  … 标签 下载中`、之后每 5 秒一行已下多少。退出码 0 是 git 与两家 CLI 都好（Mac 缺命令行工具只打
`!`），1 是没装好。

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
from framework import agents, paths, toolchain
from framework.cli import serve
from framework.cli._common import EXIT_INVALID, EXIT_OK, refuse_if_assistant

KEY_ATTEMPTS = 3
LABEL_WIDTH = 14
# 一项一行的记号（外壳按它读，`docs/specs/desktop.md` §3）：好了、没好、提醒一句不算失败
MARK_OK, MARK_FAILED, MARK_NOTICE = "✓", "✗", "!"
PROGRESS_EVERY_S = 5.0
SERVE_WAIT_S = 30.0
MAC_GIT_STUB = "/usr/bin/git"  # 没装命令行工具时它只会弹安装框
# Windows 缺省一条路径最多 260 个字符（外层 #210）：项目深、包多时会撞上；开不开要管理员
LONG_PATHS_KEY = r"SYSTEM\CurrentControlSet\Control\FileSystem"
LONG_PATHS_FIX = (r"New-ItemProperty -Path HKLM:\SYSTEM\CurrentControlSet\Control\FileSystem "
                  "-Name LongPathsEnabled -Value 1 -PropertyType DWORD -Force")


def interactive() -> bool:
    return sys.stdin.isatty()


def ask_secret(prompt: str) -> str:
    """粘贴时不回显；没有输入（Ctrl-D）当回车。"""
    try:
        return getpass.getpass(prompt)
    except EOFError:
        return ""


def git_ready(no_input: bool = False) -> tuple[str, str]:
    """跑实验要 git（`framework/experiment/gitwork.py`），Windows 上 Claude Code 的 Bash 工具与
    harness 的脚本还要它带的 bash。Mac、Linux 上是系统组件；Windows 上没有就装进平台的家
    （`toolchain`）。返回这一行的记号与一句话。

    Mac 没装命令行工具时弹一次苹果的安装框。终端里算没装好、装完再跑一次；桌面
    App（`no_input`）只提醒：git 只在跑实验时要，对话与看结果用不着，不为它把人挡在启动页
    （外层 #282）。"""
    found = shutil.which("git")
    if sys.platform == "darwin":
        tools = subprocess.run(["xcode-select", "-p"], capture_output=True, check=False)
        if tools.returncode == 0 or (found and found != MAC_GIT_STUB):
            return MARK_OK, "已装，跳过"
        subprocess.run(["xcode-select", "--install"], capture_output=True, check=False)
        if no_input:
            return MARK_NOTICE, "没装命令行工具：系统弹出了苹果的安装框，点「安装」；跑实验时才要它"
        return MARK_FAILED, "系统弹出了苹果的安装框，点「安装」，装完再跑一次 ai4sci setup"
    if sys.platform == "win32":
        try:
            procs.bash()  # 有 git 还得带 bash（MinGit 不带）
            return MARK_OK, "已装，跳过"
        except FileNotFoundError:
            pass
        try:
            toolchain.install_git(progress=_downloading("git"))
        except toolchain.ToolchainError as exc:
            return MARK_FAILED, str(exc)
        toolchain.use_private_git()
        return MARK_OK, f"Git for Windows {toolchain.GIT_TAG.lstrip('v')}，下载完成"
    if found:
        return MARK_OK, "已装，跳过"
    return MARK_FAILED, "没装：用系统的包管理器装 git"


def long_paths_hint() -> str | None:
    """Windows 没开长路径就给一行管理员命令；不拦（多数课题撞不上），也不替人改系统设置。"""
    if sys.platform != "win32":
        return None
    import winreg

    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, LONG_PATHS_KEY) as key:
            if winreg.QueryValueEx(key, "LongPathsEnabled")[0] == 1:
                return None
    except OSError:
        pass  # 没这一项就是没开
    return f"没开（一条路径最多 260 个字符）：管理员 PowerShell 里跑一次 {LONG_PATHS_FIX}"


def cmd_setup(args: argparse.Namespace) -> int:
    refused = refuse_if_assistant("装平台、填 key ")
    if refused is not None:
        return refused
    git_mark, note = git_ready(args.no_input)
    _line(git_mark, "git", note)
    if (hint := long_paths_hint()) is not None:
        _line(MARK_NOTICE, "long paths", hint)
    clis_ok = all([_cli(name, home_only=args.no_input) for name in available_backends()])
    # 桌面 App 不探模型：能不能说话由页面读 /settings 的助理状态再弹框（外层 #282）
    model_ok = args.no_input or _model()
    done = git_mark != MARK_FAILED and clis_ok and model_ok
    if args.no_serve:
        return EXIT_OK if done else EXIT_INVALID
    return _serve(args.host, args.port, browser=not args.no_input)


def _cli(name: str, home_only: bool) -> bool:
    """这家 CLI：够版本就跳过，否则从国内镜像装进平台的家。`home_only`（桌面 App）不认 PATH 上的
    那份：外壳拿到的 PATH 时有时没有，认了它，同一个人的助理就时好时坏（外层 #282）。"""
    title = TITLES[name]
    found = toolchain.find(name)
    if found is not None and found.ok and (found.private or not home_only):
        _line(MARK_OK, title, f"{_short(name, found.version)}，已装，跳过")
        return True
    try:
        got = toolchain.install(name, progress=_downloading(title))
    except toolchain.ToolchainError as exc:
        _line(MARK_FAILED, title, str(exc))
        return False
    _line(MARK_OK, title, f"{_short(name, got.version)}，下载完成")
    return True


def _model() -> bool:
    """助理与执行层用的那家能不能说话（真问一句，`ai4sci agent check` 那四项）；不能就问 key。"""
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
    return _ask_key(failing)


def _ask_key(failing: list[str]) -> bool:
    """问 DeepSeek 的 key，存下、两家都切过去、问一句（`agents.quickstart`，与页面的弹窗同一段）；
    不通再问，回车跳过。key 不上屏。"""
    title = agents.provider_of(failing[0], agents.QUICKSTART_PROVIDER).title
    print()
    for _ in range(KEY_ATTEMPTS):
        typed = ask_secret(f"粘贴 {title} 的 key（{agents.QUICKSTART_SITE} 申请，粘贴时不显示；"
                           "回车跳过）：")
        if not typed.strip():
            print("  ✗ 跳过了：之后在页面「设置 → AI」里填")
            return False
        results = agents.quickstart(typed)
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


def _line(mark: str, label: str, note: str) -> None:
    clear = "\r\x1b[2K" if sys.stdout.isatty() else ""
    print(f"{clear}  {mark} {label:<{LABEL_WIDTH}}{note}", flush=True)


def _say(ok: bool, name: str, sentence: str) -> None:
    print(f"  {'✓' if ok else '✗'} {TITLES[name]} {sentence}", flush=True)


def _downloading(title: str) -> toolchain.Progress:
    """要开始下载了：返回给 `toolchain` 报进度的回调。终端里画在同一行；不是终端（桌面 App 的启动
    页、日志）先说一句 `… 标签 下载中`，之后每 PROGRESS_EVERY_S 秒一行已下多少，不是每一块一行
    （外层 #282）。"""
    if sys.stdout.isatty():
        def draw(done: int, total: int | None) -> None:
            size = f"{done / 1e6:.0f}/{total / 1e6:.0f} MB" if total else f"{done / 1e6:.0f} MB"
            print(f"\r  ↓ {title:<{LABEL_WIDTH}}下载中 {size}", end="", flush=True)

        return draw
    print(f"  … {title:<{LABEL_WIDTH}}下载中", flush=True)
    last = time.monotonic()

    def report(done: int, total: int | None) -> None:
        nonlocal last
        now = time.monotonic()
        if now - last < PROGRESS_EVERY_S:
            return
        last = now
        size = f"已下 {done / 1e6:.0f} MB" + (f" / 共 {total / 1e6:.0f} MB" if total else "")
        print(f"  ↓ {title:<{LABEL_WIDTH}}{size}", flush=True)

    return report


def _serve(host: str, port: int, browser: bool) -> int:
    """起服务、等它能连上就开浏览器（`browser`）；已经有一个在跑就只开浏览器。"""
    url = f"http://{host}:{port}"
    if _listening(host, port):
        if browser:
            webbrowser.open(url)
        print(f"\n服务已经在跑{'，浏览器已打开' if browser else ''} {url}", flush=True)
        return EXIT_OK
    if browser:
        threading.Thread(target=_open_when_up, args=(host, port, url), daemon=True).start()
    print(f"\n{'浏览器马上打开' if browser else '服务地址'} {url}\n"
          f"关掉这个窗口服务就停；下次启动：{paths.cli()} serve\n", flush=True)
    return serve.cmd_serve(_serve_args(host, port))


def _serve_args(host: str, port: int) -> argparse.Namespace:
    """交给 serve 的参数照 serve 自己的 parser 生成：serve 加了参数（外壳要的那些），这里自动带上
    它的缺省，`make up` 与一行命令的最后一步不会因为少一个属性而断（外层 #282）。"""
    parser = argparse.ArgumentParser(prog=paths.CLI_NAME)
    serve.add_parser(parser.add_subparsers())
    return parser.parse_args(["serve", "--host", host, "--port", str(port)])


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
    group.add_argument("--no-serve", action="store_true", help="做完不起服务（桌面 App、测试用）")
    group.add_argument("--no-input", action="store_true",
                       help="桌面 App 用：不问 key、不探模型、不开浏览器，两家 CLI 一律装进家里")
    group.add_argument("--host", default="127.0.0.1")
    group.add_argument("--port", type=int, default=8765)
    group.set_defaults(func=cmd_setup)
