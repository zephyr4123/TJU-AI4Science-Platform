"""第 0 跳的候选从哪来：种子，加检索词在四家的命中（外层 #212）。

- 种子按 DOI / arXiv 号批量回 OpenAlex 取，直接进第 0 跳（执行层挑的，不再排）。
- 检索词：前几条在 OpenAlex 检索（一次扣 10 积分），全部逐条过 Crossref、arXiv、Europe PMC
  （不扣额度）。命中的编号回 OpenAlex 批量取元数据，记成线索：被几个「哪家 × 检索词」查到 ×
  （1 + 2 × 字面相关度），新论文与经典论文两种排法轮流取前若干篇进第 0 跳（`Pool.opening_batch`）。
- 失败不阻塞（外层 #228）：不扣额度的三家各查各的（一家一个线程，每家内部照旧串行、按站点限速），
  一家卡在重试里拖不住别家。某家重试用完仍失败，这次就当它不可用，后面的检索词不再问它（原来逐条
  重试，arXiv 挂了时一条约 4 分钟、15 条近一个小时）；三家一共等 `INDEX_BUDGET_S`，到点没查完的
  那家，已经回来的照收。没查成的都写进 sources.md：少一路只是少一些，不算这一步失败。
  OpenAlex 查不成才是失败（元数据都从它来），由调用方判。

为什么要多铺几路：召回实测里漏掉的多是被引很少的小方向应用论文，往外扩一跳够不着，只有更细的
检索词能查到；而 OpenAlex 的关键词检索太贵，铺不开。
"""

from __future__ import annotations

import logging
import threading
import time
from collections import Counter
from collections.abc import Callable
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
from framework.capabilities.literature_search.web import FetchError, Web

LOGGER = logging.getLogger("ai4sci.literature")

MAX_QUERIES = 15      # 检索词最多用几条：不扣额度的三家一条约 6 秒（arXiv 要隔 3 秒）
OPENALEX_QUERIES = 5  # 其中前几条也在 OpenAlex 检索：一次扣 10 积分（每天 1000）
QUERY_RESULTS = 10    # 每家每条检索词取前几篇
MAX_SEEDS = 20
# 三家关键词检索一共等多久：正常 arXiv 最慢，15 条约一分钟（两次请求隔 3 秒），给两倍
INDEX_BUDGET_S = 120.0


@dataclass
class Gathered:
    unresolved_seeds: list[str] = field(default_factory=list)
    old_seeds: int = 0     # 早于起始年份、没交给模型筛的种子
    hits: Counter[str] = field(default_factory=Counter)   # 每家命中几条
    failures: list[str] = field(default_factory=list)     # 哪家哪条检索词没查成
    unmatched: int = 0     # 命中了、但 OpenAlex 里取不到元数据的
    distinct: int = 0      # 检索命中去重后几篇（不含种子）
    queries: int = 0


def gather(pool: Pool, client: OpenAlex, seeds: Seeds, cap: int,
           progress: Callable[..., None]) -> Gathered:
    """`progress` 记进度（loop.py 的 progress.jsonl）：三家各自查完的那一刻报一行。"""
    got = Gathered(queries=min(len(seeds.queries), MAX_QUERIES))
    queries = seeds.queries[:MAX_QUERIES]
    lanes = _start_lanes(client.web, queries, pool.since, progress)
    _seeds(pool, client, seeds, got)
    for query in queries[:OPENALEX_QUERIES]:
        works = client.search(query, QUERY_RESULTS, pool.since)
        got.hits["OpenAlex"] += len(works)
        for work in works:
            pool.note_query(from_openalex(work), "OpenAlex", query)
    found = _collect(lanes, queries, got)
    lookup = _resolve(client, {h.doi for h, _ in found if h.doi},
                      {h.arxiv for h, _ in found if h.arxiv}, {h.pmid for h, _ in found if h.pmid})
    for hit, query in found:
        paper = lookup.find(hit.doi, hit.arxiv, hit.pmid)
        if paper is None:
            got.unmatched += 1
        else:
            pool.note_query(paper, hit.source, query)
    got.distinct = len(pool.open_leads())
    for paper in pool.opening_batch(cap):
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
            if pool.in_period(paper):
                pool.admit(paper, 0, "seed")
            else:
                got.old_seeds += 1


@dataclass
class _Lane:
    """一家检索源这一次的结果。只有它自己的线程写；主线程到点后读一份快照，之后再写的不算。"""

    name: str
    search: Callable[[Web, str, int, int], list[indexes.Hit]]
    answered: dict[int, list[indexes.Hit]] = field(default_factory=dict)  # 第几条检索词 → 命中
    # 重试用完仍失败的那条（第几条, 错误），之后的不再问；一次赋值，主线程读到的要么有要么没有
    failed: tuple[int, str] | None = None
    cut: threading.Event = field(default_factory=threading.Event)  # 到点了：不再起下一条
    thread: threading.Thread | None = None


def _start_lanes(web: Web, queries: tuple[str, ...], since: int,
                 progress: Callable[..., None]) -> list[_Lane]:
    """三家各起一个线程（daemon：到点没查完就不等它，进程退出时不被它拖住）。"""
    lanes = [_Lane(name, search) for name, search in indexes.SOURCES]
    for lane in lanes:
        lane.thread = threading.Thread(target=_run_lane, args=(lane, web, queries, since, progress),
                                       name=f"index-{lane.name}", daemon=True)
        lane.thread.start()
    return lanes


def _run_lane(lane: _Lane, web: Web, queries: tuple[str, ...], since: int,
              progress: Callable[..., None]) -> None:
    """一家逐条查；查完或放弃时报一行进度。到时限被截的不报：它查到的算不算，由主线程那份快照定。"""
    for i, query in enumerate(queries):
        if lane.cut.is_set():
            return
        try:
            lane.answered[i] = lane.search(web, query, QUERY_RESULTS, since)
        except FetchError as err:
            LOGGER.warning("index_failed source=%s query=%r error=%s", lane.name, query, err)
            lane.failed = (i, str(err))
            break
    progress(step="gather", source=lane.name,
             hits=sum(len(hits) for hits in lane.answered.values()), failed=lane.failed is not None)


def _collect(lanes: list[_Lane], queries: tuple[str, ...],
             got: Gathered) -> list[tuple[indexes.Hit, str]]:
    """等三家查完或到时限（从起线程算），按「检索词 × 哪家」的原顺序合并，结果可复现。"""
    deadline = time.monotonic() + INDEX_BUDGET_S
    for lane in lanes:
        assert lane.thread is not None
        lane.thread.join(max(0.0, deadline - time.monotonic()))
    snapshots = [(lane.name, dict(lane.answered), lane.failed) for lane in lanes]
    for lane in lanes:
        lane.cut.set()  # 没查完的那家手上那条查完就停，不再白占对面的限额
    found: list[tuple[indexes.Hit, str]] = []
    for i, query in enumerate(queries):
        for name, answered, _ in snapshots:
            hits = answered.get(i, [])
            got.hits[name] += len(hits)
            found += [(hit, query) for hit in hits]
    for name, answered, failed in snapshots:
        got.failures += _missed(name, queries, answered, failed)
        LOGGER.info("index_lane source=%s answered=%d/%d failed_at=%s", name, len(answered),
                    len(queries), "-" if failed is None else failed[0])
    return found


def _missed(name: str, queries: tuple[str, ...], answered: dict[int, list[indexes.Hit]],
            failed: tuple[int, str] | None) -> list[str]:
    """一家没查成的几句话，写进 sources.md：哪条失败、之后几条没再问，或到时限几条没查。"""
    if failed is not None:
        i, err = failed
        rest = len(queries) - i - 1
        return [f"{name}「{queries[i]}」：{err}"] + (
            [f"{name}：重试用完仍失败，这次当它不可用，之后 {rest} 条检索词没再问"] if rest else [])
    unasked = len(queries) - len(answered)
    return [f"{name}：到了时限还没查完，{unasked} 条检索词没查"] if unasked else []


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
