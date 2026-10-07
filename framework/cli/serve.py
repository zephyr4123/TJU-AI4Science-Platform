"""`ai4sci serve`：起网页的后端（HTTP + SSE）并把页面端出去，常驻直到叫停。

cli 层里唯一常驻的命令：它不是"跑一个能力"，是给页面一个门。能力清单、流程库、拼流程检查与描述符表
从 `capabilities.discover` 与 `contracts.workflows` 拿，以函数传给 server
（chat 层不认识 capabilities）。平台的家是 `AI4SCI_HOME`（缺省 `~/.ai4sci`）：项目、编辑台的对话与
人存的流程都在它下面；流程库 = 出厂的 + 人存的（`_common.library`），页面存流程只写后者。

页面是 `ui/web` 构建出来的静态文件（`ui/README.md`）：缺省端 `ui/web/dist`，没构建就只开接口。
TUI 不走这里——它是终端进程，直接当这些接口的客户端。

起与停（外层 #282 §3、#285，外壳与后端的约定）：绑上地址以后 stdout 打且只打一行 `ok http://…`，日志
全走 stderr；绑不上一句话退 3。叫停有三种，走同一条路：Ctrl-C、POSIX 上的 SIGTERM、带
`--until-stdin-closes` 时标准输入读到头（外壳退出时关掉它；外壳崩了内核替它关）。先不再接请求，
再把这个服务起的、还在跑的进程树（`procs` 的登记：一轮对话的 CLI 与它派生的一切）逐棵杀掉，退 0；
后台作业不在登记里，照跑。登记同时落在平台的家里的 `run/serve-<pid>.json`：服务自己崩了、被杀了，
下一个服务起来时按它收掉上一个留下的轮次。
"""

from __future__ import annotations

import argparse
import errno
import logging
import os
import signal
import sys
import threading
from pathlib import Path

import procs
from framework import paths, skills
from framework.capabilities import abilities, discover, stage_table
from framework.chat import guide, settings
from framework.chat.server import ChatServer
from framework.cli import compute as compute_cli
from framework.cli._common import (
    EXIT_INVALID,
    EXIT_OK,
    EXIT_PORT,
    EXIT_USAGE,
    library,
    setup_logging,
)
from framework.contracts import workflows

LOGGER = logging.getLogger("ai4sci.serve")
DEFAULT_UI_DIR = paths.ui_dir()
# 在跑的服务的登记文件：`serve-<pid>.json`，放在平台的家里的 `run/`（`paths.run_dir`）
RUN_FILE = "serve-{pid}.json"


def _add_compute(body: dict) -> dict:
    """页面「设置 → 算力 → 添加」：与 `ai4sci compute add` 同一段代码（写清单、就地探测、记回），
    回新的一整份设置。"""
    for key in ("name", "ssh", "key"):
        if not isinstance(body.get(key), str) or not body[key].strip():
            raise ValueError(f"body 要有非空的 {key}")
    compute_cli.add_and_check(body["name"].strip(), body["ssh"].strip(), body["key"].strip(),
                              str(body.get("root") or compute_cli.DEFAULT_ROOT),
                              bool(body.get("default")))
    return settings.snapshot()


def _descriptors() -> dict[str, object]:
    return abilities.steps()


def _skill_names() -> frozenset[str]:
    """三处库里 skill 的名字；与步骤重名当场报，不让页面拿到分辨不出的清单。"""
    names = abilities.skill_names()
    abilities.check_disjoint(set(discover()), names)
    return names


def _catalog() -> list[dict]:
    """与 `ai4sci show caps --json` 同一个形状：步骤描述符加 tag 与反查出来的 used_by。"""
    uses = workflows.used_by(library().load_valid())
    return [{**module.DESCRIPTOR.to_dict(), "kind": abilities.KIND_STEP,
             "used_by": uses.get(name, [])} for name, module in discover().items()]


def _skills() -> list[dict]:
    """能力库里 tag 为 skill 的那些：名字、一行、出处、脚本名，加反查出来的 used_by。"""
    uses = workflows.used_by(library().load_valid())
    return [{**entry, "used_by": uses.get(entry["name"], [])}
            for entry in abilities.skill_entries()]


def _skill(name: str) -> dict | None:
    """一个 skill 带正文；没有是 None（404），不合格的 SkillInvalid 是 ValueError（422）。"""
    try:
        detail = abilities.skill_detail(name)
    except skills.SkillNotFound:
        return None
    uses = workflows.used_by(library().load_valid())
    return {**detail, "used_by": uses.get(name, [])}


def _workflows() -> list[dict]:
    return library().describe(_descriptors(), _skill_names())


def _descriptor_map() -> dict[str, object]:
    return _descriptors()


def _save_workflow(doc: dict) -> dict:
    """编辑台存流程：名字不给由平台起（派生的 `<家族名>-<序号>`，P-15），核对形状、通不通、
    与库里有没有一模一样的，写进用户库（出厂的名字拒），回它在清单里的样子（带家族与差异）。"""
    catalog, skills = _descriptors(), _skill_names()
    overwrite = bool(doc.pop("overwrite", False))
    lib = library()
    saved = lib.save(doc, catalog, skills=skills, overwrite=overwrite)
    return next(row for row in lib.describe(catalog, skills) if row["name"] == saved.name)


def _check_workflow(doc: dict) -> dict:
    """编辑台拼着的那条流程有没有问题：与存流程同一套检查，只查不写；形状不对也当问题报，页面不该为此
    拿 500。名字、标题、说明还没填是常态（人先排阶段），这里只查阶段那部分，三样空着的补个占位；
    `from`（载入出厂的再改时带着父流程的名字）是存的时候才落的血缘，不归这里查（P-15）。"""
    catalog = _descriptors()
    name = str(doc.get("name") or "").strip() or "draft"
    doc = {k: v for k, v in doc.items() if k not in ("overwrite", "from")}
    doc = {**doc, "name": name, "title": str(doc.get("title") or "").strip() or "-",
           "summary": str(doc.get("summary") or "").strip() or "-"}
    try:
        workflow = workflows.parse_workflow(f"{name}.yaml", doc)
    except workflows.WorkflowInvalid as exc:
        # 文件名前缀是给终端看的；页面上这条流程还没有文件
        return {"covers": [], "remarks": [], "problems": [str(exc).removeprefix(f"{name}.yaml: ")]}
    return {"covers": workflow.covered, "remarks": workflows.remarks(workflow),
            "problems": workflows.workflow_problems(workflow, catalog, _skill_names())}


def cmd_serve(args: argparse.Namespace) -> int:
    if args.ui:
        ui_dir = Path(args.ui)
        if not (ui_dir / "index.html").is_file():
            print(f"页面目录里没有 index.html：{ui_dir}", file=sys.stderr)
            return EXIT_USAGE
    else:
        ui_dir = DEFAULT_UI_DIR if (DEFAULT_UI_DIR / "index.html").is_file() else None
    setup_logging()
    try:
        server = ChatServer((args.host, args.port), home=paths.home(), catalog=_catalog,
                            skills=_skills, skill=_skill, skill_names=_skill_names,
                            workflows=_workflows, check_workflow=_check_workflow,
                            save_workflow=_save_workflow, descriptors=_descriptor_map,
                            stage_table=stage_table, add_compute=_add_compute, ui_dir=ui_dir)
    except guide.GuideMissing as exc:
        print(str(exc), file=sys.stderr)
        return EXIT_INVALID
    except OSError as exc:  # 绑不上（GuideMissing 也是 OSError，上一条先接走了）
        print(f"{args.host}:{args.port} 用不了：{_unbindable(exc)}", file=sys.stderr)
        return EXIT_PORT
    run = paths.run_dir()
    for left in sorted(run.glob(RUN_FILE.format(pid="*"))):
        procs.reap(left)  # 主人已经不在的那几份：上一个服务崩了留下的轮次
    procs.keep_in(run / RUN_FILE.format(pid=os.getpid()))
    _stop_on_signal(server)
    if args.until_stdin_closes:
        _watch_stdin(server)
    host, port = server.server_address[:2]
    print(f"ok http://{host}:{port}\thome={server.home}\tui={ui_dir or '-'}", flush=True)
    if args.host in WILDCARD_HOSTS:
        print(f"注意：只收发给本机的请求（打开 http://127.0.0.1:{port}）。别的机器要连，"
              "--host 写这台的 IP，或者走 SSH 隧道", file=sys.stderr, flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        LOGGER.info("serve_stopping reason=ctrl_c")
    finally:
        server.server_close()
        killed = procs.kill_all()
        LOGGER.info("serve_stopped killed=%s", killed)
    return EXIT_OK


def _unbindable(exc: OSError) -> str:
    """绑不上的原因，一句人话。Windows 上装过 Hyper-V、WSL、Docker 的机器，保留端口段每次开机都变，
    落进去报的是 WSAEACCES（PermissionError），不是「被占」。"""
    if exc.errno in (errno.EADDRINUSE, getattr(errno, "WSAEADDRINUSE", errno.EADDRINUSE)):
        return "端口被别的程序占着：换一个 --port，或先关掉占着它的那个"
    if isinstance(exc, PermissionError):
        return "系统不让用这个端口（Windows 的保留端口段，或要管理员权限）：换一个 --port"
    if exc.errno in (errno.EADDRNOTAVAIL, getattr(errno, "WSAEADDRNOTAVAIL", errno.EADDRNOTAVAIL)):
        return "本机没有这个地址：--host 写错了？"
    return str(exc)


def _stop(server: ChatServer, reason: str) -> None:
    """叫停：不再接请求，`serve_forever` 返回，主线程接着收拾。`shutdown` 要等主线程的循环走完，
    所以另起一个线程调（在主线程里调会自己等自己）。"""
    LOGGER.info("serve_stopping reason=%s", reason)
    threading.Thread(target=server.shutdown, daemon=True, name="serve-stop").start()


# 听所有地址的写法：门禁只认发给本机的请求（Host 是 127.0.0.1、localhost 或 --host 写的那个），
# 它们不是任何一个 Host，从别的机器打开都是 403（外层 #283）
WILDCARD_HOSTS = ("0.0.0.0", "::")
# Windows 关掉控制台窗口、注销、关机（CTRL_CLOSE_EVENT / CTRL_LOGOFF_EVENT / CTRL_SHUTDOWN_EVENT）
CONSOLE_CLOSING = (2, 5, 6)
_console_handler = None  # 交给系统的回调要一直有人引用着，不然被回收了系统还会调它


def _stop_on_signal(server: ChatServer) -> None:
    """SIGTERM（launchd、kill、外壳收拾时）、Ctrl-C 与关掉终端窗口（SIGHUP）走同一条退出（外层
    #285）。nohup 起的忽略着 SIGHUP，照它的意思不接。Windows 上信号发不进来，关窗口、注销、关机是
    控制台事件：系统给几秒、之后直接结束进程，finally 不跑，所以在处理函数里就把轮次收拾掉。"""
    if os.name == "nt":
        _on_console_close()
        return
    signal.signal(signal.SIGTERM, lambda signum, frame: _stop(server, "SIGTERM"))
    if signal.getsignal(signal.SIGHUP) is not signal.SIG_IGN:
        signal.signal(signal.SIGHUP, lambda signum, frame: _stop(server, "SIGHUP"))


def _on_console_event(event: int) -> bool:
    """控制台事件的处理：关窗口、注销、关机就收拾在跑的轮次，算处理过了；别的（Ctrl-C、Ctrl-Break）
    交给 Python 自己的。"""
    if event not in CONSOLE_CLOSING:
        return False
    LOGGER.info("serve_stopping reason=console_event_%d", event)
    LOGGER.info("serve_stopped killed=%s", procs.kill_all())
    return True


def _on_console_close() -> None:
    global _console_handler
    import ctypes
    from ctypes import wintypes

    _console_handler = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.DWORD)(_on_console_event)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    if not kernel32.SetConsoleCtrlHandler(_console_handler, True):
        LOGGER.warning("console_handler_failed error=%d", ctypes.get_last_error())


def _watch_stdin(server: ChatServer) -> None:
    """--until-stdin-closes：标准输入读到头就叫停，外壳退出时关掉它，外壳崩了内核替它关（外层
    #285）。读的是复制出来的那一份，0 号换成一根已经读到头的空管道：之后起的子进程缺省继承 0 号，
    Windows 上 Python 子进程启动时碰到这根正被另一个线程同步读着的管道会卡死（测试机上实测，外层
    #282 审查），也不该分走外壳的这根线。用 os.read 读、不经 sys.stdin 的缓冲：退出时还挂着它，
    解释器会报 Fatal Python error。"""
    watched = os.dup(0)
    empty, writer = os.pipe()
    os.close(writer)
    os.dup2(empty, 0)
    os.close(empty)

    def watch() -> None:
        while os.read(watched, 1 << 16):
            pass
        _stop(server, "stdin_closed")

    threading.Thread(target=watch, daemon=True, name="stdin-watch").start()


def add_parser(groups: argparse._SubParsersAction) -> None:
    serving = groups.add_parser("serve", help="起网页后端：HTTP + SSE，端出页面，常驻")
    serving.add_argument("--host", default="127.0.0.1",
                         help="听哪个地址；只收 Host 是 127.0.0.1、localhost 或这个地址的请求"
                              "（0.0.0.0 只能本机打开，别的机器要连写这台的 IP）")
    serving.add_argument("--port", type=int, default=8765)
    serving.add_argument("--ui", default=None,
                         help=f"页面构建目录，缺省 {DEFAULT_UI_DIR}（没构建就只开接口）")
    serving.add_argument("--until-stdin-closes", action="store_true",
                         help="标准输入读到头就停（外壳起服务时用：外壳退出或崩了都会关掉它）")
    serving.set_defaults(func=cmd_serve)
