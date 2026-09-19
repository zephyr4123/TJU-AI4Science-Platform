"""给执行层的账本摘要：常数大小，不随轮数膨胀（纲领 workflow.md §2，P-9）。

为什么账本只给尾部若干行、且一行压成一条：内环会跑几十轮，把全部历史或 stdout 塞回
上下文会让每轮的输入线性增长，成本与跑飞的概率一起涨。摘要是常数大小的。
套模板的动作在 `executor.prompting.build_prompt`：那是通用的，这里是实验族自己的措辞。
"""

from __future__ import annotations

from framework.experiment.ledger import LedgerRow

LEDGER_TAIL_ROWS = 5


def summarize_ledger(rows: list[LedgerRow], limit: int = LEDGER_TAIL_ROWS) -> str:
    """最近 limit 行，一行一条；空账本给一句明话，不留空白让模型自己脑补。"""
    if not rows:
        return "（还没有跑过任何一轮）"
    lines = []
    for row in rows[-limit:]:
        metric = "-" if row.metric is None else f"{row.metric:.6g}"
        note = f"｜{row.note}" if row.note and row.note != "-" else ""
        lines.append(f"- 第 {row.iter} 轮：{row.status}，{metric}{note}")
    return "\n".join(lines)


def last_round_note(rows: list[LedgerRow], hint: str) -> str:
    """上一轮的结论 + 失败分类的修复提示；没有提示就不编（缺了不追加）。"""
    if not rows:
        return "这是第一轮，起点是设计阶段的基线。"
    row = rows[-1]
    text = f"第 {row.iter} 轮判为 **{row.status}**：{row.note or '无备注'}。"
    return f"{text}\n\n修复提示：{hint}" if hint else text
