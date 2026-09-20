"""Claude Code 执行层适配器：`claude -p ... --output-format stream-json`。

隔离位由 R-1 spike 实测定下（外层 issue #20）：
- `--setting-sources ""` 是唯一的承重位。不带它时项目 CLAUDE.md 会进上下文（探针原样吐回）、
  plugin / hook / 自定义 agent 全部加载，一句 pong 花 $0.459；带上后 CLAUDE.md 不进、
  plugins=[]、hooks 不触发，同一句 pong $0.050。
- `--bare` 能达到同样效果但会跳过 keychain 读取导致 Not logged in，不能用。
- `--strict-mcp-config` 清空 MCP（mcp_servers 从 6 个变 0），`--disable-slash-commands` 清空 skill。
- 权限一律走 `--permission-mode dontAsk` + `--allowedTools` 白名单，
  绝不用 `--dangerously-skip-permissions` / `bypassPermissions`。
"""

from __future__ import annotations

import json
import math
import os
import signal
import subprocess
import sys
import threading
import time
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

from backends import ChatEvent, Choice, Knobs, RunResult, Tuning
from backends._snapshot import diff, snapshot

# 不读 user/project/local 任何设置源：会话因此不继承本机的 CLAUDE.md、hook、plugin、
# 自定义 agent（P-11）。执行层再加 --no-session-persistence（一次性会话，不留）；协调层
# 不加：多轮靠 --resume 续接，靠的就是 CLI 自己的会话持久化
ISOLATION_ARGS = ("--setting-sources", "", "--strict-mcp-config", "--disable-slash-commands")
# CLI 自带的联网工具，两层都放行（端口要求）。实测 2026-09-20：dontAsk 下不在白名单就被拒，
# 拒绝信息还说「可以用别的工具试」，agent 于是拿 Bash 里的 curl 硬凑；白名单加上后搜索与读页都通
WEB_TOOLS = ("WebSearch", "WebFetch")
# 与 framework/run/jobs.py 的 CHAT_ID_ENV 同名：适配器不 import framework（端口方向），
# 名字抄一份，测试对账
CHAT_ID_ENV = "AI4SCI_CHAT_ID"
EXECUTOR_ISOLATION_ARGS = ("--no-session-persistence", *ISOLATION_ARGS)
# 协调层的两个旋钮（外层 #86）。起服务的人在环境里给缺省，人在页面或终端上每轮可改。
MODEL_ENV = "AI4SCI_COORDINATOR_MODEL"
EFFORT_ENV = "AI4SCI_COORDINATOR_EFFORT"
# 模型写 CLI 认的别名（`--model` 也收全名：环境里给了全名照样能用，清单上会多出那一项）
MODELS = (Choice("sonnet", "Sonnet", "快"), Choice("opus", "Opus", "强"),
          Choice("fable", "Fable", "最强"))
# `--effort` 的五档，按 2.1.276 的 --help；顺序就是从浅到深
EFFORTS = (Choice("low", "低"), Choice("medium", "中"), Choice("high", "高"),
           Choice("xhigh", "超高"), Choice("max", "最高"))
_TAIL_CHARS = 4000
# tool_result 进事件的正文上限：页面与 CLI 打印只要开头，全文在 raw 里落盘
_RESULT_CHARS = 4000


def _env_num(name: str, default: float, cast: type) -> float:
    """读一个数值配置项。值非法就抛，不静默回落默认值（P-7）。"""
    raw = os.environ.get(name)
    value = default if raw is None else cast(raw)
    assert isinstance(value, (int, float)) and value > 0, f"{name} 必须是正数，得到 {value!r}"
    return value


def _default_effort() -> str | None:
    """环境里给的缺省思考深度；没给就 None（CLI 自己定），给错就炸，不静默回落（P-7）。"""
    raw = os.environ.get(EFFORT_ENV)
    if not raw:
        return None
    assert raw in {c.id for c in EFFORTS}, \
        f"{EFFORT_ENV} 只认 {', '.join(c.id for c in EFFORTS)}，得到 {raw!r}"
    return raw


def build_env(timeout_s: float, chat_id: str | None = None) -> dict[str, str]:
    """两层会话共用的子进程环境：继承本进程，外加 venv 的 bin 进 PATH、关后台、Bash 超时对齐本轮。

    agent 敲的是裸 `ai4sci`（纲领 P-14：它面前只有这一个入口，不写路径不挂前缀），
    所以起它的服务得让这个名字找得到：把自己解释器所在的 bin 目录**追加**到 PATH 末尾。
    追加不是前置：不让 venv 里的 python / ruff 遮住系统的，agent 用不到它们。
    不 resolve：venv 的 python 是指向系统解释器的软链，解析完就是系统 bin，里面没有 ai4sci
    （实测 #60 第一次真跑就栽在这）。
    关后台与超时对齐（外层 #57）：`claude -p` 里 Bash 超过 CLI 自己的缺省超时（2 分钟）会被自动
    挪到后台，一轮结束后台子进程约 5 秒后被杀；所以 `CLAUDE_CODE_DISABLE_BACKGROUND_TASKS=1` 关掉
    全部后台机制，并把 Bash 超时抬到与本轮超时一样长——唯一会杀它的只有我们自己的定时器。
    `chat_id` 只有协调层有：agent 调用的命令从环境里知道自己属于哪段对话，`--detach` 的作业记下它，
    跑完叫醒（外层 #63）；不给就不留上一段的。"""
    millis = str(int(timeout_s * 1000))
    bin_dir = str(Path(sys.executable).parent)
    inherited = os.environ.get("PATH", "")
    path = f"{inherited}{os.pathsep}{bin_dir}" if inherited else bin_dir
    env = {**os.environ, "PATH": path, "CLAUDE_CODE_DISABLE_BACKGROUND_TASKS": "1",
           "BASH_DEFAULT_TIMEOUT_MS": millis, "BASH_MAX_TIMEOUT_MS": millis}
    env.pop(CHAT_ID_ENV, None)
    if chat_id:
        env[CHAT_ID_ENV] = chat_id
    return env


def _abs_glob(path: Path) -> str:
    # 实测：Claude Code 的权限规则里单个 `/` 开头按项目根解释，文件系统绝对路径必须写成 `//`。
    # 写成 `Write(/abs/code/**)` 时对 code/ 下的 Write 照样被拒，改 `//` 后才放行。
    return f"//{path.resolve().as_posix().lstrip('/')}/**"


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


class ClaudeCodeRunner:
    def __init__(self, cli: str = "claude") -> None:
        self.cli = cli

    def build_argv(self, prompt: str, cwd: Path, allowed_paths: list[Path],
                   bash_rules: tuple[str, ...] = ()) -> list[str]:
        # bash_rules 由调用方显式给而不是默认放行：dontAsk 下只读 Bash（grep/ls/wc）本就自动放行，
        # 写操作（sed -i）实测被拒——不给 Bash 规则，才守得住"只能改 allowed_paths"
        rules: list[str] = []
        for path in allowed_paths:
            rules += [f"Edit({_abs_glob(path)})", f"Write({_abs_glob(path)})"]
        rules.append(f"Read({_abs_glob(cwd)})")  # 读整个工作目录：harness 与 data 要看得见
        rules += [*bash_rules, *WEB_TOOLS]
        argv = [self.cli, "-p", prompt, "--output-format", "stream-json", "--verbose",
                "--permission-mode", "dontAsk", *EXECUTOR_ISOLATION_ARGS,
                "--allowedTools", *rules,
                "--max-turns", str(int(_env_num("AI4SCI_EXECUTOR_MAX_TURNS", 30, int))),
                "--max-budget-usd", str(_env_num("AI4SCI_EXECUTOR_MAX_BUDGET_USD", 2.0, float))]
        model = os.environ.get("AI4SCI_EXECUTOR_MODEL")
        if model:  # 缺省不传，让 CLI 用它自己的默认模型
            argv += ["--model", model]
        return argv

    def run(self, prompt: str, cwd: Path, timeout_s: float,
            allowed_paths: list[Path], bash_rules: tuple[str, ...] = ()) -> RunResult:
        before = snapshot(cwd)
        argv = self.build_argv(prompt, cwd, allowed_paths, bash_rules)
        raw: list[str] = []
        err: list[str] = []
        started = time.monotonic()
        # start_new_session：自成进程组，超时时 killpg 能一起带走 CLI 派生的子进程（sleep 之类）
        # stdin 必须给 DEVNULL：实测不给的话 CLI 会等 3 秒 stdin 再继续
        # 环境与协调层同一份：裸 `ai4sci` 找得到、关后台、Bash 超时对齐本轮（skill 脚本会跑几分钟）
        proc = subprocess.Popen(argv, cwd=str(cwd), stdin=subprocess.DEVNULL,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                text=True, start_new_session=True, env=build_env(timeout_s))
        # stdout 与 stderr 各一个线程排空。只读 stdout 的话，CLI 往 stderr 写满管道缓冲区
        # 就会卡住，表面上是"超时"，真正原因是没人读它（实测 CLI 会往 stderr 打 Warning）
        readers = [threading.Thread(target=lambda: raw.extend(proc.stdout), daemon=True),
                   threading.Thread(target=lambda: err.extend(proc.stderr), daemon=True)]
        for reader in readers:
            reader.start()
        timed_out = False
        try:
            proc.wait(timeout=timeout_s)
        except subprocess.TimeoutExpired:
            timed_out = True
            kill_tree(proc.pid)
            proc.wait()
        for reader in readers:
            reader.join(timeout=5)
        wall_s = time.monotonic() - started
        events, junk = parse_events(raw)
        self._persist(cwd, raw, err)
        cost, duration_s = final_metrics(events, timed_out, wall_s, proc.returncode)
        return RunResult(exit_code=proc.returncode, events=events,
                         changed_files=diff(before, snapshot(cwd)), cost_usd=cost,
                         duration_s=duration_s, timed_out=timed_out,
                         stdout_tail="".join(junk + err)[-_TAIL_CHARS:])

    @staticmethod
    def _persist(cwd: Path, raw: list[str], err: list[str]) -> None:
        # 完整事件流落盘取证，给执行层的只有摘要（P-9：日志不进 prompt）
        log_dir = cwd / ".ai4sci"
        log_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
        (log_dir / f"executor-{stamp}.jsonl").write_text("".join(raw), encoding="utf-8")
        if err:  # stderr 单独一份：排障时先看它，不用在事件流里翻
            (log_dir / f"executor-{stamp}.stderr.log").write_text("".join(err), encoding="utf-8")


def parse_events(raw: list[str]) -> tuple[list[dict], list[str]]:
    """拆成结构化事件与非 JSON 行。非 JSON 行不丢，原样留给 stdout_tail（不吞）。"""
    events: list[dict] = []
    junk: list[str] = []
    for line in raw:
        if not line.strip():
            continue
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError:
            junk.append(line)
    return events, junk


def final_metrics(
    events: list[dict], timed_out: bool, wall_s: float, exit_code: int = 0
) -> tuple[float, float]:
    """成本与耗时只认最终 result 事件；拿不到就抛，不填 0 蒙混。

    例外是进程没能正常走完：超时被杀、被外部 kill、CLI 自己崩了（退出码非 0），
    result 事件根本没机会发出来，此时成本填 NaN 表示"未知"，由调用方把这一轮判成
    执行层失败。正常退出（0）却没有 result 才是协议坏了，照抛。

    实测到的 result.subtype：`success`、`error_max_turns`、`error_max_budget_usd`。
    三者都带 total_cost_usd，所以这里不区分——失败分类是 runner 读 events 的事，不是本函数的事。
    """
    result = next((e for e in reversed(events) if e.get("type") == "result"), None)
    if result is None:
        if timed_out or exit_code != 0:
            return math.nan, wall_s
        raise RuntimeError(
            "stream-json 事件流里没有 result 事件，拿不到 total_cost_usd 与 duration_ms"
        )
    cost = float(result["total_cost_usd"])
    duration_s = float(result["duration_ms"]) / 1000.0
    assert cost >= 0 and duration_s >= 0, f"result 事件的成本或耗时为负：{cost}, {duration_s}"
    return cost, duration_s


class ClaudeCodeChat:
    """协调层适配器：同一个 CLI，多轮靠 `--resume <session id>`，指南靠 `--append-system-prompt`。

    实测（2026-09-16，haiku）：第一轮 init 事件给 session_id，第二轮 `--resume` 带上它，
    模型记得第一轮的内容，result 事件的 session_id 与第一轮相同；两轮共 $0.02。
    事件边跑边出：stdout 逐行读、逐行翻译，stderr 另起线程排空（同 Runner 的教训）。

    长命令不许进后台（外层 #57，`build_env`）：实测 `cap auto-research --max-iters 3` 第 4 轮死在
    半路，因为 Bash 被 CLI 挪到后台、一轮结束就被杀；现在唯一会杀它的只有我们自己的定时器，杀了会报
    "这一轮超过 N 秒"。

    花费：`--resume` 时 result 事件的 `total_cost_usd` 是整段会话到此刻的累计，不是这一轮的（实测
    2026-09-19：七轮单调递增 0.165 → 0.284，`modelUsage` 的 token 数也是累计），所以报 `"session"`，
    这一轮花了多少由框架减。
    """

    cost_reporting = "session"

    def __init__(self, cli: str = "claude") -> None:
        self.cli = cli

    @staticmethod
    def knobs() -> Knobs:
        """有哪些模型、哪几档思考深度、不选时用什么。缺省模型是环境里给的那个（没给就 None：
        CLI 自己定，我们不猜）；给的是清单外的全名就把它也列上，页面上才对得上号。"""
        model = os.environ.get(MODEL_ENV) or None
        models = MODELS
        if model is not None and model not in {c.id for c in MODELS}:
            models = (*MODELS, Choice(model, model, "环境里给的"))
        return Knobs(models=models, efforts=EFFORTS, model=model, effort=_default_effort())

    def build_argv(
        self, message: str, cwd: Path, *, session_id: str | None, system_prompt: str,
        allowed_paths: list[Path], bash_rules: tuple[str, ...],
        readable_paths: list[Path] = (), tuning: Tuning | None = None,
    ) -> list[str]:
        rules: list[str] = []
        for path in allowed_paths:
            rules += [f"Edit({_abs_glob(path)})", f"Write({_abs_glob(path)})"]
        rules.append(f"Read({_abs_glob(cwd)})")
        # 工作目录之外能读不能写的目录（研究助理看流程库）：`--add-dir` 让 Read / Glob / Grep 在
        # dontAsk 下不被拒；Edit / Write 的白名单没有它，写照旧被拒
        for path in readable_paths:
            rules.append(f"Read({_abs_glob(path)})")
        rules += [*bash_rules, *WEB_TOOLS]
        argv = [self.cli, "-p", message, "--output-format", "stream-json", "--verbose",
                "--include-partial-messages",  # 逐字吐（端口的 delta 事件，外层 #65）
                "--permission-mode", "dontAsk", *ISOLATION_ARGS,
                "--allowedTools", *rules,
                "--max-turns", str(int(_env_num("AI4SCI_COORDINATOR_MAX_TURNS", 50, int))),
                "--max-budget-usd",
                str(_env_num("AI4SCI_COORDINATOR_MAX_BUDGET_USD", 2.0, float))]
        if readable_paths:
            argv += ["--add-dir", *(str(Path(p).resolve()) for p in readable_paths)]
        if system_prompt:
            argv += ["--append-system-prompt", system_prompt]
        if session_id:
            argv += ["--resume", session_id]
        # 这一轮选的压过环境里的缺省；都没有就不传，让 CLI 用它自己的
        picked = tuning or Tuning()
        model = picked.model or os.environ.get(MODEL_ENV)
        if model:
            argv += ["--model", model]
        effort = picked.effort or _default_effort()
        if effort:
            if effort not in {c.id for c in EFFORTS}:
                raise ValueError(
                    f"思考深度只认 {', '.join(c.id for c in EFFORTS)}，得到 {effort!r}")
            argv += ["--effort", effort]
        return argv

    def turn(
        self, message: str, cwd: Path, timeout_s: float, *, session_id: str | None,
        system_prompt: str, allowed_paths: list[Path], bash_rules: tuple[str, ...],
        readable_paths: list[Path] = (), chat_id: str | None = None,
        tuning: Tuning | None = None,
    ) -> Iterator[ChatEvent]:
        argv = self.build_argv(message, cwd, session_id=session_id, system_prompt=system_prompt,
                               allowed_paths=allowed_paths, bash_rules=bash_rules,
                               readable_paths=readable_paths, tuning=tuning)
        err: list[str] = []
        started = time.monotonic()
        proc = subprocess.Popen(argv, cwd=str(cwd), stdin=subprocess.DEVNULL,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                text=True, start_new_session=True,
                                env=build_env(timeout_s, chat_id))
        drain = threading.Thread(target=lambda: err.extend(proc.stderr), daemon=True)
        drain.start()
        # 超时由定时器杀树：主线程在逐行读 stdout，不能同时 wait(timeout)
        timed_out = threading.Event()

        def _kill() -> None:
            timed_out.set()
            kill_tree(proc.pid)

        timer = threading.Timer(timeout_s, _kill)
        timer.start()
        seen_result = False
        try:
            for line in proc.stdout:
                event = _translate(line)
                if event is None:
                    continue
                seen_result = seen_result or event.kind == "done"
                yield event
        finally:
            timer.cancel()
            proc.wait()
            drain.join(timeout=5)
        if timed_out.is_set():
            yield ChatEvent("error", text=f"这一轮超过 {timeout_s:g} 秒，进程树已杀",
                            is_error=True, exit_code=proc.returncode,
                            duration_s=time.monotonic() - started,
                            raw={"stderr_tail": "".join(err)[-_TAIL_CHARS:]})
        elif not seen_result:
            yield ChatEvent("error", is_error=True, exit_code=proc.returncode,
                            duration_s=time.monotonic() - started,
                            text=(f"CLI 退出码 {proc.returncode}，没有 result 事件："
                                  f"{''.join(err)[-_TAIL_CHARS:].strip() or '无 stderr'}"),
                            raw={"stderr_tail": "".join(err)[-_TAIL_CHARS:]})


def _translate(line: str) -> ChatEvent | None:
    """一行 stream-json → 一个（或零个）ChatEvent。非 JSON 行与不关心的事件返回 None。

    形状按实测：`system/init` 带 session_id；`assistant.message.content[]` 里 text / tool_use /
    thinking；`user.message.content[]` 里 tool_result（content 是字符串或块列表）；
    `system/permission_denied`；`result` 带 total_cost_usd / duration_ms / result 文本；
    开了 `--include-partial-messages` 后 `stream_event.event` 是 API 的原生流事件，只翻
    `content_block_delta` 里的 `text_delta`（thinking_delta / signature_delta 不是给人看的）。
    """
    if not line.strip():
        return None
    try:
        raw = json.loads(line)
    except json.JSONDecodeError:
        return None
    kind = raw.get("type")
    sid = raw.get("session_id")
    if kind == "system":
        if raw.get("subtype") == "init":
            return ChatEvent("init", session_id=sid, raw=raw)
        if raw.get("subtype") == "permission_denied":
            return ChatEvent("denied", tool=str(raw.get("tool_name", "")),
                             text=str(raw.get("message", "")), is_error=True,
                             session_id=sid, raw=raw)
        return None
    if kind == "stream_event":
        event = raw.get("event") or {}
        delta = event.get("delta") or {}
        if event.get("type") == "content_block_delta" and delta.get("type") == "text_delta":
            piece = delta.get("text")
            return ChatEvent("delta", text=piece, session_id=sid, raw=raw) if piece else None
        return None
    if kind == "assistant":
        blocks = raw.get("message", {}).get("content", [])
        texts = [b["text"] for b in blocks if b.get("type") == "text" and b.get("text")]
        tools = [b for b in blocks if b.get("type") == "tool_use"]
        if tools:
            block = tools[0]
            return ChatEvent("tool_use", tool=str(block.get("name", "")),
                             tool_input=dict(block.get("input") or {}), session_id=sid, raw=raw)
        if texts:
            return ChatEvent("text", text="\n".join(texts), session_id=sid, raw=raw)
        return None
    if kind == "user":
        blocks = raw.get("message", {}).get("content", [])
        results = [b for b in blocks if isinstance(b, dict) and b.get("type") == "tool_result"]
        if not results:
            return None
        block = results[0]
        content = block.get("content", "")
        if isinstance(content, list):
            content = "\n".join(str(c.get("text", "")) for c in content if isinstance(c, dict))
        return ChatEvent("tool_result", text=str(content)[:_RESULT_CHARS],
                         is_error=bool(block.get("is_error")), session_id=sid, raw=raw)
    if kind == "result":
        cost = raw.get("total_cost_usd")
        duration = raw.get("duration_ms")
        text = raw.get("result")
        return ChatEvent("done", text=text.strip() if isinstance(text, str) else "",
                         is_error=bool(raw.get("is_error")), session_id=sid,
                         cost_usd=float(cost) if cost is not None else math.nan,
                         duration_s=float(duration) / 1000.0 if duration is not None else 0.0,
                         exit_code=0, raw=raw)
    return None


def make_runner() -> ClaudeCodeRunner:
    return ClaudeCodeRunner()


def make_chat() -> ClaudeCodeChat:
    return ClaudeCodeChat()
