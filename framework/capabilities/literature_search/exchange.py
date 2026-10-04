"""框架与执行层之间的两份文件：执行层写的 `seeds.md`（检索词、纳入标准、种子）与每一跳的筛选结论。

两份都由执行层写、框架读，形状在这里定、在这里核：不合形状返回问题清单，由 `loop.py` 判失败。
写法选 markdown 的小节与 `|` 分隔的行，不选 JSON：两家 CLI 写这种文本都稳，人打开也看得懂。
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from framework.capabilities.literature_search.papers import WORK_KEY_RE
from framework.capabilities.literature_search.pool import VERDICTS

SEEDS_NAME = "seeds.md"
SECTIONS = ("检索词", "纳入标准", "种子")
BULLET_RE = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s+")


@dataclass(frozen=True)
class Seeds:
    queries: tuple[str, ...]
    criteria: str
    seeds: tuple[str, ...]        # 种子一节的原文，一行一条（编号由 papers.dois_in 认）


def parse_seeds(text: str) -> tuple[Seeds | None, list[str]]:
    """三节按标题切；检索词与纳入标准不许空，种子可以空（没有联网搜索的 agent 交不出种子）。"""
    sections = _sections(text)
    problems = [f"缺「## {name}」一节" for name in SECTIONS if name not in sections]
    if problems:
        return None, problems
    queries = tuple(q.strip("`'\" ") for q in _items(sections["检索词"]))
    queries = tuple(q for q in queries if q)
    criteria = sections["纳入标准"].strip()
    if not queries:
        problems.append("「检索词」一节一条都没有")
    if not criteria:
        problems.append("「纳入标准」一节是空的")
    return (Seeds(queries, criteria, tuple(_items(sections["种子"]))) if not problems
            else None), problems


def parse_decisions(text: str, expected: list[str]) -> tuple[dict[str, tuple[str, str]], list[str]]:
    """每行 `W号 | 收 或 不收 | 理由`，返回拿到合格结论的与问题清单。不在 expected 里的号
    （抄错的）、结论不认的、没写理由的、同一篇两条相反结论的进问题清单，这几篇不算有结论；
    同一篇重复写了一样的结论不算错。漏写的列在最后。"""
    decided: dict[str, tuple[str, str]] = {}
    conflicted: set[str] = set()
    problems: list[str] = []
    for number, raw in enumerate(text.splitlines(), start=1):
        line = BULLET_RE.sub("", raw).strip().strip("|").strip()
        if not line or line.startswith("#") or line.startswith("```"):
            continue
        parts = [p.strip() for p in line.split("|", 2)]
        match = WORK_KEY_RE.search(parts[0])
        if len(parts) != 3 or match is None:
            problems.append(f"第 {number} 行不是「W号 | 收 或 不收 | 理由」：{raw.strip()[:80]}")
            continue
        key, verdict, reason = match.group(0), parts[1], parts[2]
        if key not in expected:
            problems.append(f"第 {number} 行的 {key} 不在这一跳的候选里")
        elif verdict not in VERDICTS:
            problems.append(f"{key} 的结论是「{verdict}」，只认「收」或「不收」")
        elif not reason:
            problems.append(f"{key} 没写理由")
        elif key in conflicted:
            continue
        elif key in decided:
            if decided[key][0] != verdict:
                del decided[key]
                conflicted.add(key)
                problems.append(f"{key} 写了两条相反的结论")
        else:
            decided[key] = (verdict, reason)
    missing = [k for k in expected if k not in decided]
    if missing:
        problems.append(f"{len(missing)} 篇没有结论：{', '.join(missing[:10])}"
                        + (" 等" if len(missing) > 10 else ""))
    return decided, problems


def _sections(text: str) -> dict[str, str]:
    found: dict[str, list[str]] = {}
    current: str | None = None
    for line in text.splitlines():
        if line.startswith("## "):
            current = line[3:].strip()
            found.setdefault(current, [])
        elif current is not None:
            found[current].append(line)
    return {name: "\n".join(lines) for name, lines in found.items()}


def _items(body: str) -> list[str]:
    """一节里的条目：列表项去掉记号；不是列表项的非空行也算一条（agent 偶尔不写记号）。"""
    return [BULLET_RE.sub("", line).strip() for line in body.splitlines()
            if line.strip() and not line.strip().startswith("```")]
