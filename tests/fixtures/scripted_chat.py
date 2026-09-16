"""剧本协调层适配器：形状与真 `Chat` 完全一致，每一轮吐预先写好的事件。

对话落盘、CLI 打印、HTTP SSE 都是确定性代码，不该由模型的发挥来证明（P-5）。
剧本记下每次 turn() 收到的 message / session_id / system_prompt，测试据此断言"续接带上了 id"。
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

from backends import ChatEvent

SESSION = "sess-0001"


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


def with_tool(text: str, tool: str, tool_input: dict, result: str) -> list[ChatEvent]:
    """按了一个按钮的一轮：init → tool_use → tool_result → 文本 → done。"""
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
    def __init__(self, turns: list[list[ChatEvent]]) -> None:
        self.turns = list(turns)
        self.calls: list[dict] = []

    def turn(self, message: str, cwd: Path, timeout_s: float, *, session_id: str | None,
             system_prompt: str, allowed_paths: list[Path],
             bash_rules: tuple[str, ...]) -> Iterator[ChatEvent]:
        assert self.turns, "剧本用完了还在调 turn()"
        self.calls.append({"message": message, "cwd": Path(cwd), "timeout_s": timeout_s,
                           "session_id": session_id, "system_prompt": system_prompt,
                           "allowed_paths": list(allowed_paths), "bash_rules": tuple(bash_rules)})
        yield from self.turns.pop(0)
