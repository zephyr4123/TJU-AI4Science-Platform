"""Codex 适配器：`codex exec --json`（执行层一次性会话）与 `codex exec resume`（协调层续接）。

每一条都是 2026-09-22 在本机实测的（codex-cli 0.147.0，ChatGPT Plus 账号登录），flag 与配置键先对过
官方文档（learn.chatgpt.com/docs/*，developers.openai.com/codex/* 308 跳过去）与源码
（github.com/openai/codex 的 rust-v0.147.0：exec/src/cli.rs、exec/src/exec_events.rs）；外层 #131。

- **隔离的承重位是私有 `CODEX_HOME`**（`~/.config/ai4sci/codex-home`，
`AI4SCI_CODEX_HOME` 可指向别处）：
  本机的 config.toml、plugins、MCP、hooks、memories、用户 skills 都不进；`auth.json` 软链到真的
  `~/.codex/auth.json`（登录共用、凭据不复制；token 刷新写穿软链），真的不在就是「没登录」。协调层的
  会话 rollout 也落在私有 home 下，续接靠它。`--ignore-user-config --ignore-rules` 照带（文档点名给
  自动化用的两个开关）。
- **skills 关不干净得自己关**：
`$HOME/.agents/skills` 与随包的 `.system/` 在私有 home 下照样被扫（实测
  88 个个人 skill 全进清单、一句 pong 19k tokens）；只有 `[[skills.config]] path=<SKILL.md 的路径>
  enabled=false` 关得掉（写目录路径不认），所以每次起会话现扫现关（`-c skills.config=[...]`），关完
  12k tokens、agent 自报「No skills available」。
- **沙箱是门**：
`workspace-write` + `sandbox_workspace_write.writable_roots`（exec 与 resume 都认这个
  `-c`；`--add-dir` resume 上没有）。工作区外、HOME 下的写「operation not permitted」退 1，
  `.git` 只读，
  `$TMPDIR` / `/tmp` 缺省可写；网络缺省关，`network_access=true` 才通——`ai4sci` 要 ssh、pip、下载。
  **没有按命令的白名单**（execpolicy 只管沙箱外的命令，未命中即放行），端口的 `bash_rules` 只能写进
  `tool_guide` 让它照做；真门仍是框架事后的 `changed_files`。审批 exec 硬写 never，
  这里显式再带一遍。
- **事件**（`--json`，一行一个）：`thread.started{thread_id}`、`turn.started`、`item.started |
  item.updated | item.completed{item:{id,type,…}}`、`turn.completed{usage}`、
  `turn.failed{error.message}`、
  `error{message}`。item.type：agent_message{text}、reasoning{text}、command_execution{command,
  aggregated_output, exit_code, status}、file_change{changes:[{path,kind}], status}、mcp_tool_call、
  collab_tool_call、web_search{query, action}、todo_list、error{message}。**没有逐字事件**：
  一段话说完
  才来一条 agent_message，所以一段一条 `text`（端口注释里写明了这是 CLI 的限制）。被中断时既无
  turn.completed 也无 turn.failed，流直接断——收尾同时看 EOF。
- **prompt 一律从 stdin 喂**（位置参数 `-`）：stdin 不关它会一直等 EOF（实测挂了 15 分钟）；
resume 只在
  `-` 时读 stdin，给了位置参数就静默丢掉管道里的内容。
- **续接**：`codex exec resume <thread_id> -` 加同一组 `-c`；`--ephemeral` 的线程续不了（no rollout
  found），协调层不带它、执行层带。resume 时 `developer_instructions` 不再生效（线程开头那份留着），
  指南变了的提醒由框架加在话前。
- **指南**走 `-c developer_instructions="<TOML 字符串>"`：叠加在内置指令之外，
不替换（`model_instructions_file`
  是整体替换，官方不建议）；换行与中文实测都行。AGENTS.md 一律不读：`project_doc_max_bytes=0`。
- **联网**：顶层 `web_search="live"`（`tools.web_search=true` 在 0.147 会被反序列化器丢掉），
搜索在服务端，
  read-only 沙箱里也通；事件是 `web_search` item。
- **模型 / 深度**：`-m <slug>` + `-c model_reasoning_effort="<档>"`。0.147 随包的目录：
gpt-5.6-sol / terra /
  luna、gpt-5.5（四款都给 Plus），四款共有 low / medium / high / xhigh（sol、terra 另有 max、ultra，
  luna 有
  max，不进清单，`Knobs.check` 才守得住）。slug 写错是服务端 400：`error` + `turn.failed`，
  退出码 1。
- **成本**：ChatGPT 订阅报不出美元，`turn.completed.usage` 只有 token 数——`cost_usd` 一律 NaN、
usage 进
  raw（端口：绝不填 0）；`cost_reporting = "turn"`。退出码只有 0 / 1；没有轮数 / 花费的闸，
  超时是唯一的闸。
- 长命令 agent 自己等着跑完（sleep 70 实测通过），没有 Claude Code 那种 2 分钟挪后台的机制。
"""

from __future__ import annotations

import json
import math
import os
import shutil
import subprocess
import sys
import threading
import time
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

from backends import AgentProbe, ChatEvent, Choice, Knobs, RunResult, Tuning
from backends._procs import kill_tree
from backends._snapshot import diff, snapshot

__all__ = ["CodexRunner", "CodexChat", "KNOBS", "MODELS", "EFFORTS", "codex_home", "build_env",
           "config_args", "skill_off_paths", "toml_str", "tool_guide", "parse_events", "Translator",
           "final_report", "probe", "parse_version", "make_runner", "make_chat"]

NAME = "codex"
HOME_ENV = "AI4SCI_CODEX_HOME"
REAL_HOME_ENV = "CODEX_HOME"
DEFAULT_HOME = Path.home() / ".config" / "ai4sci" / "codex-home"
AUTH_NAME = "auth.json"
CHAT_ID_ENV = "AI4SCI_CHAT_ID"
MIN_VERSION = (0, 147, 0)
# 起点 terra / medium（P-25）：Plus 的五小时窗 terra 25–200 句、sol 10–100、
# luna 250–2000（官方估计区间），
# 研究助理一段对话几十轮，均衡的那款当起点
MODELS = (Choice("gpt-5.6-terra", "GPT-5.6 Terra", "均衡"),
          Choice("gpt-5.6-sol", "GPT-5.6 Sol", "强"),
          Choice("gpt-5.6-luna", "GPT-5.6 Luna", "快"),
          Choice("gpt-5.5", "GPT-5.5", "上一代"))
EFFORTS = (Choice("low", "低"), Choice("medium", "中"), Choice("high", "高"),
           Choice("xhigh", "超高"))
KNOBS = Knobs(models=MODELS, efforts=EFFORTS, model="gpt-5.6-terra", effort="medium")
# 两层共用的 exec 参数：JSONL、不查 git 仓库（工作区不是仓库）、不读本机配置与 execpolicy
BASE_ARGS = ("--json", "--skip-git-repo-check", "--ignore-user-config", "--ignore-rules")
# 两层共用的配置覆盖（`-c key=value`，值按 TOML 解析）；沙箱与可写根另算
BASE_CONFIG = (
    'approval_policy="never"',       # exec 本就 never，写明
    "project_doc_max_bytes=0",       # 不读 AGENTS.md（源码行为，文档没给开关）
    'web_search="live"',             # 自带的联网搜索（端口要求）
    'sandbox_mode="workspace-write"',  # resume 没有 -s，两种形态都用 -c
    "sandbox_workspace_write.network_access=true",  # ai4sci 要 ssh / pip / 下载
    "features.hooks=false",
    "features.memories=false",
    "mcp_servers={}",
    "notify=[]",
)
_TAIL_CHARS = 4000
_RESULT_CHARS = 4000
# 系统 skills 的目录（随包安装进 CODEX_HOME）、个人 skills、管理员 skills：都要按 SKILL.md 逐个关
SKILL_ROOTS = ("skills/.system",)
USER_SKILLS = Path.home() / ".agents" / "skills"
ADMIN_SKILLS = Path("/etc/codex/skills")
TOOL_GUIDE = """## 工具怎么用

- 读文件、找文件、搜内容用 shell（cat / rg / ls）；改文件用 apply_patch。
- 命令只许跑 {commands}；不要 pip、curl、git，也不要碰工作目录之外的路径——沙箱会拒（operation
  not permitted），拒了就换路子，不要反复试。
- 写完不用自己查行宽、跑 lint：框架会跑 ruff 与校验，问题喂回给你。
"""
# 协调层的同一段：这家没有单独的读文件工具，看文件就是 shell 的只读命令；「只能运行 ai4sci」
# 说的是动作
CHAT_TOOL_GUIDE = """## 工具怎么用

- 看文件、列目录、搜内容用 shell 的只读命令：ls、cat、head、rg、find（原件在 `materials/`，
要看就直接看）。
  这不算「运行动作」——沙箱只让你写工作区，读是放开的。
- 运行动作只用 {commands} 一类命令；不要 pip、curl、git、
python 这类去凑（没有对应的命令就停下来说缺什么）。
- 改文件（需求、流程实例）用 apply_patch 或 ai4sci 的命令，只在工作区里。
"""


def parse_version(text: str) -> tuple[int, ...] | None:
    """`codex --version` 的原文形如 `codex-cli 0.147.0`：取最后一个词的三段数字；认不出返回 None。
    """
    words = text.strip().split()
    parts = words[-1].split(".") if words else []
    if len(parts) < 3 or not all(p.isdigit() for p in parts[:3]):
        return None
    return tuple(int(p) for p in parts[:3])


def toml_str(text: str) -> str:
    """一段任意文字写成 TOML 基本字符串：JSON 的转义规则是它的子集（`"` `\\` 控制字符），
    非 ASCII 原样
    留着（TOML 允许）；DEL 是 TOML 不许裸写、JSON 又不转义的唯一一个，单独处理。"""
    return json.dumps(text, ensure_ascii=False).replace("\x7f", "\\u007f")


def codex_home() -> Path:
    """私有 CODEX_HOME：建目录、把真的 auth.json 软链进来（不复制凭据）。真的没登录就是悬空软链，
    `codex login status` 会说 Not logged in，自检把这句原样给人。"""
    home = Path(os.environ.get(HOME_ENV) or DEFAULT_HOME).expanduser()
    home.mkdir(parents=True, exist_ok=True)
    real = Path(os.environ.get(REAL_HOME_ENV) or (Path.home() / ".codex")).expanduser() / AUTH_NAME
    link = home / AUTH_NAME
    if link.is_symlink() and link.readlink() != real:
        link.unlink()
    if not link.is_symlink():
        assert not link.exists(), f"{link} 是普通文件不是软链：私有 home 里不该有凭据副本"
        link.symlink_to(real)
    return home


def skill_off_paths(home: Path, cwd: Path) -> list[Path]:
    """要关掉的 skill：私有 home 里随包装的系统 skills、`$HOME/.agents/skills`、
    `/etc/codex/skills`，
    以及 cwd 一路往上每级的 `.agents/skills`（文档说 REPO 层这么扫）。只认 SKILL.md 的路径。"""
    roots = [home / r for r in SKILL_ROOTS] + [USER_SKILLS, ADMIN_SKILLS]
    roots += [p / ".agents" / "skills" for p in (cwd.resolve(), *cwd.resolve().parents)]
    found: list[Path] = []
    for root in roots:
        if not root.is_dir():
            continue
        for entry in sorted(root.iterdir()):
            if (entry / "SKILL.md").is_file():
                found.append(entry / "SKILL.md")
    return found


def config_args(writable: list[Path], *, tuning: Tuning | None, skills_off: list[Path],
                developer_instructions: str = "") -> list[str]:
    """`-c` 那一串：基本项、可写根、要关的 skill、模型深度，协调层开新线程时再加指南。"""
    picked = KNOBS.fill(tuning)
    roots = ", ".join(toml_str(str(Path(p).resolve())) for p in writable)
    off = ", ".join("{path=" + toml_str(str(p)) + ", enabled=false}" for p in skills_off)
    items = [*BASE_CONFIG, f"sandbox_workspace_write.writable_roots=[{roots}]",
             f"skills.config=[{off}]", f"model_reasoning_effort={toml_str(picked.effort)}"]
    if developer_instructions:
        items.append(f"developer_instructions={toml_str(developer_instructions)}")
    argv: list[str] = []
    for item in items:
        argv += ["-c", item]
    return [*argv, "-m", picked.model]


def build_env(timeout_s: float, home: Path, chat_id: str | None = None) -> dict[str, str]:
    """子进程环境：继承本进程，venv 的 bin **追加**进 PATH（裸 `ai4sci` 找得到，
    同 Claude Code 的教训）、
    `CODEX_HOME` 指到私有 home、`AI4SCI_CHAT_ID` 告诉它调用的命令属于哪段对话。Codex 缺省把整个环境
    透传给它跑的命令（`shell_environment_policy.inherit = all`），AI4SCI_* 不用另外放行。
    `timeout_s` 留着与 Claude Code 的签名对齐：Codex 没有每条命令的超时，agent 自己等。"""
    assert timeout_s > 0
    bin_dir = str(Path(sys.executable).parent)
    inherited = os.environ.get("PATH", "")
    env = {**os.environ, "PATH": f"{inherited}{os.pathsep}{bin_dir}" if inherited else bin_dir,
           REAL_HOME_ENV: str(home)}
    env.pop(CHAT_ID_ENV, None)
    if chat_id:
        env[CHAT_ID_ENV] = chat_id
    return env


def _commands(bash_rules: tuple[str, ...]) -> str:
    return ("、".join(f"`{p} …`" for p in bash_rules) if bash_rules
            else "（没有：这次一条都不跑）")


def tool_guide(bash_rules: tuple[str, ...]) -> str:
    return TOOL_GUIDE.format(commands=_commands(bash_rules))


def chat_tool_guide(bash_rules: tuple[str, ...]) -> str:
    return CHAT_TOOL_GUIDE.format(commands=_commands(bash_rules))


def parse_events(raw: list[str]) -> tuple[list[dict], list[str]]:
    """拆成结构化事件与非 JSON 行；非 JSON 行原样留给 stdout_tail（不吞）。"""
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


def final_report(events: list[dict]) -> str:
    """收尾的自述 = 最后一条 agent_message；没有就空串，不编。"""
    for event in reversed(events):
        item = event.get("item") or {}
        if event.get("type") == "item.completed" and item.get("type") == "agent_message":
            text = item.get("text")
            return text.strip() if isinstance(text, str) else ""
    return ""


def _write_stdin(proc: subprocess.Popen, text: str) -> None:
    """prompt 走 stdin：另起线程写、写完关——大 prompt 撑满管道时不能卡住读 stdout 的主线程。"""
    def _pump() -> None:
        try:
            proc.stdin.write(text)
        except BrokenPipeError:
            pass  # CLI 没读完就退了（参数错、没登录）：退出码与 stderr 会说明，这里不是失败点
        finally:
            proc.stdin.close()
    threading.Thread(target=_pump, daemon=True).start()


class CodexRunner:
    name = NAME

    def __init__(self, cli: str = "codex") -> None:
        self.cli = cli

    @staticmethod
    def tool_guide(bash_rules: tuple[str, ...]) -> str:
        return tool_guide(bash_rules)

    def build_argv(self, cwd: Path, allowed_paths: list[Path], runtime_paths: list[Path] = (),
                   tuning: Tuning | None = None, *, home: Path | None = None) -> list[str]:
        """一次性会话：`--ephemeral`（不留 rollout）。可写根 = 只许改的目录 + 平台自己要写的目录。
        `--ephemeral` 与 `--color` 只在根形态有（resume 没有）。"""
        home = codex_home() if home is None else home
        writable = [*allowed_paths, *runtime_paths]
        return [self.cli, "exec", *BASE_ARGS, "--ephemeral", "--color", "never",
                "-C", str(Path(cwd).resolve()),
                *config_args(writable, tuning=tuning, skills_off=skill_off_paths(home, Path(cwd))),
                "-"]

    def run(self, prompt: str, cwd: Path, timeout_s: float,
            allowed_paths: list[Path], bash_rules: tuple[str, ...] = (),
            runtime_paths: list[Path] = (), tuning: Tuning | None = None,
            max_turns: int | None = None, max_budget_usd: float | None = None) -> RunResult:
        # max_turns / max_budget_usd：Codex 没有这两个闸（文档与 --help 都没有），超时是唯一的闸；
        # bash_rules 进了 tool_guide（调用方拼提示时已加），这里没有可翻的白名单
        home = codex_home()
        before = snapshot(cwd)
        argv = self.build_argv(cwd, allowed_paths, runtime_paths, tuning, home=home)
        raw: list[str] = []
        err: list[str] = []
        started = time.monotonic()
        proc = subprocess.Popen(argv, cwd=str(cwd), stdin=subprocess.PIPE,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                text=True, start_new_session=True, env=build_env(timeout_s, home))
        _write_stdin(proc, prompt)
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
        _persist(cwd, raw, err)
        # 成功也是 NaN：订阅账号报不出美元（端口：绝不填 0），
        # token 用量在 turn.completed 的 usage 里
        return RunResult(exit_code=proc.returncode, events=events,
                         changed_files=diff(before, snapshot(cwd)), cost_usd=math.nan,
                         duration_s=wall_s, timed_out=timed_out,
                         stdout_tail="".join(junk + err)[-_TAIL_CHARS:],
                         report=final_report(events))


def _persist(cwd: Path, raw: list[str], err: list[str]) -> None:
    # 与 Claude Code 同一处、同一种命名：框架按这个模式把日志搬到产出目录（P-9：日志不进 prompt）
    log_dir = cwd / ".ai4sci"
    log_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    (log_dir / f"executor-{stamp}.jsonl").write_text("".join(raw), encoding="utf-8")
    if err:
        (log_dir / f"executor-{stamp}.stderr.log").write_text("".join(err), encoding="utf-8")


class Translator:
    """`--json` 的一行 → 零个或几个 ChatEvent。有状态：done 要带最后一段话，`error` 顶层事件与
    `turn.failed` 成对出现只报一次，命令的开始与结束要配成 tool_use / tool_result。"""

    def __init__(self, started: float) -> None:
        self.started = started
        self.last_text = ""
        self.fatal: str | None = None
        self.finished = False  # 见过 turn.completed 或 turn.failed
        self.thread_id: str | None = None

    def feed(self, line: str) -> list[ChatEvent]:
        if not line.strip():
            return []
        try:
            raw = json.loads(line)
        except json.JSONDecodeError:
            return []
        kind = raw.get("type")
        sid = self.thread_id
        if kind == "thread.started":
            self.thread_id = sid = str(raw.get("thread_id") or "") or None
            return [ChatEvent("init", session_id=sid, raw=raw)]
        if kind == "turn.completed":
            self.finished = True
            return [ChatEvent("done", text=self.last_text, session_id=sid, cost_usd=math.nan,
                              duration_s=time.monotonic() - self.started, exit_code=0, raw=raw)]
        if kind == "turn.failed":
            self.finished = True
            message = str((raw.get("error") or {}).get("message") or self.fatal or "turn failed")
            return [ChatEvent("error", text=message, is_error=True, session_id=sid, exit_code=1,
                              duration_s=time.monotonic() - self.started, raw=raw)]
        if kind == "error":
            self.fatal = str(raw.get("message") or "")  # 随后多半跟着 turn.failed，那时一起报
            return []
        if kind not in ("item.started", "item.completed"):
            return []  # item.updated 只有 todo_list 用，页面不画计划
        item = raw.get("item") or {}
        itype = item.get("type")
        done = kind == "item.completed"
        if itype == "agent_message" and done:
            self.last_text = str(item.get("text") or "")
            return [ChatEvent("text", text=self.last_text, session_id=sid, raw=raw)]
        if itype == "command_execution":
            if not done:
                return [ChatEvent("tool_use", tool="shell", session_id=sid, raw=raw,
                                  tool_input={"command": str(item.get("command") or "")})]
            code = item.get("exit_code")
            bad = item.get("status") in ("failed", "declined") or (code not in (None, 0))
            output = str(item.get("aggregated_output") or "")[:_RESULT_CHARS]
            return [ChatEvent("tool_result", text=output, is_error=bool(bad), session_id=sid,
                              raw=raw)]
        if itype == "file_change" and done:
            changes = [f"{c.get('kind')} {c.get('path')}" for c in item.get("changes") or []]
            return [ChatEvent("tool_use", tool="apply_patch", session_id=sid, raw=raw,
                              tool_input={"changes": changes}),
                    ChatEvent("tool_result", text="\n".join(changes), session_id=sid,
                              is_error=item.get("status") == "failed", raw=raw)]
        if itype == "web_search" and done:
            action = item.get("action") or {}
            return [ChatEvent("tool_use", tool="web_search", session_id=sid, raw=raw,
                              tool_input={"query": str(item.get("query") or ""),
                                          "action": str(action.get("type") or "")})]
        if itype == "mcp_tool_call":
            tool = f"{item.get('server', '')}.{item.get('tool', '')}"
            if not done:
                return [ChatEvent("tool_use", tool=tool, session_id=sid, raw=raw,
                                  tool_input=dict(item.get("arguments") or {}))]
            error = (item.get("error") or {}).get("message")
            result = item.get("result") or {}
            text = error or json.dumps(result.get("content", ""), ensure_ascii=False)
            return [ChatEvent("tool_result", text=str(text)[:_RESULT_CHARS], is_error=bool(error),
                              session_id=sid, raw=raw)]
        if itype == "error" and done:
            # 非致命的 item 错误（模型元数据缺失之类）：留一行给人看，不算这一轮失败
            return [ChatEvent("tool_result", text=str(item.get("message") or ""), is_error=True,
                              session_id=sid, raw=raw)]
        return []


class CodexChat:
    """协调层：开新线程用 `codex exec`（不 ephemeral），续接用 `codex exec resume <thread_id>`。

    实测：第一轮 thread.started 给 thread_id，第二轮 resume 带上它模型记得第一轮说的词；
    resume 认 `-c`
    的沙箱与可写根覆盖（read-only 开的线程 resume 成 workspace-write 后能写）；
    `developer_instructions`
    只在开线程那次生效。`cost_reporting = "turn"`，值永远 NaN（订阅账号）。
    """

    name = NAME
    cost_reporting = "turn"
    guide_channel = "thread"  # developer_instructions 只在开线程时生效，指南变了框架塞进话里

    def __init__(self, cli: str = "codex") -> None:
        self.cli = cli

    @staticmethod
    def knobs() -> Knobs:
        return KNOBS

    @staticmethod
    def tool_guide(bash_rules: tuple[str, ...]) -> str:
        return chat_tool_guide(bash_rules)

    def build_argv(self, cwd: Path, *, session_id: str | None, system_prompt: str,
                   allowed_paths: list[Path], runtime_paths: list[Path] = (),
                   tuning: Tuning | None = None, home: Path | None = None) -> list[str]:
        home = codex_home() if home is None else home
        writable = [*allowed_paths, *runtime_paths]
        skills_off = skill_off_paths(home, Path(cwd))
        if session_id:
            # resume 没有 -C / -s / --add-dir / --color；线程的 cwd 记在 rollout 里，
            # 沙箱与可写根靠 -c
            return [self.cli, "exec", "resume", *BASE_ARGS,
                    *config_args(writable, tuning=tuning, skills_off=skills_off), session_id, "-"]
        return [self.cli, "exec", *BASE_ARGS, "--color", "never", "-C", str(Path(cwd).resolve()),
                *config_args(writable, tuning=tuning, skills_off=skills_off,
                             developer_instructions=system_prompt), "-"]

    def turn(
        self, message: str, cwd: Path, timeout_s: float, *, session_id: str | None,
        system_prompt: str, allowed_paths: list[Path], bash_rules: tuple[str, ...],
        readable_paths: list[Path] = (), runtime_paths: list[Path] = (),
        chat_id: str | None = None, tuning: Tuning | None = None,
    ) -> Iterator[ChatEvent]:
        # bash_rules：没有按命令的白名单可翻，指南前言已经写了只许 ai4sci；readable_paths：
        # 沙箱读是全盘
        # 放开的，不用管
        home = codex_home()
        argv = self.build_argv(cwd, session_id=session_id, system_prompt=system_prompt,
                               allowed_paths=allowed_paths, runtime_paths=runtime_paths,
                               tuning=tuning, home=home)
        err: list[str] = []
        started = time.monotonic()
        proc = subprocess.Popen(argv, cwd=str(cwd), stdin=subprocess.PIPE,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                text=True, start_new_session=True,
                                env=build_env(timeout_s, home, chat_id))
        _write_stdin(proc, message)
        drain = threading.Thread(target=lambda: err.extend(proc.stderr), daemon=True)
        drain.start()
        timed_out = threading.Event()

        def _kill() -> None:
            timed_out.set()
            kill_tree(proc.pid)

        timer = threading.Timer(timeout_s, _kill)
        timer.start()
        translator = Translator(started)
        try:
            for line in proc.stdout:
                yield from translator.feed(line)
        finally:
            timer.cancel()
            proc.wait()
            drain.join(timeout=5)
        tail = "".join(err)[-_TAIL_CHARS:]
        if timed_out.is_set():
            yield ChatEvent("error", text=f"这一轮超过 {timeout_s:g} 秒，进程树已杀",
                            is_error=True, exit_code=proc.returncode,
                            duration_s=time.monotonic() - started, raw={"stderr_tail": tail})
        elif not translator.finished:
            why = translator.fatal or tail.strip() or "无 stderr"
            yield ChatEvent("error", is_error=True, exit_code=proc.returncode,
                            duration_s=time.monotonic() - started,
                            text=f"CLI 退出码 {proc.returncode}，没有 turn.completed：{why}",
                            raw={"stderr_tail": tail})
        elif session_id and translator.thread_id and translator.thread_id != session_id:
            # resume 找不到线程时 Codex 会静默开一条新的（源码 resolve_resume_thread_id）：
            # 对不上就报，
            # 不让「记忆丢了」悄悄过去
            yield ChatEvent("error", is_error=True, exit_code=proc.returncode,
                            text=(f"续接的线程 {session_id} 不在了，"
                                  f"Codex 静默开了 {translator.thread_id}"),
                            duration_s=time.monotonic() - started, raw={"stderr_tail": tail})


def probe(cli: str = "codex", speak_timeout_s: float = 120.0) -> AgentProbe:
    """四句人话（纲领 P-25）：装了没、版本够不够、登录了没、能不能说话。

    登录看 `codex login status` 的退出码（0 / 1，文字在 stderr），在私有 CODEX_HOME 下跑——软链指着
    真的 auth.json，所以答案与本机一致；说话真跑一句 pong，走与真会话同一组隔离参数。
    """
    result = AgentProbe()
    exe = shutil.which(cli)
    if exe is None:
        result.items.append(("装了没", False, f"找不到 `{cli}`：装 Codex CLI 后再检查"))
        return result
    result.installed = True
    result.items.append(("装了没", True, exe))
    version = subprocess.run([cli, "--version"], capture_output=True, text=True, timeout=30)
    raw = (version.stdout or version.stderr).strip()
    result.version = raw
    parsed = parse_version(raw)
    want = ".".join(map(str, MIN_VERSION))
    if version.returncode != 0 or parsed is None:
        result.items.append(("版本", False, f"`{cli} --version` 认不出：{raw or '无输出'}"))
        return result
    if parsed < MIN_VERSION:
        result.items.append(("版本", False, f"{raw}，要 ≥ {want}（这版实测过的 flag）"))
        return result
    result.items.append(("版本", True, raw))
    home = codex_home()
    env = build_env(30.0, home)
    status = subprocess.run([cli, "login", "status"], capture_output=True, text=True, timeout=30,
                            env=env)
    result.logged_in = status.returncode == 0
    if not result.logged_in:
        said = (status.stderr or status.stdout).strip() or "Not logged in"
        result.items.append(("登录", False, f"{said}：在终端跑 `codex login`，登录后再检查"))
        return result
    result.items.append(("登录", True, (status.stderr or status.stdout).strip() or "已登录"))
    started = time.monotonic()
    argv = [cli, "exec", *BASE_ARGS, "--ephemeral", "--color", "never", "-C", str(home),
            *config_args([], tuning=None, skills_off=skill_off_paths(home, home)), "-"]
    try:
        # cwd 也放在私有 home 里：说一句话不该在谁的目录里留下东西
        spoke = subprocess.run(argv, capture_output=True, text=True, timeout=speak_timeout_s,
                               input="Reply with exactly the word pong and nothing else.",
                               env=build_env(speak_timeout_s, home), cwd=str(home))
    except subprocess.TimeoutExpired:
        result.items.append(("说话", False, f"{speak_timeout_s:g} 秒没回话"))
        return result
    events, _ = parse_events(spoke.stdout.splitlines(keepends=True))
    reply = final_report(events)
    if spoke.returncode != 0 or "pong" not in reply.lower():
        failed = next((e for e in events if e.get("type") in ("turn.failed", "error")), {})
        why = (str((failed.get("error") or {}).get("message") or failed.get("message") or "")
               or spoke.stderr.strip() or reply or "无输出")
        result.items.append(("说话", False, f"退出码 {spoke.returncode}：{why[-300:]}"))
        return result
    result.spoke_s = time.monotonic() - started
    usage = next((e.get("usage") or {} for e in events if e.get("type") == "turn.completed"), {})
    tokens = int(usage.get("input_tokens") or 0) + int(usage.get("output_tokens") or 0)
    result.items.append(("说话", True,
                         f"pong，{result.spoke_s:.1f} 秒，{tokens} tokens（订阅，不计美元）"))
    return result


def make_runner() -> CodexRunner:
    return CodexRunner()


def make_chat() -> CodexChat:
    return CodexChat()
