"""剧本协调层适配器：形状与真 `Chat` 完全一致，每一轮吐预先写好的事件。

对话落盘、CLI 打印、HTTP SSE 都是确定性代码，不该由模型的发挥来证明（P-5）。
剧本记下每次 turn() 收到的 message / session_id / system_prompt，测试据此断言"续接带上了 id"。
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

from backends import ChatEvent, Choice, Knobs, Tuning

SESSION = "sess-0001"
# 剧本后端的两个旋钮：两个模型、两档深度，起点 a / low（P-25：旋钮上只有具体值）
KNOBS = Knobs(models=(Choice("a", "甲", "快"), Choice("b", "乙")),
              efforts=(Choice("low", "低"), Choice("high", "高")), model="a", effort="low")


def reply(text: str, *, cost: float = 0.01, session: str = SESSION) -> list[ChatEvent]:
    """最常见的一轮：init → 一句文本 → done。"""
    return [ChatEvent("init", session_id=session, raw={"type": "system", "subtype": "init",
                                                        "session_id": session}),
            ChatEvent("text", text=text, session_id=session,
                      raw={"type": "assistant", "message": {"content": [
                          {"type": "text", "text": text}]}}),
            ChatEvent("done", text=text, session_id=session, cost_usd=cost, duration_s=1.5,
                      exit_code=0, raw={"type": "result", "result": text,
                                        "total_cost_usd": cost, "duration_ms": 1500})]


def streamed(text: str, *, pieces: int = 3) -> list[ChatEvent]:
    """逐字吐的一轮：init → 几条 delta → 完整 text → done（端口契约：delta 之后必有 text）。"""
    events = reply(text)
    step = max(1, -(-len(text) // pieces))
    deltas = [ChatEvent("delta", text=text[i:i + step], session_id=SESSION,
                        raw={"type": "stream_event", "event": {"type": "content_block_delta",
                             "delta": {"type": "text_delta", "text": text[i:i + step]}}})
              for i in range(0, len(text), step)]
    events[1:1] = deltas
    return events


def with_tool(text: str, tool: str, tool_input: dict, result: str) -> list[ChatEvent]:
    """调用了一条命令的一轮：init → tool_use → tool_result → 文本 → done。"""
    events = reply(text)
    events[1:1] = [ChatEvent("tool_use", tool=tool, tool_input=tool_input, session_id=SESSION,
                             raw={"type": "assistant", "message": {"content": [
                                 {"type": "tool_use", "name": tool, "input": tool_input}]}}),
                   ChatEvent("tool_result", text=result, session_id=SESSION,
                             raw={"type": "user", "message": {"content": [
                                 {"type": "tool_result", "content": result}]}})]
    return events


def failure(why: str) -> list[ChatEvent]:
    """没走完的一轮：init → error（超时、进程死了）。"""
    return [ChatEvent("init", session_id=SESSION, raw={"type": "system", "subtype": "init",
                                                        "session_id": SESSION}),
            ChatEvent("error", text=why, is_error=True, exit_code=137)]


class ScriptedChat:
    # 顶着真适配器的名字：按人的设置按名字查这家用什么（P-25），剧本不在 `_BACKENDS` 里
    name = "claude_code"
    cost_reporting = "turn"
    guide_channel = "turn"

    def __init__(self, turns: list[list[ChatEvent]], knobs: Knobs = KNOBS,
                 cost_reporting: str = "turn") -> None:
        self.turns = list(turns)
        self.calls: list[dict] = []
        self._knobs = knobs
        self.cost_reporting = cost_reporting

    def knobs(self) -> Knobs:
        return self._knobs

    @staticmethod
    def tool_guide(bash_rules: tuple[str, ...]) -> str:
        return ""  # 剧本没有工具：指南里不插「工具怎么用」

    def turn(self, message: str, cwd: Path, timeout_s: float, *, session_id: str | None,
             system_prompt: str, allowed_paths: list[Path],
             bash_rules: tuple[str, ...], readable_paths: list[Path] = (),
             chat_id: str | None = None,
             tuning: Tuning | None = None) -> Iterator[ChatEvent]:
        assert self.turns, "剧本用完了还在调 turn()"
        self.calls.append({"message": message, "cwd": Path(cwd), "timeout_s": timeout_s,
                           "session_id": session_id, "system_prompt": system_prompt,
                           "allowed_paths": list(allowed_paths), "bash_rules": tuple(bash_rules),
                           "readable_paths": list(readable_paths), "chat_id": chat_id,
                           "tuning": tuning})
        yield from self.turns.pop(0)
