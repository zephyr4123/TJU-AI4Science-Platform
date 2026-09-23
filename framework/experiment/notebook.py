"""实验笔记：一个 run 一本，runner 每轮追加一条，下一轮整本喂给执行层。

为什么要有它：每轮执行层都是新会话，只看账本尾部的"变差 / 持平"会把同一个改动做两遍
（真跑第 2 轮与第 5 轮分数一模一样，外层 #28）。新会话是为了上下文不膨胀，不是为了失忆；
记忆放磁盘、每轮读回来才是 P-3 的本意。

为什么由 runner 写而不是执行层写：笔记必须活在棘轮之外——执行层只能改 code/，而 code/
在 discard 时会被 reset 掉；runner 写在 experiment/ 下，回滚不抹。

在四层的 memory 层，且不 import framework 的任何东西：笔记是纯文本的追加与读回，
文件名归 `run.layout` 管（NOTEBOOK_NAME 在那里定义，避免两处各写一遍）。

为什么它不违反 P-9：P-9 挡的是 stdout 与整段日志，不是记忆。每条笔记有硬上限，整本的
上限由 max_iterations 决定，是有界的。
"""

from __future__ import annotations

from pathlib import Path

REPORT_CHARS = 600   # 执行层自述最多留这么多字符：够写假设与改动，不够贴日志
DIFFSTAT_LINES = 6   # git diff --stat 最多留几行


def append(
    path: Path, *, iter_n: int, status: str, metric: str, note: str, report: str, diffstat: str
) -> None:
    """追加一条；空自述也要记，"执行层没说"本身就是信息。"""
    body = report.strip() or "（执行层没有自述）"
    if len(body) > REPORT_CHARS:
        body = body[:REPORT_CHARS].rstrip() + "…"
    stat = "\n".join(diffstat.strip().splitlines()[:DIFFSTAT_LINES]) or "（没有产生 commit）"
    entry = (
        f"### 第 {iter_n} 轮 · {status} · {metric}\n\n"
        f"{body}\n\n"
        f"改动：\n```\n{stat}\n```\n"
        f"裁决：{note}\n\n"
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(entry)


def read(path: Path) -> str:
    """整本读回；没有就明说，不留空白让模型脑补。"""
    if not path.is_file():
        return "（这次实验还没有笔记：这是第一轮，起点是设计那包的基线）"
    return path.read_text(encoding="utf-8").strip()
