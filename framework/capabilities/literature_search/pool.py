"""候选池：看过的每篇论文从哪来、第几跳、筛的结论；还没看的线索按「被几篇已收录的关联」排队。

只是数据，不发请求、不起会话：查接口与起会话是 `loop.py` 的事，这里只管记账与排序，所以能
脱开网与模型单测。

来源记成短标记，给人看时由 `report.py` 翻成话：
- `seed` 种子（执行层用自带搜索找来的）；`query:<检索词>` 关键词检索；
- `ref:<W>` 收录的 W 引用了它（向后）；`cites:<W>` 它引用了收录的 W（向前）。
"""

from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

from framework.capabilities.literature_search.papers import Paper
from framework.files import write_atomic

INCLUDE = "收"
EXCLUDE = "不收"
VERDICTS = (INCLUDE, EXCLUDE)


@dataclass
class Entry:
    paper: Paper
    hop: int                                  # 第几跳交给模型筛的
    found: list[str] = field(default_factory=list)
    verdict: str | None = None                # INCLUDE / EXCLUDE；None 是还没筛
    reason: str = ""

    def to_dict(self) -> dict:
        return {"paper": self.paper.to_dict(), "hop": self.hop, "found": self.found,
                "verdict": self.verdict, "reason": self.reason}


class Pool:
    def __init__(self, excluded: frozenset[str] = frozenset()) -> None:
        self.entries: dict[str, Entry] = {}
        # 线索：还没交给模型的 W 号 → 来源标记；元数据取过的放 cache（排序要被引数）
        self.leads: dict[str, set[str]] = defaultdict(set)
        self.cache: dict[str, Paper] = {}
        # 永远不进池的 W 号：召回实测时把当标准答案的那篇综述挡在外面，否则向后一跳就把答案全抄回来
        self.excluded = excluded

    def admit(self, paper: Paper, hop: int, found: str) -> bool:
        """一篇论文交给第 hop 跳筛；已经在池里的只补一条来源。返回是不是新进的。"""
        if paper.key in self.excluded:
            return False
        if paper.key in self.entries:
            if found not in self.entries[paper.key].found:
                self.entries[paper.key].found.append(found)
            return False
        self.entries[paper.key] = Entry(paper, hop, [found])
        return True

    def of_hop(self, hop: int) -> list[Entry]:
        return [e for e in self.entries.values() if e.hop == hop]

    def included(self) -> list[Entry]:
        return [e for e in self.entries.values() if e.verdict == INCLUDE]

    def decide(self, key: str, verdict: str, reason: str) -> None:
        assert verdict in VERDICTS, f"筛选结论只认 {VERDICTS}，得到 {verdict!r}"
        self.entries[key].verdict = verdict
        self.entries[key].reason = reason

    def note_refs(self, paper: Paper) -> None:
        """收录的 paper 引用的每一篇记一条向后的线索。"""
        for ref in paper.refs:
            self._lead(ref, f"ref:{paper.key}")

    def note_citing(self, key: str, citing: list[Paper]) -> None:
        """引用了收录的 key 的论文记向前的线索；元数据顺手进缓存，省一次批量取。"""
        for paper in citing:
            self.cache[paper.key] = paper
            self._lead(paper.key, f"cites:{key}")

    def open_leads(self) -> list[str]:
        """还没进池的线索，关联多的在前（同样多的按 W 号，结果稳定可复现）。"""
        return sorted((k for k in self.leads if k not in self.entries),
                      key=lambda k: (-self.links(k), k))

    def links(self, key: str) -> int:
        """一条线索关联到几篇收录的论文：同一篇既引用它又被它引用只算一篇。"""
        return len({mark.split(":", 1)[1] for mark in self.leads[key]})

    def next_batch(self, n: int) -> list[Paper]:
        """下一跳交给模型筛的 n 篇：关联多的在前，同样多的被引多的在前。没取到元数据的不排。"""
        ready = [k for k in self.open_leads() if k in self.cache]
        ready.sort(key=lambda k: (-self.links(k), -self.cache[k].cited_by, k))
        return [self.cache[k] for k in ready[:n]]

    def found_of(self, key: str) -> list[str]:
        return sorted(self.leads[key])

    def describe(self, mark: str) -> str:
        """来源标记 → 一句话：给模型筛与给人看用同一句。"""
        kind, _, value = mark.partition(":")
        if kind == "seed":
            return "种子（联网搜索找到）"
        if kind == "query":
            return f"检索词「{value}」"
        title = self.entries[value].paper.title if value in self.entries else value
        return f"被收录的《{title}》引用" if kind == "ref" else f"引用了收录的《{title}》"

    def save(self, path: Path) -> None:
        """看过的每篇一行 JSON（`candidates.jsonl`），按进池顺序；每跳结束重写一次。"""
        lines = [json.dumps(e.to_dict(), ensure_ascii=False) for e in self.entries.values()]
        write_atomic(path, "\n".join(lines) + ("\n" if lines else ""))

    def _lead(self, key: str, mark: str) -> None:
        if key not in self.excluded:
            self.leads[key].add(mark)
