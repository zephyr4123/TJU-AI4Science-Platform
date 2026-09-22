"""agent 端口：一个 coding agent CLI 一个适配器文件。

两个端口，同一批适配器文件：`Runner` 是执行层（一次会话、跑完退出、只看它改了什么），
`Chat` 是协调层（多轮、按 session id 续接、事件流边跑边出）。同一个 CLI 两种用法，
所以放同一个文件里；换一家 CLI 就是加一个文件、在 `_BACKENDS` 加一行（主人红线：涉及
agent 的一律可替换）。每家还要有一个模块级 `probe()`：装了没、版本够不够、登录了没、能不能说话
（纲领 P-25 四句人话），`ai4sci agent check` 与冷启动自检读它。

这里只放几样东西：结果结构、两个协议、自检结果、按名字取适配器的函数。
没有注册表、没有抽象基类——纲领 §5 要求「一个后端一个文件，60 到 80 行」，
注册表会让"有哪些后端"散进各个模块的 import 副作用里，加后端时改动看不见。
显式字典反过来：加一个后端就是加一行，diff 里一眼能看到（P-8）。
"""

from __future__ import annotations

import importlib
import math
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

__all__ = ["RunResult", "Runner", "ChatEvent", "Choice", "Tuning", "Knobs", "Chat", "AgentProbe",
           "BackendNotFound", "get_backend", "get_chat", "probe", "available_backends"]


@dataclass
class RunResult:
    """一次执行层调用的全部可取证产物。

    `changed_files` 由框架自己快照 diff 得出，不采信 CLI 自报（P-2：执行层不当自己的裁判）。
    `cost_usd` 在超时被杀时拿不到（result 事件根本没来），此时按约定填 NaN 表示"未知"，
    绝不填 0 —— 填 0 会让账本上的预算统计静默偏低，属于 P-7 说的静默降级。订阅账号报不出美元的
    CLI（Codex 用 ChatGPT 登录）成功也是 NaN，token 用量在 `events` 里。
    `report` 是执行层收尾的自述（Claude Code 是 result 事件的文本，Codex 是最后一条 agent_message）
    ；
    没有就空串，不编。
    """

    exit_code: int
    events: list[dict] = field(default_factory=list)
    changed_files: list[str] = field(default_factory=list)
    cost_usd: float = 0.0
    duration_s: float = 0.0
    timed_out: bool = False
    stdout_tail: str = ""
    report: str = ""


@dataclass(frozen=True)
class Tuning:
    """一轮用什么：模型与思考深度。字段 None 是「这家适配器给的起点」（`Knobs.model` / `.effort`），
    适配器不替人猜别的；对话 meta 与设置里记的一律是具体值（纲领 P-25）。"""

    model: str | None = None
    effort: str | None = None


@runtime_checkable
class Runner(Protocol):
    """执行层适配器的唯一形状。

    `allowed_paths` 是"只许改这些目录"的意图；各家 CLI 的权限模型语义对不齐，
    适配器只负责尽量收紧，真正的门是 runner 事后拿 `changed_files` 判（纲领 §5）。
    `bash_rules` 是放行的**命令前缀**（执行层只有 `ai4sci skill`，纲领 P-22），与 CLI 无关的写法，
    各家适配器翻成自己的（Claude Code 是 `Bash(ai4sci skill *)`；Codex 没有按命令的白名单，
    沙箱是门、
    前缀写进 `tool_guide` 让它照做）；不给就一条命令都不放。
    `runtime_paths` 是平台自己要写的目录（数据根、按人的配置、uv 缓存）：
    agent 敲的 `ai4sci` 会往里写，
    有沙箱的 CLI（Codex）要把它们设成可写根，没有沙箱的（Claude Code，Bash 子进程不受限）不用管；
    agent 自己不许编辑这些目录，所以它不是 `allowed_paths`。
    `tuning` 是这次会话用什么模型、什么深度（从按人的设置来，P-25）；None 用适配器给的起点。
    `max_turns` / `max_budget_usd` 是这一次会话的轮数与花费上限，不给用适配器的缺省（环境变量）：
    读别人整个仓库再写壳的会话（复现）要比从零写一版的多得多——真跑时 30 轮在读完仓库、写完
    文件、还没来得及自述时就被掐了（外层 #122）。没这两个闸的 CLI 只靠超时。
    联网：适配器必须放行这家 CLI **自带**的联网搜索与网页读取工具（Claude Code 是 WebSearch /
    WebFetch，Codex 是 web_search），不能让 agent 拿 Bash 里的 curl 去凑——实测 dontAsk 下不放行
    就被拒，拒绝信息还教它「用别的工具试试」（主人 2026-09-20）。
    `tool_guide` 是塞进执行层提示末尾的「工具怎么用」一段：读文件、改文件、跑命令各用什么，
    是这家 CLI
    自己的事（Claude Code 有 Read / Glob / Grep，Codex 只有 shell 与补丁），框架不替它写。
    """

    name: str

    def tool_guide(self, bash_rules: tuple[str, ...]) -> str: ...

    def run(
        self,
        prompt: str,
        cwd: Path,
        timeout_s: float,
        allowed_paths: list[Path],
        bash_rules: tuple[str, ...] = (),
        runtime_paths: list[Path] = (),
        tuning: Tuning | None = None,
        max_turns: int | None = None,
        max_budget_usd: float | None = None,
    ) -> RunResult: ...


# 事件种类：适配器把各家 CLI 的原生事件翻成这几种，上层（落盘、CLI 打印、网页 SSE）只认这几种。
# `delta` 是助理正在说的一小段字（外层 #65）：能逐字吐的适配器必须逐字吐，最后仍要有一条完整的
# `text`——上层拿 text 替换攒起来的 delta，落盘只留 text 不留 delta。CLI 本身不给逐字事件的
# （Codex `exec --json` 只在一段话说完时给 agent_message），一段一条 text，页面上一段一段出，
# 适配器文件头要写明这是 CLI 的限制
CHAT_EVENT_KINDS = ("init", "delta", "text", "tool_use", "tool_result", "denied", "done", "error")


@dataclass
class ChatEvent:
    """协调 agent 一轮里的一个事件。`raw` 是 CLI 的原生事件，留档用；上层不解析它。

    `done` 带这一轮的成本、耗时、后端 session id 与最终回复；`error` 是这一轮没走完
    （超时、进程死了、协议坏了），`text` 里是原因。成本拿不到填 NaN 不填 0（同 RunResult）。
    `delta` 的 `text` 是刚到的那几个字，不是累计；同一段话结束时会来一条完整的 `text`。
    """

    kind: str
    text: str = ""
    tool: str = ""
    tool_input: dict = field(default_factory=dict)
    is_error: bool = False
    session_id: str | None = None
    cost_usd: float = math.nan
    duration_s: float = 0.0
    exit_code: int | None = None
    raw: dict = field(default_factory=dict)

    def __post_init__(self) -> None:
        assert self.kind in CHAT_EVENT_KINDS, f"未知的事件种类 {self.kind!r}"


@dataclass(frozen=True)
class Choice:
    """旋钮上的一个刻度：`id` 给 CLI 看，`label` 给人看，`note` 是一句提示（可空）。"""

    id: str
    label: str
    note: str = ""


@dataclass(frozen=True)
class Knobs:
    """一家 CLI 能拧的两个旋钮（外层 #86）：有哪些模型、有哪几档思考深度，以及各自的起点。

    清单由适配器自报（页面照单渲染，不写死哪家有什么）。`model` / `effort` 是起点：按人的设置里没填
    这家时用它（纲领 P-25：旋钮上只有具体值，没有「默认」这一项），必须在清单上——适配器写死一个
    稳妥的，不是 CLI 自己的缺省（那个拿不准、还会随版本变）。哪家真换不了模型就报空清单，页面上那枚
    旋钮不出现，起点也就空串。
    """

    models: tuple[Choice, ...]
    efforts: tuple[Choice, ...]
    model: str
    effort: str

    def __post_init__(self) -> None:
        for name, picked, choices in (("model", self.model, self.models),
                                       ("effort", self.effort, self.efforts)):
            ids = {c.id for c in choices}
            assert (picked in ids) if ids else picked == "", \
                f"Knobs.{name} 的起点 {picked!r} 不在清单 {sorted(ids)} 里"

    def check(self, tuning: Tuning) -> None:
        """人选的值要在清单上；不在就报一句带清单的话（ValueError：配置值非法，不静默回落）。"""
        for name, picked, choices in (("模型", tuning.model, self.models),
                                       ("思考深度", tuning.effort, self.efforts)):
            if picked is not None and picked not in {c.id for c in choices}:
                raise ValueError(
                    f"{name} {picked!r} 不在清单上；可选：{', '.join(c.id for c in choices)}")

    def fill(self, tuning: Tuning | None) -> Tuning:
        """把没选的字段填成起点：适配器起会话前、框架开新对话时都用它，之后不再有 None。"""
        picked = tuning or Tuning()
        filled = Tuning(model=picked.model or self.model, effort=picked.effort or self.effort)
        self.check(filled)
        return filled


@runtime_checkable
class Chat(Protocol):
    """协调层适配器的唯一形状：一句话进、一串事件出，能按 session id 续。

    `session_id=None` 开新会话，否则续接；每一轮至少吐一个 `init`（带 session id）和
    一个 `done` 或 `error`。`system_prompt` 是协调层指南；`allowed_paths`、`bash_rules`、
    `runtime_paths` 的语义同 `Runner`：尽量收紧，各家 CLI 的权限模型对不齐，
    自带的联网工具同样必须放行；
    `readable_paths` 是工作目录之外「能读不能写」的目录（研究助理看流程库用，P-16）。
    `chat_id` 是这段对话的名字：
    适配器要让 agent 调用的命令拿得到它（环境变量 `AI4SCI_CHAT_ID`），后台作业跑完才知道叫醒谁。
    `tuning` 是这一轮用什么模型、什么思考深度（外层 #86）：框架从对话 meta 里给的是具体值；None 或
    字段为 None 用 `knobs()` 的起点。`knobs()` 报这家 CLI 有哪些刻度，页面与终端只许从里面选。
    `cost_reporting` 说清 `done.cost_usd` 是什么：`"turn"` 是这一轮的花费；`"session"` 是续接的
    整段会话到此刻的累计（Claude Code 的 `--resume` 就这样报），框架自己减上一轮的累计得到这一轮的。
    报错了就是页面上一句「你是什么模型」显示 $0.28（实测 2026-09-19：那一轮实际 $0.014）。
    """

    name: str
    cost_reporting: str

    def knobs(self) -> Knobs: ...

    def turn(
        self,
        message: str,
        cwd: Path,
        timeout_s: float,
        *,
        session_id: str | None,
        system_prompt: str,
        allowed_paths: list[Path],
        bash_rules: tuple[str, ...],
        readable_paths: list[Path] = (),
        runtime_paths: list[Path] = (),
        chat_id: str | None = None,
        tuning: Tuning | None = None,
    ) -> Iterator[ChatEvent]: ...


@dataclass
class AgentProbe:
    """自检一家 CLI 的结果（纲领 P-25 四句人话）：一项一行（名字、过没过、一句话给人看）。

    不过也不抛：`ai4sci agent check` 要把整张报告打给人看，不过关只报告不拒绝保留（同算力）。
    `version` 是 `--version` 读到的原文；`spoke_s` 是说一句话花的秒数（没说成是 NaN）；
    `cost_usd` 那一句话的花费（报不出美元的 CLI 是 NaN）。
    """

    items: list[tuple[str, bool, str]] = field(default_factory=list)
    installed: bool = False
    version: str = ""
    logged_in: bool = False
    spoke_s: float = math.nan
    cost_usd: float = math.nan

    @property
    def ok(self) -> bool:
        return bool(self.items) and all(ok for _, ok, _ in self.items)

    def to_dict(self) -> dict[str, Any]:
        """写进按人的设置文件（NaN 写 None：YAML 里不留 .nan）。"""
        return {"ok": self.ok, "installed": self.installed, "version": self.version,
                "logged_in": self.logged_in,
                "spoke_s": None if math.isnan(self.spoke_s) else round(self.spoke_s, 2),
                "cost_usd": None if math.isnan(self.cost_usd) else self.cost_usd,
                "items": [{"name": n, "ok": ok, "note": note} for n, ok, note in self.items]}


class BackendNotFound(ValueError):
    """要的后端不存在。继承 ValueError：调用方按"配置值非法"处理，不是运行时故障。"""


# 名字 → 模块。懒加载是为了让"没装某个 CLI 的 SDK"不影响别的后端 import。
_BACKENDS: dict[str, str] = {
    "claude_code": "backends.claude_code",
    "codex": "backends.codex",
}
# 给人看的名字（产品名，页面「设置 → AI」照它写；纲领 P-21 机器的名字不上屏）
TITLES: dict[str, str] = {"claude_code": "Claude Code", "codex": "Codex"}


def available_backends() -> list[str]:
    return sorted(_BACKENDS)


def _module(name: str, layer: str):
    try:
        module_path = _BACKENDS[name]
    except KeyError:
        raise BackendNotFound(
            f"未知的{layer}后端 {name!r}；可用的有：{', '.join(available_backends())}"
        ) from None
    return importlib.import_module(module_path)


def get_backend(name: str) -> Runner:
    """按名字取适配器。名字不对就报错退出，绝不静默回退到某个默认后端（P-7）。
    名字贴在适配器上（`runner.name`）：起会话的那层按它查按人的设置里这家用什么模型。"""
    module = _module(name, "执行层")
    runner = module.make_runner()
    # 断言而不是信任：适配器模块是人写的，形状对不上要在这里就炸，别等到跑一半
    assert hasattr(runner, "run"), f"后端 {name!r} 的 make_runner() 没有返回带 run() 的对象"
    assert hasattr(runner, "tool_guide"), f"后端 {name!r} 的执行层适配器没有 tool_guide()"
    runner.name = name
    return runner


def get_chat(name: str) -> Chat:
    """按名字取协调层适配器；同 `get_backend`，名字不对就报错，不回退。"""
    module = _module(name, "agent ")
    assert hasattr(module, "make_chat"), f"后端 {name!r} 还没有协调层适配器（make_chat）"
    chat = module.make_chat()
    assert hasattr(chat, "turn"), f"后端 {name!r} 的 make_chat() 没有返回带 turn() 的对象"
    assert hasattr(chat, "knobs"), \
        f"后端 {name!r} 的协调层适配器没有 knobs()：得报有哪些模型与思考深度"
    chat.name = name
    return chat


def probe(name: str) -> AgentProbe:
    """自检一家：模块级 `probe()`，装了没 / 版本 / 登录 / 说一句话。"""
    module = _module(name, "agent ")
    assert hasattr(module, "probe"), f"后端 {name!r} 没有 probe()：得会自检（纲领 P-25）"
    result = module.probe()
    assert isinstance(result, AgentProbe), f"后端 {name!r} 的 probe() 没有返回 AgentProbe"
    return result
