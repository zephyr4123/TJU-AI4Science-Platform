"""写 `sources.md`：文献阶段的主文件（P-20），给研究者与下游读。

格式由本能力定、下游只当文本读（复现流程把它原样拼进提示）。收录的每篇都写清怎么找到的、为什么收、
原文在不在；没收的不列在这里，在 `candidates.jsonl` 里逐篇带理由。
"""

from __future__ import annotations

from framework.capabilities.literature_search.exchange import Seeds
from framework.capabilities.literature_search.fulltext import Fulltext
from framework.capabilities.literature_search.gather import OPENALEX_QUERIES, Gathered
from framework.capabilities.literature_search.papers import Paper
from framework.capabilities.literature_search.pool import Entry, Pool

AUTHORS_SHOWN = 3


def render(*, title: str, seeds: Seeds, pool: Pool, stop: str, texts: dict[str, Fulltext],
           fulltext: bool, gathered: Gathered) -> str:
    included = sorted(pool.included(), key=lambda e: (e.hop, -e.paper.cited_by, e.paper.key))
    per_hop = "，".join(f"第 {hop} 跳 {n} 篇" for hop, n in _count_by_hop(included))
    got = [e for e in included if texts.get(e.paper.key, Fulltext(None, None)).path]
    lines = [
        f"# 材料来源：{title}",
        "",
        "文献检索的产出：框架查 OpenAlex、顺着引用往外扩，执行层按纳入标准看摘要筛。"
        "收录的每篇写了怎么找到的、为什么收；看过没收的在 candidates.jsonl，逐篇带理由。",
        "",
        f"- 检索词：{'；'.join(f'`{q}`' for q in seeds.queries[:gathered.queries])}",
        f"- 检索：{gathered.queries} 条检索词过 Crossref、arXiv、Europe PMC，前 "
        f"{min(gathered.queries, OPENALEX_QUERIES)} 条也过 OpenAlex；命中 "
        + "、".join(f"{name} {n} 条" for name, n in sorted(gathered.hits.items()))
        + f"，去重后 {gathered.distinct} 篇（OpenAlex 里取不到的 {gathered.unmatched} 条不算）"
        + (f"；{len(gathered.failures)} 次没查成，列在文末" if gathered.failures else ""),
        f"- 种子：{len(seeds.seeds)} 条，查不到的 {len(gathered.unresolved_seeds)} 条列在文末",
        f"- 看过摘要 {len(pool.entries)} 篇，收录 {len(included)} 篇" + (f"（{per_hop}）" if per_hop
                                                                    else ""),
        f"- 停在：{stop}",
        (f"- 原文：拿到 {len(got)} 篇，在 papers/ 下" if fulltext else "- 原文：这次没有下载"),
        "",
        "## 纳入标准",
        "",
        seeds.criteria,
        "",
        f"## 收录（{len(included)} 篇）",
    ]
    for number, entry in enumerate(included, start=1):
        lines += ["", *_paper_block(number, entry, pool, texts.get(entry.paper.key), fulltext)]
    missing = [e for e in included if fulltext and e not in got]
    if missing:
        lines += ["", f"## 没拿到原文的（{len(missing)} 篇）", "",
                  "请研究者自己下好放进 materials/：", ""]
        lines += [f"- 《{e.paper.title}》 {_link(e.paper) or '（没有链接）'}" for e in missing]
    if gathered.unresolved_seeds:
        lines += ["", "## 查不到的种子", "",
                  "认不出 DOI 或 arXiv 号，或 OpenAlex 里没有这一篇：", ""]
        lines += [f"- {line}" for line in gathered.unresolved_seeds]
    if gathered.failures:
        lines += ["", "## 没查成的检索", "", "重试三次仍失败，这一路少了：", ""]
        lines += [f"- {failure}" for failure in gathered.failures]
    return "\n".join(lines) + "\n"


def _paper_block(number: int, entry: Entry, pool: Pool, text: Fulltext | None,
                 fulltext: bool) -> list[str]:
    paper = entry.paper
    authors = "、".join(paper.authors[:AUTHORS_SHOWN]) + (
        " 等" if len(paper.authors) > AUTHORS_SHOWN else "")
    found = "；".join(pool.describe(m) for m in entry.found)
    block = [
        f"### {number}. {paper.title}（{paper.year or '年份不详'}）",
        "",
        f"- 作者：{authors or '不详'}",
        f"- 出处：{paper.venue or '不详'}；被引 {paper.cited_by}",
        f"- 链接：{_link(paper) or '没有'}",
        f"- 怎么找到的：{found}（第 {entry.hop} 跳）",
        f"- 为什么收：{entry.reason}",
    ]
    if fulltext and text is not None:
        block.append(f"- 原文：`{text.path}`（{text.pages} 页）" if text.path
                     else f"- 原文：没拿到，{text.why}")
    return block


def _link(paper: Paper) -> str:
    links = [f"https://doi.org/{paper.doi}"] if paper.doi else []
    if paper.arxiv:
        links.append(f"https://arxiv.org/abs/{paper.arxiv}")
    if not links and paper.landing_url:
        links.append(paper.landing_url)
    return " ｜ ".join(links)


def _count_by_hop(entries: list[Entry]) -> list[tuple[int, int]]:
    counts: dict[int, int] = {}
    for entry in entries:
        counts[entry.hop] = counts.get(entry.hop, 0) + 1
    return sorted(counts.items())
