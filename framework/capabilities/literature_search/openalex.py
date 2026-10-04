"""OpenAlex 的客户端：文献检索的元数据与引用关系都从这里取（外层 #212）。

为什么元数据统一到它：四家免费接口里只有它同时给摘要、参考文献表与「谁引用了它」，多跳只能靠它；
Crossref、arXiv、Europe PMC 只用来按关键词多铺几路，命中的 DOI / arXiv 号 / PMID 回到这里批量取。
Semantic Scholar 不配 key 单次请求也 429、CORE 时好时坏、Google Scholar 是爬网页，都不接
（2026-10-04 实测）。

额度：不配 key 每个 IP 每天 1000 积分，配了免费的 key 每天 10000（纲领 P-27：不要 key 也能用，
有 key 用得更多；key 只从环境变量 `OPENALEX_API_KEY` 读，读取点只在这里，放请求头不进 URL）。
关键词检索一次扣 10，filter 列表（按 DOI / W 号 / arXiv 落地页 / PMID 批量取、`cites:`）一次扣 1，
按 id 取单篇扣 0。所以关键词检索只给前几条检索词用、其余走另外三家；批量取一次 100 个；「谁引用了
它」把一跳的新收录合成一次 OR 查询（原来一篇一次，占一次检索花费的三分之一）。响应头
`x-ratelimit-remaining` 每次记日志；额度用完抛 `QuotaExhausted`，不静默少查。
"""

from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.parse
from typing import Any

from framework.capabilities.literature_search.web import Web

LOGGER = logging.getLogger("ai4sci.literature")

BASE_URL = "https://api.openalex.org/works"
SELECT = ("id,doi,ids,display_name,publication_year,authorships,primary_location,locations,"
          "cited_by_count,abstract_inverted_index,referenced_works,best_oa_location")
BATCH = 100        # filter 里一次 OR 的个数：OpenAlex 的上限
CITING_PAGE = 200  # 「谁引用了它」一页取多少（OpenAlex 一页的上限）
KEY_ENV = "OPENALEX_API_KEY"


class OpenAlexError(RuntimeError):
    """返回的不是预期的形状。"""


class QuotaExhausted(OpenAlexError):
    """今天的额度用完了：不配 key 每个 IP 每天 1000 积分，到点重置。"""


def api_key() -> str | None:
    """`OPENALEX_API_KEY`：可选，设了额度大十倍；空串当没设。"""
    return os.environ.get(KEY_ENV, "").strip() or None


class OpenAlex:
    def __init__(self, web: Web | None = None, key: str | None = None) -> None:
        self.web = web or Web()
        self.remaining: int | None = None  # 最近一次响应头里的剩余积分；没见过是 None
        self._headers = {"Authorization": f"Bearer {key}"} if key else {}
        LOGGER.info("openalex_client keyed=%s", bool(key))

    def search(self, query: str, n: int) -> list[dict[str, Any]]:
        """关键词检索，按相关度取前 n 篇（扣 10）。"""
        return self._list({"search": query, "per-page": str(n)})

    def by_dois(self, dois: list[str]) -> list[dict[str, Any]]:
        """按 DOI 批量取；OpenAlex 没收录的 DOI 不在结果里（调用方按 DOI 对账）。"""
        return self._batched("doi", dois)

    def by_keys(self, keys: list[str]) -> list[dict[str, Any]]:
        return self._batched("openalex_id", keys)

    def by_arxiv(self, ids: list[str]) -> list[dict[str, Any]]:
        """按 arXiv 号批量取：查落地页。论文后来发了期刊的，主 DOI 是期刊的，按 arXiv 的 DOI 查是
        404（真跑丢过三篇种子）；落地页里存的多是 http 的，https 的也带上，不漏。"""
        return self._batched("locations.landing_page_url",
                             [f"{scheme}://arxiv.org/abs/{i}" for i in ids
                              for scheme in ("http", "https")])

    def by_pmids(self, pmids: list[str]) -> list[dict[str, Any]]:
        return self._batched("pmid", pmids)

    def citing(self, keys: list[str], pages: int) -> list[dict[str, Any]]:
        """引用了 keys 里任何一篇的论文，按被引数取前 pages 页（每页 200 篇、每页扣 1）。
        谁引用了谁由调用方按每篇的参考文献表对回去。"""
        works: list[dict[str, Any]] = []
        for start in range(0, len(keys), BATCH):
            cursor: str | None = "*"
            for _ in range(pages):
                if cursor is None:
                    break
                body = self._page({"filter": f"cites:{'|'.join(keys[start:start + BATCH])}",
                                   "sort": "cited_by_count:desc", "per-page": str(CITING_PAGE),
                                   "cursor": cursor})
                works += body["results"]
                cursor = body.get("meta", {}).get("next_cursor")
        return works

    @property
    def requests(self) -> int:
        return self.web.requests[urllib.parse.urlsplit(BASE_URL).netloc]

    def _batched(self, field: str, values: list[str]) -> list[dict[str, Any]]:
        works: list[dict[str, Any]] = []
        for start in range(0, len(values), BATCH):
            chunk = values[start:start + BATCH]
            works += self._list({"filter": f"{field}:{'|'.join(chunk)}", "per-page": str(BATCH)})
        return works

    def _list(self, params: dict[str, str]) -> list[dict[str, Any]]:
        return self._page(params)["results"]

    def _page(self, params: dict[str, str]) -> dict[str, Any]:
        url = f"{BASE_URL}?{urllib.parse.urlencode({**params, 'select': SELECT})}"
        body, headers = self.web.get(url, headers=self._headers, on_error=self._quota)
        self._note_remaining(headers)
        LOGGER.info("openalex_get remaining=%s url=%s", self.remaining, url)
        doc = json.loads(body)
        if not isinstance(doc.get("results"), list):
            raise OpenAlexError(f"OpenAlex 返回里没有 results 列表：{url}")
        return doc

    def _quota(self, err: urllib.error.HTTPError) -> None:
        self._note_remaining(dict(err.headers.items()) if err.headers else {})
        if err.code == 429 and self.remaining == 0:
            raise QuotaExhausted(
                "OpenAlex 今天的额度用完了（不配 key 每个 IP 每天 1000 积分，配了免费的 key 10000，"
                f"设环境变量 {KEY_ENV}），重置前没法再查：{err.url}") from err

    def _note_remaining(self, headers: dict[str, str]) -> None:
        value = {k.lower(): v for k, v in headers.items()}.get("x-ratelimit-remaining")
        if value is not None and value.strip().lstrip("-").isdigit():
            self.remaining = int(value)
