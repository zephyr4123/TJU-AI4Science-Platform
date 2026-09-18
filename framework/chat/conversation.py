"""一段对话在磁盘上的样子，以及"发一轮"这个动作。

    <域>/chats/<chat_id>/ meta.json          后端名、后端 session id、cwd、轮数、累计花费、
                                              上次选的模型与思考深度（None 是后端缺省）
                          transcript.md       人一句 agent 一句，给人翻
                          inflight.json       正在跑的那一轮；在就拒绝再发
                          turn-N/message.md   这一轮人说的
                          turn-N/events.jsonl 这一轮 CLI 的原生事件流，一行一个

域是工作区（研究助理）或编辑台（造流助理），由 chat/scope.py 定；这里只拿到对话目录。

会话内容存在 CLI 自己的目录里（`--resume` 靠它），我们只记 session id；但事件流自己留一份：
它是"agent 那一轮到底按了什么"的唯一证据（P-3）。
"""

from __future__ import annotations

import json
import logging
import math
import os
import re
import secrets
from collections.abc import Iterator
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from backends import Chat, ChatEvent, Tuning

LOGGER = logging.getLogger("ai4sci.chat")
META_NAME = "meta.json"
TRANSCRIPT_NAME = "transcript.md"
INFLIGHT_NAME = "inflight.json"
TIMEOUT_ENV = "AI4SCI_COORDINATOR_TIMEOUT_S"
DEFAULT_TIMEOUT_S = 900.0
# transcript.md 里一轮的样子；写在 `_close_turn`，读在 `read_turns`，两处必须同步改
TURN_HEADING = "## 第 {n} 轮"
TURN_RE = re.compile(r"^## 第 (\d+) 轮\n\n\*\*(人|框架)\*\*：(.*?)\n\n\*\*agent\*\*：(.*?)"
                     r"(?=\n## 第 \d+ 轮\n|\Z)", re.S | re.M)
# 一轮是谁开的口：人在说话，或者框架来叫醒（作业跑完，外层 #63）。页面与 transcript 都要标清
ORIGINS = ("人", "框架")


class ConversationNotFound(FileNotFoundError):
    pass


class ConversationBusy(RuntimeError):
    """这段对话正有一轮在跑。CLI 与 HTTP 都要把它变成"稍等"，不排队、不并发。"""


def coordinator_timeout_s() -> float:
    """协调 agent 一轮的墙钟上限：它会调用命令等基线跑完，所以缺省和执行层一样给 15 分钟。"""
    raw = os.environ.get(TIMEOUT_ENV)
    value = DEFAULT_TIMEOUT_S if raw is None else float(raw)
    assert value > 0, f"{TIMEOUT_ENV} 必须是正数，得到 {value!r}"
    return value


@dataclass
class Conversation:
    chat_id: str
    backend: str
    cwd: str
    created_at: str
    session_id: str | None = None
    turns: int = 0
    cost_usd: float = 0.0
    # 这段对话上次选的模型与思考深度（外层 #86）：每轮可改、改了记住；None 是后端缺省
    model: str | None = None
    effort: str | None = None

    @property
    def dir(self) -> Path:
        return Path(self._dir)

    @property
    def tuning(self) -> Tuning:
        return Tuning(model=self.model, effort=self.effort)

    def tune(self, tuning: Tuning) -> None:
        """换模型 / 思考深度：变了才落盘。合不合清单由调用方拿 `Chat.knobs()` 先查。"""
        if tuning != self.tuning:
            self.model, self.effort = tuning.model, tuning.effort
            self.save()

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def save(self) -> None:
        (self.dir / META_NAME).write_text(
            json.dumps(self.to_dict(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def new_conversation(chats_dir: Path, backend: str, cwd: Path,
                     chat_id: str | None = None, tuning: Tuning | None = None) -> Conversation:
    """建 `<chats_dir>/<id>/`。id 缺省 `chat-<UTC 时间戳>-<4 位随机>`：同一秒开两段也不撞。"""
    stamp = datetime.now(UTC)
    chat_id = chat_id or f"chat-{stamp:%Y%m%dT%H%M%SZ}-{secrets.token_hex(2)}"
    directory = Path(chats_dir) / chat_id
    if directory.exists():
        raise FileExistsError(f"对话已存在，不覆盖：{directory}")
    directory.mkdir(parents=True)
    picked = tuning or Tuning()
    conv = Conversation(chat_id=chat_id, backend=backend, cwd=str(Path(cwd).resolve()),
                        created_at=stamp.isoformat(timespec="seconds"),
                        model=picked.model, effort=picked.effort)
    conv._dir = directory
    (directory / TRANSCRIPT_NAME).write_text(f"# 对话 {chat_id}\n", encoding="utf-8")
    conv.save()
    LOGGER.info("chat_new chat_id=%s backend=%s cwd=%s model=%s effort=%s", chat_id, backend,
                conv.cwd, conv.model or "-", conv.effort or "-")
    return conv


def load_conversation(chats_dir: Path, chat_id: str) -> Conversation:
    directory = Path(chats_dir) / chat_id
    meta = directory / META_NAME
    if not meta.is_file():
        raise ConversationNotFound(f"对话不存在或没有 {META_NAME}：{directory}")
    conv = Conversation(**json.loads(meta.read_text(encoding="utf-8")))
    conv._dir = directory
    return conv


def list_conversations(chats_dir: Path) -> list[Conversation]:
    root = Path(chats_dir)
    if not root.is_dir():
        return []
    return [load_conversation(chats_dir, p.name) for p in sorted(root.iterdir())
            if (p / META_NAME).is_file()]


def title(conv: Conversation) -> str | None:
    """给列表用的一句话：第一轮人说的第一行；还没说过话就是 None，页面自己起名。"""
    message = conv.dir / "turn-1" / "message.md"
    if not message.is_file():
        return None
    first = message.read_text(encoding="utf-8").strip().splitlines()
    return first[0].strip()[:60] if first else None


def read_turns(conv: Conversation) -> list[dict[str, Any]]:
    """把 transcript.md 读回成一轮一条 {turn, message, reply}：页面要的是结构，不是 markdown。"""
    text = (conv.dir / TRANSCRIPT_NAME).read_text(encoding="utf-8")
    return [{"turn": int(n), "origin": origin, "message": message.strip(), "reply": reply.strip()}
            for n, origin, message, reply in TURN_RE.findall(text)]


def send(
    conv: Conversation, chat: Chat, message: str, *, system_prompt: str,
    allowed_paths: list[Path], bash_rules: tuple[str, ...], readable_paths: list[Path] = (),
    timeout_s: float | None = None, origin: str = "人", tuning: Tuning | None = None,
) -> Iterator[ChatEvent]:
    """发一轮：写 message.md → 逐个事件落盘并往外吐 → done/error 时更新 meta 与 transcript。

    生成器：调用方边迭代边拿事件（CLI 逐行打、HTTP 逐条 SSE）。中途调用方不迭代到底，
    finally 也会摘掉 inflight 标记，但 meta 不会记这一轮——那是"没走完"的真实状态。
    `origin` 是谁开的口：缺省是人；框架叫醒 agent 时是「框架」，transcript 与 history 照实标。
    `tuning` 给了就是这一轮起改用这个模型 / 思考深度（记进 meta，之后每轮沿用）；不给沿用上次的。
    """
    message = message.strip()
    if not message:
        raise ValueError("消息是空的")
    if origin not in ORIGINS:
        raise ValueError(f"origin 只认 {ORIGINS}，得到 {origin!r}")
    inflight = conv.dir / INFLIGHT_NAME
    if inflight.exists():
        raise ConversationBusy(f"这段对话正有一轮在跑（{inflight}），等它结束再发")
    if tuning is not None:
        conv.tune(tuning)
    # 轮次编号取盘上下一个空号，不取 meta.turns + 1：半途放弃的一轮目录留着当证据，
    # 不计入 turns，下一轮也不能撞上它
    turn_n = _next_turn(conv.dir)
    turn_dir = conv.dir / f"turn-{turn_n}"
    turn_dir.mkdir()
    (turn_dir / "message.md").write_text(message + "\n", encoding="utf-8")
    inflight.write_text(json.dumps({"turn": turn_n,
                                    "started_at": datetime.now(UTC).isoformat(timespec="seconds")}),
                        encoding="utf-8")
    events_path = turn_dir / "events.jsonl"
    timeout = coordinator_timeout_s() if timeout_s is None else timeout_s
    LOGGER.info("chat_turn_start chat_id=%s turn=%d resume=%s model=%s effort=%s", conv.chat_id,
                turn_n, conv.session_id or "-", conv.model or "-", conv.effort or "-")
    try:
        with events_path.open("a", encoding="utf-8") as fh:
            for event in chat.turn(message, Path(conv.cwd), timeout, session_id=conv.session_id,
                                   system_prompt=system_prompt, allowed_paths=allowed_paths,
                                   bash_rules=bash_rules, readable_paths=readable_paths,
                                   chat_id=conv.chat_id, tuning=conv.tuning):
                if event.kind != "delta":  # 逐字片段只往外吐不落盘：证据是完整的 text，不是碎片
                    fh.write(json.dumps(event.raw or _bare(event), ensure_ascii=False) + "\n")
                    fh.flush()
                if event.session_id and event.session_id != conv.session_id:
                    conv.session_id = event.session_id
                    conv.save()
                if event.kind in ("done", "error"):
                    _close_turn(conv, turn_n, message, event, origin)
                yield event
    finally:
        inflight.unlink(missing_ok=True)


def _next_turn(directory: Path) -> int:
    taken = [int(p.name.split("-", 1)[1]) for p in directory.glob("turn-*")
             if p.is_dir() and p.name.split("-", 1)[1].isdigit()]
    return max(taken, default=0) + 1


def _bare(event: ChatEvent) -> dict[str, Any]:
    """适配器自己造的事件（超时、协议坏了）没有原生 raw，落盘就记它的字段。"""
    return {"type": f"ai4sci_{event.kind}", "text": event.text, "exit_code": event.exit_code}


def _close_turn(conv: Conversation, turn_n: int, message: str, event: ChatEvent,
                origin: str) -> None:
    conv.turns += 1
    if not math.isnan(event.cost_usd):
        conv.cost_usd += event.cost_usd
    conv.save()
    reply = event.text if event.kind == "done" else f"（这一轮没走完：{event.text}）"
    with (conv.dir / TRANSCRIPT_NAME).open("a", encoding="utf-8") as fh:
        fh.write(f"\n{TURN_HEADING.format(n=turn_n)}\n\n**{origin}**：{message}\n\n"
                 f"**agent**：{reply}\n")
    LOGGER.info("chat_turn_end chat_id=%s turn=%d kind=%s cost_usd=%s session=%s",
                conv.chat_id, turn_n, event.kind, event.cost_usd, conv.session_id or "-")
