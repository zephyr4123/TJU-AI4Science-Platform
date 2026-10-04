"""第 0 跳的候选从哪来：种子，加检索词在四家的命中（外层 #212）。

- 种子按 DOI / arXiv 号批量回 OpenAlex 取，直接进第 0 跳（执行层挑的，不再排）。
- 检索词：前几条在 OpenAlex 检索（一次扣 10 积分），全部逐条过 Crossref、arXiv、Europe PMC
  （不扣额度）。命中的编号回 OpenAlex 批量取元数据，记成线索，与之后几跳同一套排法：被几个
  「哪家 × 检索词」查到 ×（1 + 2 × 字面相关度），取前若干篇进第 0 跳。
- 不扣额度的三家某条没查成（重试用完）不算这一步失败：记下来写进 sources.md，少一路而已；
  OpenAlex 查不成才是失败，由调用方判。

为什么要多铺几路：召回实测里漏掉的多是被引很少的小方向应用论文，往外扩一跳够不着，只有更细的
检索词能查到；而 OpenAlex 的关键词检索太贵，铺不开。
"""

from __future__ import annotations

import logging
from collections import Counter
from dataclasses import dataclass, field

from framework.capabilities.literature_search import indexes
from framework.capabilities.literature_search.exchange import Seeds
from framework.capabilities.literature_search.openalex import OpenAlex
from framework.capabilities.literature_search.papers import (
    ARXIV_DOI_PREFIX,
    Paper,
    arxivs_in,
    dois_in,
    from_openalex,
)
from framework.capabilities.literature_search.pool import Pool
from framework.capabilities.literature_search.web import FetchError

LOGGER = logging.getLogger("ai4sci.literature")

MAX_QUERIES = 15      # 检索词最多用几条：不扣额度的三家一条约 6 秒（arXiv 要隔 3 秒）
OPENALEX_QUERIES = 5  # 其中前几条也在 OpenAlex 检索：一次扣 10 积分（每天 1000）
QUERY_RESULTS = 10    # 每家每条检索词取前几篇
MAX_SEEDS = 20


@dataclass
class Gathered:
    unresolved_seeds: list[str] = field(default_factory=list)
    hits: Counter[str] = field(default_factory=Counter)   # 每家命中几条
    failures: list[str] = field(default_factory=list)     # 哪家哪条检索词没查成
    unmatched: int = 0     # 命中了、但 OpenAlex 里取不到元数据的
    distinct: int = 0      # 检索命中去重后几篇（不含种子）
    queries: int = 0


def gather(pool: Pool, client: OpenAlex, seeds: Seeds, cap: int) -> Gathered:
    got = Gathered(queries=min(len(seeds.queries), MAX_QUERIES))
    _seeds(pool, client, seeds, got)
    queries = seeds.queries[:MAX_QUERIES]
    for query in queries[:OPENALEX_QUERIES]:
        works = client.search(query, QUERY_RESULTS)
        got.hits["OpenAlex"] += len(works)
        for work in works:
            pool.note_query(from_openalex(work), "OpenAlex", query)
    found: list[tuple[indexes.Hit, str]] = []
    for query in queries:
        for name, search in indexes.SOURCES:
            try:
                hits = search(client.web, query, QUERY_RESULTS)
            except FetchError as err:
                LOGGER.warning("index_failed source=%s query=%r error=%s", name, query, err)
                got.failures.append(f"{name}「{query}」：{err}")
                continue
            got.hits[name] += len(hits)
            found += [(hit, query) for hit in hits]
    lookup = _resolve(client, {h.doi for h, _ in found if h.doi},
                      {h.arxiv for h, _ in found if h.arxiv}, {h.pmid for h, _ in found if h.pmid})
    for hit, query in found:
        paper = lookup.find(hit.doi, hit.arxiv, hit.pmid)
        if paper is None:
            got.unmatched += 1
        else:
            pool.note_query(paper, hit.source, query)
    got.distinct = len(pool.open_leads())
    for paper in pool.next_batch(cap):
        for mark in pool.found_of(paper.key):
            pool.admit(paper, 0, mark)
    LOGGER.info("gather seeds=%d unresolved=%d queries=%d hits=%s unmatched=%d distinct=%d "
                "admitted=%d failures=%d", len(seeds.seeds[:MAX_SEEDS]),
                len(got.unresolved_seeds), got.queries, dict(got.hits), got.unmatched,
                got.distinct, len(pool.of_hop(0)), len(got.failures))
    return got


def _seeds(pool: Pool, client: OpenAlex, seeds: Seeds, got: Gathered) -> None:
    lines = list(seeds.seeds[:MAX_SEEDS])
    wanted = {line: (dois_in(line), arxivs_in(line)) for line in lines}
    lookup = _resolve(client, {d for dois, _ in wanted.values() for d in dois},
                      {a for _, ids in wanted.values() for a in ids}, set())
    for line, (dois, ids) in wanted.items():
        papers = [lookup.find(d, None, None) for d in dois] + [lookup.find(None, a, None)
                                                                for a in ids]
        papers = [p for p in papers if p is not None]
        if not papers:
            got.unresolved_seeds.append(line)
        for paper in papers:
            pool.admit(paper, 0, "seed")


class _Lookup:
    def __init__(self, papers: list[Paper]) -> None:
        self.by_doi = {p.doi: p for p in papers if p.doi}
        self.by_arxiv = {p.arxiv: p for p in papers if p.arxiv}
        self.by_pmid = {p.pmid: p for p in papers if p.pmid}

    def find(self, doi: str | None, arxiv: str | None, pmid: str | None) -> Paper | None:
        return ((doi and self.by_doi.get(doi)) or (arxiv and self.by_arxiv.get(arxiv))
                or (pmid and self.by_pmid.get(pmid)) or None)


def _resolve(client: OpenAlex, dois: set[str], arxivs: set[str], pmids: set[str]) -> _Lookup:
    """编号回 OpenAlex 批量取（一批 50 篇扣 1）。arXiv 号先按落地页查，查不到的再按 arXiv 的 DOI
    查：发了期刊的只认落地页，只有预印本的两种都认，两路都走才不漏。"""
    papers = [from_openalex(w) for w in client.by_dois(sorted(dois))
              + client.by_arxiv(sorted(arxivs)) + client.by_pmids(sorted(pmids))]
    seen = {p.arxiv for p in papers if p.arxiv}
    rest = sorted(ARXIV_DOI_PREFIX + a for a in arxivs - seen)
    papers += [from_openalex(w) for w in client.by_dois(rest)]
    return _Lookup(papers)
