"""候选池：看过的每篇论文从哪来、第几跳、筛的结论；还没看的线索按「被几篇已收录的关联」排队。

只是数据，不发请求、不起会话：查接口与起会话是 `loop.py` 的事，这里只管记账与排序，所以能
脱开网与模型单测。

线索怎么排（外层 #212 两道召回实测定的）：证据数 ×（1 + 2 × 字面相关度），同分看被引数。证据数是
关联到几篇已收录的，加被几个「哪家 × 检索词」查到（第 0 跳只有后者）。
只按关联数排分不开——线索池里关联 1 篇的上千条，答案就混在里面；字面相关度是题目加摘要命中
检索词的程度，词按在这批线索里的稀有度加权（「neural」「network」人人有，几乎不算分），零模型。
单用字面相关度更差（关联数才是「这篇在这个领域里被用到」的证据），乘上去最好；系数 1 到 3 结果
差不多，取 2：第 1 跳前 30 篇里的答案，生理信号那道 11→15，PINN 方法那道 6→7。

第 0 跳另有一处（`opening_batch`）：候选全是检索命中，没有「被谁用到」的证据，排在前面的多是
刚出来的新论文（生理信号那道前 60 篇里一半是 2026 年的）。两种排法轮流取：上面那种（新论文多），
与再乘 1 + ln(1 + 被引数)（经典论文多）。只用后者答案更多（前 60 篇 4→9 篇），可答案取自一篇
2025 年的综述，天然不含新论文，而研究者两头都要；轮流取答案 6 篇、2025 年后的仍有 26 篇。
第 1 跳不乘被引数：候选本来就是收录的论文引用的，再乘反而更差（生理信号那道前 30 篇 15→9）。

起始年份（外层 #227）：早于它的线索不排、不交给模型筛——检索那头已经按年份查了，这里挡的是
种子与向后的参考文献（多是旧的）；年份不详的照常交，不知道不等于旧。

同一篇的不同版本（外层 #232）：预印本、会议、期刊在 OpenAlex 各一个 W 号，演练里 130 篇有 6 组，
多占筛选名额、在 sources.md 列两遍，两个版本还被判出相反的结论。题目一样、年份相近的认成一篇
（`papers.same_work`）：池里已有的，另一个版本并进去、补上编号与原文链接；同一批里只取一个。

来源记成短标记，给人看时由 `report.py` 翻成话：
- `seed` 种子（执行层用自带搜索找来的）；`query:<哪家>:<检索词>` 关键词检索；
- `ref:<W>` 收录的 W 引用了它（向后）；`cites:<W>` 它引用了收录的 W（向前）。
"""

from __future__ import annotations

import json
import math
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path

from framework.capabilities.literature_search.papers import (
    Paper,
    merge_versions,
    same_work,
    version_title,
)
from framework.files import write_atomic

INCLUDE = "收"
EXCLUDE = "不收"
VERDICTS = (INCLUDE, EXCLUDE)
LEXICAL_WEIGHT = 2.0
# 字面相关度不算的词：英文虚词（检索词与题目都是英文的）
STOPWORDS = frozenset(
    "a an the of for and in on with by to from using via based its their is are we our this "
    "that as at or be into than".split())


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
    def __init__(self, excluded: frozenset[str] = frozenset(), queries: tuple[str, ...] = (),
                 since: int = 0) -> None:
        self.entries: dict[str, Entry] = {}
        # 线索：还没交给模型的 W 号 → 来源标记；元数据取过的放 cache（排序要被引数）
        self.leads: dict[str, set[str]] = defaultdict(set)
        self.cache: dict[str, Paper] = {}
        # 永远不进池的 W 号：召回实测时把当标准答案的那篇综述挡在外面，否则向后一跳就把答案全抄回来
        self.excluded = excluded
        self.terms = Counter(t for q in queries for t in set(tokens(q)))
        self.since = since  # 起始年份，0 不限；检索那头也按它查（gather / loop 读这一处）
        # 并进池里某篇的另一个版本：它的 W 号 → 并到了哪篇
        self.folded: dict[str, str] = {}
        self._titles: dict[str, str] = {}  # 归一后的题目 → 池里那篇的 W 号

    def admit(self, paper: Paper, hop: int, found: str) -> bool:
        """一篇论文交给第 hop 跳筛；已经在池里的只补一条来源。返回是不是新进的。"""
        if paper.key in self.excluded:
            return False
        same = self._entry_of(paper)
        if same is not None:
            self._fold(same, paper, [found])
            return False
        self.entries[paper.key] = Entry(paper, hop, [found])
        if title := version_title(paper.title):
            self._titles.setdefault(title, paper.key)
        return True

    def in_period(self, paper: Paper) -> bool:
        return not self.since or paper.year is None or paper.year >= self.since

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

    def note_query(self, paper: Paper, source: str, query: str) -> None:
        """一条检索命中记成线索：第 0 跳也照线索排，被几家、几条检索词同时查到的在前。已经进池的
        （种子）只补一条来源。"""
        mark = f"query:{source}:{query}"
        same = self._entry_of(paper)
        if same is not None:
            self._fold(same, paper, [mark])
            return
        self.cache[paper.key] = paper
        self._lead(paper.key, mark)

    def note_citing(self, paper: Paper, cited: set[str]) -> None:
        """paper 引用了收录的 cited 里的这几篇：记向前的线索；元数据顺手进缓存，省一次批量取。"""
        self.cache[paper.key] = paper
        for key in cited:
            self._lead(paper.key, f"cites:{key}")

    def open_leads(self) -> list[str]:
        """还没进池的线索，关联多的在前（同样多的按 W 号，结果稳定可复现）。"""
        return sorted((k for k in self.leads if k not in self.entries and k not in self.folded),
                      key=lambda k: (-self.links(k), k))

    def links(self, key: str) -> int:
        """一条线索有几条独立的证据：关联到几篇收录的论文（同一篇既引用它又被它引用只算一篇），
        加上被几个「哪家 × 检索词」查到。"""
        return len({mark.split(":", 1)[1] for mark in self.leads[key]})

    def next_batch(self, n: int) -> list[Paper]:
        """下一跳交给模型筛的 n 篇：关联数 ×（1 + 2 × 字面相关度）高的在前，同分被引多的在前。
        没取到元数据的、早于起始年份的不排。"""
        ready = self._ready()
        relevance = self._lexical(ready)
        ready.sort(key=lambda k: (-self.links(k) * (1 + LEXICAL_WEIGHT * relevance[k]),
                                  -self.cache[k].cited_by, k))
        return [self.cache[k] for k in ready[:n]]

    def opening_batch(self, n: int) -> list[Paper]:
        """第 0 跳的 n 篇：「新」与「经典」两种排法轮流取，重复的跳过。"""
        ready = self._ready()
        relevance = self._lexical(ready)

        def base(k: str) -> float:
            return self.links(k) * (1 + LEXICAL_WEIGHT * relevance[k])
        fresh = sorted(ready, key=lambda k: (-base(k), -self.cache[k].cited_by, k))
        classic = sorted(ready, key=lambda k: (
            -base(k) * (1 + math.log1p(self.cache[k].cited_by)), k))
        picked: list[str] = []
        for pair in zip(fresh, classic, strict=True):
            for key in pair:
                if key not in picked and len(picked) < n:
                    picked.append(key)
        return [self.cache[k] for k in picked]

    def _ready(self) -> list[str]:
        """能排的线索：取到了元数据、不早于起始年份；池里某篇的另一个版本先并进去，同一篇的几个
        版本只留证据最多的一个（其余留作线索，那一个进池后下次并进去）。"""
        ready: dict[str, str] = {}
        for key in self.open_leads():
            paper = self.cache.get(key)
            if paper is None or not self.in_period(paper):
                continue
            same = self._entry_of(paper)
            if same is not None:
                self._fold(same, paper, sorted(self.leads[key]))
                continue
            title = version_title(paper.title) or key
            if title not in ready:  # open_leads 按证据数排好了，先到的就是证据最多的
                ready[title] = key
        return list(ready.values())

    def _entry_of(self, paper: Paper) -> Entry | None:
        """池里的同一篇：同一个 W 号、并过的版本，或题目一样、年份相近的另一个版本。"""
        key = self.folded.get(paper.key, paper.key)
        if key in self.entries:
            return self.entries[key]
        title = version_title(paper.title)
        entry = self.entries.get(self._titles.get(title, "")) if title else None
        return entry if entry is not None and same_work(entry.paper, paper) else None

    def _fold(self, entry: Entry, paper: Paper, marks: list[str]) -> None:
        if paper.key != entry.paper.key and paper.key not in self.folded:
            entry.paper = merge_versions(entry.paper, paper)
            self.folded[paper.key] = entry.paper.key
        entry.found += [m for m in marks if m not in entry.found]

    def _lexical(self, keys: list[str]) -> dict[str, float]:
        """每条线索的题目加摘要命中检索词的程度（0~1），词按在这批线索里的稀有度（idf）加权。"""
        words = {k: set(tokens(f"{self.cache[k].title} {self.cache[k].abstract}")) for k in keys}
        df = Counter(t for w in words.values() for t in w if t in self.terms)
        weight = {t: (math.log((len(keys) + 1) / (df[t] + 1)) + 1) * n
                  for t, n in self.terms.items()}
        total = sum(weight.values())
        if not total:
            return dict.fromkeys(keys, 0.0)
        return {k: sum(v for t, v in weight.items() if t in words[k]) / total for k in keys}

    def found_of(self, key: str) -> list[str]:
        return sorted(self.leads[key])

    def describe(self, mark: str) -> str:
        """来源标记 → 一句话：给模型筛与给人看用同一句。"""
        kind, _, value = mark.partition(":")
        if kind == "seed":
            return "种子（联网搜索找到）"
        if kind == "query":
            source, _, query = value.partition(":")
            return f"检索词「{query}」（{source}）"
        title = self.entries[value].paper.title if value in self.entries else value
        return f"被收录的《{title}》引用" if kind == "ref" else f"引用了收录的《{title}》"

    def save(self, path: Path) -> None:
        """看过的每篇一行 JSON（`candidates.jsonl`），按进池顺序；每跳结束重写一次。"""
        lines = [json.dumps(e.to_dict(), ensure_ascii=False) for e in self.entries.values()]
        write_atomic(path, "\n".join(lines) + ("\n" if lines else ""))

    def _lead(self, key: str, mark: str) -> None:
        if key not in self.excluded:
            self.leads[key].add(mark)


def tokens(text: str) -> list[str]:
    """英文小写词，去虚词与两个字母以下的；连字符留在词里（physics-informed 是一个词）。"""
    return [t for t in re.findall(r"[a-z][a-z\-]+", text.lower())
            if t not in STOPWORDS and len(t) > 2]
