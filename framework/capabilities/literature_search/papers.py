"""一篇论文在文献检索里的样子：从 OpenAlex 的记录取出要用的字段，以及从种子文字里认 DOI / arXiv 号。

键用 OpenAlex 的 W 号：参考文献表与「谁引用了它」给的都是 W 号，去重与多跳的连线都按它算。
DOI 与 arXiv 号只用来进门（种子）和给人看。arXiv 号不换成 `10.48550/arxiv.<号>` 去按 DOI 查：
论文后来发了期刊的，OpenAlex 的主 DOI 是期刊的，arXiv 只挂在 `locations` 里，按 DOI 查是 404
（2026-10-04 真跑，B-PINNs 等三篇种子就这样丢了）；改按落地页 `http://arxiv.org/abs/<号>` 查。
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, replace
from typing import Any

# DOI：前缀 10.<4~9 位注册号>/，后缀到空白或成对符号为止；句末标点另外剥掉
DOI_RE = re.compile(r"10\.\d{4,9}/[^\s\"'<>\[\]{}]+")
ARXIV_RE = re.compile(
    r"(?:arxiv\.org/(?:abs|pdf|html)/|arxiv:\s*)"
    r"(\d{4}\.\d{4,5}|[a-z\-]+(?:\.[a-z]{2})?/\d{7})(?:v\d+)?", re.IGNORECASE)
WORK_KEY_RE = re.compile(r"W\d+")
PMID_RE = re.compile(r"(\d+)\s*$")  # OpenAlex 给的是 https://pubmed.ncbi.nlm.nih.gov/<号>
ARXIV_DOI_PREFIX = "10.48550/arxiv."
AUTHORS_KEPT = 8  # 给人看与给模型筛都用不着全部作者，几百人的合作论文只留前几位
# 认同一篇的不同版本：题目归一后至少这么长才认（「Introduction」这类短题目不同论文撞上的多），
# 年份差不过这么多（预印本到期刊一两年）
VERSION_TITLE_MIN = 20
VERSION_YEARS = 2


@dataclass(frozen=True)
class Paper:
    key: str                  # OpenAlex 的 W 号
    title: str
    year: int | None
    authors: tuple[str, ...]
    venue: str                # 期刊、会议或预印本服务器的名字；不知道是空串
    doi: str | None           # 裸 DOI（10.xxx/...），小写
    arxiv: str | None         # arXiv 号，不带版本
    pmid: str | None          # PubMed 号（Europe PMC 的命中按它对回来）
    abstract: str             # OpenAlex 没有摘要是空串
    cited_by: int
    refs: tuple[str, ...]     # 它引用的论文（W 号）
    pdf_url: str | None       # 开放获取的 PDF；arXiv 的按号拼
    landing_url: str | None   # 出版社或预印本的落地页

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Paper:
        return cls(**{**data, "authors": tuple(data["authors"]), "refs": tuple(data["refs"])})


def from_openalex(work: dict[str, Any]) -> Paper:
    """OpenAlex 的一条 work（按 `openalex.SELECT` 取的字段）→ Paper。缺的字段给空，不编。"""
    doi = bare_doi(work.get("doi"))
    primary = work.get("primary_location") or {}
    source = primary.get("source") or {}
    landing = primary.get("landing_page_url")
    arxiv = arxiv_of(doi, [landing, *(loc.get("landing_page_url")
                                      for loc in work.get("locations") or [])])
    pubmed = PMID_RE.search((work.get("ids") or {}).get("pmid") or "")
    best = work.get("best_oa_location") or {}
    pdf = best.get("pdf_url") or (f"https://arxiv.org/pdf/{arxiv}" if arxiv else None)
    return Paper(
        key=work_key(work["id"]),
        title=(work.get("display_name") or "").strip(),
        year=work.get("publication_year"),
        authors=tuple(a["author"]["display_name"]
                      for a in (work.get("authorships") or [])[:AUTHORS_KEPT]
                      if (a.get("author") or {}).get("display_name")),
        venue=(source.get("display_name") or "").strip(),
        doi=doi,
        arxiv=arxiv,
        pmid=pubmed.group(1) if pubmed else None,
        abstract=abstract_text(work.get("abstract_inverted_index")),
        cited_by=int(work.get("cited_by_count") or 0),
        refs=tuple(work_key(r) for r in work.get("referenced_works") or []),
        pdf_url=pdf,
        landing_url=landing,
    )


def work_key(openalex_id: str) -> str:
    """`https://openalex.org/W123` 或 `W123` → `W123`。认不出就抛：W 号是池子的键，不能猜。"""
    match = WORK_KEY_RE.search(openalex_id or "")
    if match is None:
        raise ValueError(f"认不出 OpenAlex 的 W 号：{openalex_id!r}")
    return match.group(0)


def abstract_text(inverted: dict[str, list[int]] | None) -> str:
    """OpenAlex 的摘要是倒排表（词 → 出现的位置）；按位置排回原文。"""
    if not inverted:
        return ""
    positions = sorted((pos, word) for word, places in inverted.items() for pos in places)
    return " ".join(word for _, word in positions)


def arxiv_of(doi: str | None, landings: list[str | None]) -> str | None:
    """arXiv 号：DOI 是 arXiv 的就从它取，否则看各个落地页里有没有 arxiv.org 的。"""
    if doi and doi.startswith(ARXIV_DOI_PREFIX):
        return doi[len(ARXIV_DOI_PREFIX):]
    for landing in landings:
        match = ARXIV_RE.search(landing or "")
        if match:
            return match.group(1).lower()
    return None


def dois_in(text: str) -> list[str]:
    """一行种子里认出的 DOI（arXiv 的 DOI 不算，归 `arxivs_in`），按出现顺序、去重。"""
    found = [bare_doi(m.group(0)) for m in DOI_RE.finditer(text)]
    return list(dict.fromkeys(d for d in found if d and not d.startswith(ARXIV_DOI_PREFIX)))


def arxivs_in(text: str) -> list[str]:
    """一行种子里认出的 arXiv 号：arxiv.org 链接、`arXiv:` 写法、arXiv 的 DOI，按出现顺序、去重。"""
    found = [m.group(1).lower() for m in ARXIV_RE.finditer(text)]
    found += [d[len(ARXIV_DOI_PREFIX):] for d in map(bare_doi, (m.group(0) for m in
              DOI_RE.finditer(text))) if d and d.startswith(ARXIV_DOI_PREFIX)]
    return list(dict.fromkeys(found))


def bare_doi(value: str | None) -> str | None:
    """`https://doi.org/10.1/ABC.` → `10.1/abc`：去掉链接前缀与句末标点；
    DOI 不分大小写，一律小写。"""
    if not value:
        return None
    match = DOI_RE.search(value)
    return match.group(0).rstrip(".,;:)").lower() if match else None


def version_title(title: str) -> str | None:
    """认同一篇不同版本用的题目：小写、只留字母与数字；太短的不认，返回 None。"""
    words = " ".join(re.findall(r"[a-z0-9]+", title.lower()))
    return words if len(words) >= VERSION_TITLE_MIN else None


def same_work(a: Paper, b: Paper) -> bool:
    """同一篇的不同版本（预印本 / 会议 / 期刊在 OpenAlex 各一个 W 号，外层 #232）：题目归一后一样、
    年份差不过 `VERSION_YEARS`（不知道年份的不拦）。"""
    title = version_title(a.title)
    return (title is not None and title == version_title(b.title)
            and (a.year is None or b.year is None or abs(a.year - b.year) <= VERSION_YEARS))


def merge_versions(kept: Paper, other: Paper) -> Paper:
    """另一个版本补进来：缺的编号、摘要、原文与落地页从它取（期刊版常没有开放获取的 PDF，
    arXiv 版有），参考文献并起来，被引取大的；W 号、题目、年份、出处照旧用先进池的那个。"""
    return replace(kept, doi=kept.doi or other.doi, arxiv=kept.arxiv or other.arxiv,
                   pmid=kept.pmid or other.pmid, abstract=kept.abstract or other.abstract,
                   pdf_url=kept.pdf_url or other.pdf_url,
                   landing_url=kept.landing_url or other.landing_url,
                   refs=tuple(dict.fromkeys(kept.refs + other.refs)),
                   cited_by=max(kept.cited_by, other.cited_by))
