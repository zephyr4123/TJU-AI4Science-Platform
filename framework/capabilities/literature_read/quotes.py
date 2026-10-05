"""原句核对：笔记里 `> 原文：` 抄的那句，在原文里找不找得到（外层 #233）。

零模型：两边都把大小写、空白、markdown 的排版记号（加粗、斜体、行内代码）、弯引号与各种破折号归一，
PDF 解析带进正文的脚注标记（`<sup>9</sup>`）与标点前多出的空格去掉，再按子串比；抄半句带省略号的，
先去掉省略号。找不到不改笔记、不判失败，只把对上几条记进清单——
研究助理与研究者据此知道哪几句要回原文核。
"""

from __future__ import annotations

import re

QUOTE_RE = re.compile(r"^\s*>\s*原文[：:]\s*(.+?)\s*$", re.MULTILINE)
_SAME = str.maketrans({"“": '"', "”": '"', "‘": "'", "’": "'", "—": "-", "–": "-",
                       "*": None, "_": None, "`": None})
_ENDS = " \"'.…"
_FOOTNOTE_RE = re.compile(r"<sup>.*?</sup>|<[^>]+>")
_SPACE_BEFORE_PUNCT_RE = re.compile(r"\s+([,.;:!?)])")


def quoted(note: str) -> list[str]:
    """笔记里抄的原句，按出现的顺序。"""
    return QUOTE_RE.findall(note)


def found(quote: str, text: str) -> bool:
    said = _normal(quote).replace("...", "").strip(_ENDS)
    return bool(said) and said in _normal(text)


def _normal(text: str) -> str:
    text = _SPACE_BEFORE_PUNCT_RE.sub(r"\1", _FOOTNOTE_RE.sub("", text.translate(_SAME)))
    return " ".join(text.lower().split())
