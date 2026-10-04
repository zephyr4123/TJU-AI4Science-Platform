"""一篇论文在文献检索里的样子：从 OpenAlex 的记录取出要用的字段，以及从种子文字里认 DOI / arXiv 号。

键用 OpenAlex 的 W 号：参考文献表与「谁引用了它」给的都是 W 号，去重与多跳的连线都按它算。
DOI 与 arXiv 号只用来进门（种子）和给人看。arXiv 预印本在 OpenAlex 里的 DOI 是
`10.48550/arxiv.<号>`，所以 arXiv 链接一律换成这个 DOI 去查，不另接 arXiv 的接口。
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from typing import Any

# DOI：前缀 10.<4~9 位注册号>/，后缀到空白或成对符号为止；句末标点另外剥掉
DOI_RE = re.compile(r"10\.\d{4,9}/[^\s\"'<>\[\]{}]+")
ARXIV_RE = re.compile(
    r"(?:arxiv\.org/(?:abs|pdf|html)/|arxiv:\s*)"
    r"(\d{4}\.\d{4,5}|[a-z\-]+(?:\.[a-z]{2})?/\d{7})(?:v\d+)?", re.IGNORECASE)
WORK_KEY_RE = re.compile(r"W\d+")
ARXIV_DOI_PREFIX = "10.48550/arxiv."
AUTHORS_KEPT = 8  # 给人看与给模型筛都用不着全部作者，几百人的合作论文只留前几位


@dataclass(frozen=True)
class Paper:
    key: str                  # OpenAlex 的 W 号
    title: str
    year: int | None
    authors: tuple[str, ...]
    venue: str                # 期刊、会议或预印本服务器的名字；不知道是空串
    doi: str | None           # 裸 DOI（10.xxx/...），小写
    arxiv: str | None         # arXiv 号，不带版本
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
    doi = _bare_doi(work.get("doi"))
    primary = work.get("primary_location") or {}
    source = primary.get("source") or {}
    landing = primary.get("landing_page_url")
    arxiv = arxiv_of(doi, landing)
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


def arxiv_of(doi: str | None, landing: str | None) -> str | None:
    if doi and doi.startswith(ARXIV_DOI_PREFIX):
        return doi[len(ARXIV_DOI_PREFIX):]
    match = ARXIV_RE.search(landing or "")
    return match.group(1).lower() if match else None


def dois_in(text: str) -> list[str]:
    """一行种子里认出的 DOI（arXiv 链接换成它在 OpenAlex 里的 DOI），按出现顺序、去重。"""
    found = [_bare_doi(m.group(0)) for m in DOI_RE.finditer(text)]
    found += [ARXIV_DOI_PREFIX + m.group(1).lower() for m in ARXIV_RE.finditer(text)]
    return list(dict.fromkeys(d for d in found if d))


def _bare_doi(value: str | None) -> str | None:
    """`https://doi.org/10.1/ABC.` → `10.1/abc`：去掉链接前缀与句末标点；
    DOI 不分大小写，一律小写。"""
    if not value:
        return None
    match = DOI_RE.search(value)
    return match.group(0).rstrip(".,;:)").lower() if match else None
