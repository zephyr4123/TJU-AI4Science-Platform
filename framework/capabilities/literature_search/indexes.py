"""三家不扣额度的关键词检索：Crossref、arXiv、Europe PMC（外层 #212）。

只取编号（DOI / arXiv 号 / PMID），不取元数据：元数据、摘要与引用关系统一回 OpenAlex 批量取
（一批 50 篇扣 1 积分），池子里每篇论文只有一种样子。OpenAlex 的关键词检索一次扣 10，所以检索词
多铺几路靠这三家。

实测（2026-10-04）：
- Crossref 全学科，单次约 1.5 秒；并发就 429，串行没事。只要期刊论文、会议论文与预印本，
  书的章节、数据集这类不要。
- arXiv 的检索式里空格是「或」（`all:a b` 查的是 a OR b，命中几十万条），要拼成
  `all:a AND all:b`；官方要求两次请求隔 3 秒。同一台机器上几次检索同时跑会被 429，不带
  Retry-After，1 / 2 / 4 秒退避三次就放弃，三个并行时丢了 5~10 条检索词（外层 #216），所以 arXiv
  按自己的退避表等得更久、多等一次。返回的是 Atom XML，只用正则取每条 entry 的 id，
  不起 XML 解析器（这里只要编号，用不着整棵树）。
- Europe PMC 生物医学为主，按相关度排；非生物医学的题目命中的多是不相关的，交给排序与筛选。

起始年份（外层 #227）每家都推到检索里，不只是事后滤：每条检索词每家只取前 10 篇，不推下去前 10
里多半是旧的。三家的写法：Crossref `from-pub-date`、arXiv `submittedDate` 区间（按第一版提交的
日子）、Europe PMC `PUB_YEAR` 区间；0 不限。
"""

from __future__ import annotations

import json
import re
import urllib.parse
from dataclasses import dataclass

from framework.capabilities.literature_search.papers import ARXIV_RE, bare_doi
from framework.capabilities.literature_search.web import Web

CROSSREF_URL = "https://api.crossref.org/works"
CROSSREF_TYPES = ("journal-article", "proceedings-article", "posted-content")
ARXIV_URL = "https://export.arxiv.org/api/query"
ARXIV_SPACING_S = 3.0
ARXIV_BACKOFF_S = (5.0, 15.0, 30.0, 60.0)
EUROPE_PMC_URL = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"
ENTRY_ID_RE = re.compile(r"<entry>.*?<id>\s*(\S+?)\s*</id>", re.DOTALL)


@dataclass(frozen=True)
class Hit:
    """一条检索命中：哪家查到的，带哪种编号（至少一种）。"""

    source: str
    doi: str | None = None
    arxiv: str | None = None
    pmid: str | None = None


def crossref(web: Web, query: str, n: int, since: int) -> list[Hit]:
    filters = [f"type:{t}" for t in CROSSREF_TYPES] + ([f"from-pub-date:{since}"] if since else [])
    params = {"query": query, "rows": str(n), "select": "DOI,type", "filter": ",".join(filters)}
    body, _ = web.get(f"{CROSSREF_URL}?{urllib.parse.urlencode(params)}")
    items = json.loads(body)["message"]["items"]
    return [Hit("Crossref", doi=d) for d in (bare_doi(i.get("DOI")) for i in items) if d]


def arxiv(web: Web, query: str, n: int, since: int) -> list[Hit]:
    terms = [t for t in re.split(r"\s+", query.replace('"', " ").strip()) if t]
    search = " AND ".join(f"all:{t}" for t in terms)
    if since:
        search += f" AND submittedDate:[{since}01010000 TO 300001010000]"
    params = {"search_query": search, "max_results": str(n)}
    body, _ = web.get(f"{ARXIV_URL}?{urllib.parse.urlencode(params)}", spacing_s=ARXIV_SPACING_S,
                      backoff_s=ARXIV_BACKOFF_S)
    ids = [m.group(1).lower() for m in map(ARXIV_RE.search,
                                           ENTRY_ID_RE.findall(body.decode("utf-8"))) if m]
    return [Hit("arXiv", arxiv=i) for i in dict.fromkeys(ids)]


def europe_pmc(web: Web, query: str, n: int, since: int) -> list[Hit]:
    where = f"{query} AND PUB_YEAR:[{since} TO 3000]" if since else query
    params = {"query": where, "format": "json", "pageSize": str(n), "resultType": "lite"}
    body, _ = web.get(f"{EUROPE_PMC_URL}?{urllib.parse.urlencode(params)}")
    results = json.loads(body)["resultList"]["result"]
    hits = [Hit("Europe PMC", doi=bare_doi(r.get("doi")), pmid=r.get("pmid")) for r in results]
    return [h for h in hits if h.doi or h.pmid]


# 检索词逐条过这三家（OpenAlex 的关键词检索另算，只给前几条）
SOURCES = (("Crossref", crossref), ("arXiv", arxiv), ("Europe PMC", europe_pmc))
