"""给执行层的那段提示：模板 + 常数大小的账本摘要（纲领 workflow.md §2，P-9）。

为什么账本只给尾部若干行、且一行压成一条：内环会跑几十轮，把全部历史或 stdout 塞回
上下文会让每轮的输入线性增长，成本与跑飞的概率一起涨。摘要是常数大小的。

模板用 `string.Template`：占位符缺一个就抛 KeyError，不会静默留下一个 `$xxx` 在提示里。

模板路径由调用方传进来，本模块不持有它：模板是**能力**的资产（实验内环的模板在
`capabilities/experiment/prompt.md`），组装是执行层这一层的活。写死一个路径就等于把
executor 焊在实验内环上，别的能力再想用同一套组装就得复制一份。
"""

from __future__ import annotations

from pathlib import Path
from string import Template

from framework.memory.ledger import LedgerRow

LEDGER_TAIL_ROWS = 5
DIRECTION_ZH = {"minimize": "越小", "maximize": "越大"}


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
        return "这是第一轮，起点是任务包的基线。"
    row = rows[-1]
    text = f"第 {row.iter} 轮判为 **{row.status}**：{row.note or '无备注'}。"
    return f"{text}\n\n修复提示：{hint}" if hint else text


def build_prompt(template_path: Path, values: dict[str, object], domain_extra: str = "") -> str:
    """套模板；领域包的追加段存在才追加，缺了不追加也不回退到别的模板。"""
    text = Template(Path(template_path).read_text(encoding="utf-8")).substitute(values)
    if domain_extra.strip():
        text += "\n\n## 领域约定\n\n" + domain_extra.strip() + "\n"
    return text
