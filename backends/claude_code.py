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
import threading
import time
from datetime import UTC, datetime
from pathlib import Path

from backends import RunResult
from backends._snapshot import diff, snapshot

# 不读 user/project/local 任何设置源：执行层会话因此不继承本机的
# CLAUDE.md、hook、plugin、自定义 agent（P-11）
ISOLATION_ARGS = ("--no-session-persistence", "--setting-sources", "", "--strict-mcp-config",
                  "--disable-slash-commands")
_TAIL_CHARS = 4000


def _env_num(name: str, default: float, cast: type) -> float:
    """读一个数值配置项。值非法就抛，不静默回落默认值（P-7）。"""
    raw = os.environ.get(name)
    value = default if raw is None else cast(raw)
    assert isinstance(value, (int, float)) and value > 0, f"{name} 必须是正数，得到 {value!r}"
    return value


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
    def __init__(self, cli: str = "claude", bash_rules: tuple[str, ...] = ()) -> None:
        # bash_rules 显式传入而不是默认放行：dontAsk 下只读 Bash（grep/ls/wc）本就自动放行，
        # 写操作（sed -i）实测被拒——默认不给 Bash 规则，才守得住"只能改 allowed_paths"。
        self.cli = cli
        self.bash_rules = tuple(bash_rules)

    def build_argv(self, prompt: str, cwd: Path, allowed_paths: list[Path]) -> list[str]:
        rules: list[str] = []
        for path in allowed_paths:
            rules += [f"Edit({_abs_glob(path)})", f"Write({_abs_glob(path)})"]
        rules.append(f"Read({_abs_glob(cwd)})")  # 读整个工作目录：harness 与 data 要看得见
        rules += self.bash_rules
        argv = [self.cli, "-p", prompt, "--output-format", "stream-json", "--verbose",
                "--permission-mode", "dontAsk", *ISOLATION_ARGS,
                "--allowedTools", *rules,
                "--max-turns", str(int(_env_num("AI4SCI_EXECUTOR_MAX_TURNS", 30, int))),
                "--max-budget-usd", str(_env_num("AI4SCI_EXECUTOR_MAX_BUDGET_USD", 2.0, float))]
        model = os.environ.get("AI4SCI_EXECUTOR_MODEL")
        if model:  # 缺省不传，让 CLI 用它自己的默认模型
            argv += ["--model", model]
        return argv

    def run(self, prompt: str, cwd: Path, timeout_s: float,
            allowed_paths: list[Path]) -> RunResult:
        before = snapshot(cwd)
        argv = self.build_argv(prompt, cwd, allowed_paths)
        raw: list[str] = []
        err: list[str] = []
        started = time.monotonic()
        # start_new_session：自成进程组，超时时 killpg 能一起带走 CLI 派生的子进程（sleep 之类）
        # stdin 必须给 DEVNULL：实测不给的话 CLI 会等 3 秒 stdin 再继续
        proc = subprocess.Popen(argv, cwd=str(cwd), stdin=subprocess.DEVNULL,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                text=True, start_new_session=True)
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
        cost, duration_s = final_metrics(events, timed_out, wall_s)
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


def final_metrics(events: list[dict], timed_out: bool, wall_s: float) -> tuple[float, float]:
    """成本与耗时只认最终 result 事件；拿不到就抛，不填 0 蒙混。

    唯一的例外是超时被杀：result 事件根本没机会发出来，此时成本填 NaN 表示"未知"。

    实测到的 result.subtype：`success`、`error_max_turns`、`error_max_budget_usd`。
    三者都带 total_cost_usd，所以这里不区分——失败分类是 runner 读 events 的事，不是本函数的事。
    """
    result = next((e for e in reversed(events) if e.get("type") == "result"), None)
    if result is None:
        if timed_out:
            return math.nan, wall_s
        raise RuntimeError(
            "stream-json 事件流里没有 result 事件，拿不到 total_cost_usd 与 duration_ms"
        )
    cost = float(result["total_cost_usd"])
    duration_s = float(result["duration_ms"]) / 1000.0
    assert cost >= 0 and duration_s >= 0, f"result 事件的成本或耗时为负：{cost}, {duration_s}"
    return cost, duration_s


def make_runner() -> ClaudeCodeRunner:
    return ClaudeCodeRunner()
