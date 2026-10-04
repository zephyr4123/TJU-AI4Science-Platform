"""OpenAlex 的客户端：文献检索唯一的学术接口（外层 #212）。

为什么只接这一家：不配 key 的几家 2026-10-04 实测过，Semantic Scholar 单次请求也 429、
CORE 时好时坏、Google Scholar 是爬网页；OpenAlex 全学科、不要 key，参考文献表与「谁引用了它」
都有，arXiv 预印本也收（DOI `10.48550/arxiv.<号>`），多跳只靠它就够。

额度：不配 key 每个 IP 每天 1000 积分。关键词检索一次扣 10，filter 列表（按 DOI / W 号批量取、
`cites:`）一次扣 1，按 id 取单篇扣 0。响应头 `x-ratelimit-remaining` 每次记日志；额度用完抛
`QuotaExhausted`，不静默少查。串行、一次一个请求：429（每秒限流）、5xx、断网重试，
退避 1 / 2 / 4 秒，`Retry-After` 优先。标准库 urllib：框架的运行时依赖不为几个 GET 加一个库。
"""

from __future__ import annotations

import json
import logging
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from typing import Any

LOGGER = logging.getLogger("ai4sci.literature")

BASE_URL = "https://api.openalex.org/works"
# 如实报身份：伪装浏览器的 UA 有的站直接 403（Zenodo 实测）
USER_AGENT = "ai4sci (+https://github.com/zephyr4123/TJU-AI4Science)"
SELECT = ("id,doi,display_name,publication_year,authorships,primary_location,locations,"
          "cited_by_count,abstract_inverted_index,referenced_works,best_oa_location")
BATCH = 50          # filter 里一次 OR 的个数：OpenAlex 上限 100，留一半余量给 URL 长度
TIMEOUT_S = 30
BACKOFF_S = (1.0, 2.0, 4.0)
RETRY_AFTER_MAX_S = 30.0
RETRIED_STATUS = frozenset({429, 500, 502, 503, 504})

# 拿 URL 发 GET，返回（JSON 正文, 响应头）；测试换成查表的假函数，不连网
Get = Callable[[str], tuple[dict[str, Any], dict[str, str]]]


class OpenAlexError(RuntimeError):
    """请求失败且重试用完，或返回的不是预期的形状。信息里带 URL 与原因。"""


class QuotaExhausted(OpenAlexError):
    """今天的额度用完了：不配 key 每个 IP 每天 1000 积分，到点重置。"""


def http_get(url: str) -> tuple[dict[str, Any], dict[str, str]]:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=TIMEOUT_S) as response:
        headers = {k.lower(): v for k, v in response.headers.items()}
        return json.loads(response.read().decode("utf-8")), headers


class OpenAlex:
    def __init__(self, get: Get = http_get, sleep: Callable[[float], None] = time.sleep) -> None:
        self._get = get
        self._sleep = sleep
        self.requests = 0
        self.remaining: int | None = None  # 最近一次响应头里的剩余积分；没见过是 None

    def search(self, query: str, n: int) -> list[dict[str, Any]]:
        """关键词检索，按相关度取前 n 篇（扣 10）。"""
        return self._list({"search": query, "per-page": str(n)})

    def by_dois(self, dois: list[str]) -> list[dict[str, Any]]:
        """按 DOI 批量取；OpenAlex 没收录的 DOI 不在结果里（调用方按 DOI 对账）。"""
        return self._batched("doi", dois)

    def by_keys(self, keys: list[str]) -> list[dict[str, Any]]:
        return self._batched("openalex_id", keys)

    def by_arxiv(self, ids: list[str]) -> list[dict[str, Any]]:
        """按 arXiv 号批量取：查落地页。OpenAlex 里存的多是 http 的，https 的也带上，不漏。"""
        return self._batched("locations.landing_page_url",
                             [f"{scheme}://arxiv.org/abs/{i}" for i in ids
                              for scheme in ("http", "https")])

    def citing(self, key: str, n: int) -> list[dict[str, Any]]:
        """引用了 key 的论文，按被引数取前 n 篇（扣 1）。"""
        return self._list({"filter": f"cites:{key}", "sort": "cited_by_count:desc",
                           "per-page": str(n)})

    def _batched(self, field: str, values: list[str]) -> list[dict[str, Any]]:
        works: list[dict[str, Any]] = []
        for start in range(0, len(values), BATCH):
            chunk = values[start:start + BATCH]
            works += self._list({"filter": f"{field}:{'|'.join(chunk)}", "per-page": str(BATCH)})
        return works

    def _list(self, params: dict[str, str]) -> list[dict[str, Any]]:
        url = f"{BASE_URL}?{urllib.parse.urlencode({**params, 'select': SELECT})}"
        body = self._request(url)
        results = body.get("results")
        if not isinstance(results, list):
            raise OpenAlexError(f"OpenAlex 返回里没有 results 列表：{url}")
        return results

    def _request(self, url: str) -> dict[str, Any]:
        for attempt, backoff in enumerate((*BACKOFF_S, None), start=1):
            try:
                body, headers = self._get(url)
            except urllib.error.HTTPError as err:
                retry_after = _retry_after(err.headers)
                self._note_remaining(dict(err.headers.items()) if err.headers else {})
                if err.code == 429 and self.remaining == 0:
                    raise QuotaExhausted(
                        "OpenAlex 今天的额度用完了（不配 key 每个 IP 每天 1000 积分，"
                        f"一次关键词检索扣 10），重置前没法再查：{url}") from err
                if err.code not in RETRIED_STATUS or backoff is None:
                    raise OpenAlexError(
                        f"OpenAlex 返回 {err.code}（第 {attempt} 次）：{url}") from err
                wait = backoff if retry_after is None else min(retry_after, RETRY_AFTER_MAX_S)
                LOGGER.warning("openalex_retry status=%d attempt=%d wait_s=%.1f url=%s",
                               err.code, attempt, wait, url)
            except (urllib.error.URLError, TimeoutError) as err:
                if backoff is None:
                    raise OpenAlexError(
                        f"连不上 OpenAlex（第 {attempt} 次）：{err}；{url}") from err
                wait = backoff
                LOGGER.warning("openalex_retry error=%s attempt=%d wait_s=%.1f url=%s",
                               err, attempt, wait, url)
            else:
                self.requests += 1
                self._note_remaining(headers)
                LOGGER.info("openalex_get remaining=%s url=%s", self.remaining, url)
                return body
            self._sleep(wait)
        raise AssertionError("重试循环不会走到这里")  # 最后一次失败在循环里已经抛了

    def _note_remaining(self, headers: dict[str, str]) -> None:
        value = {k.lower(): v for k, v in headers.items()}.get("x-ratelimit-remaining")
        if value is not None and value.strip().lstrip("-").isdigit():
            self.remaining = int(value)


def _retry_after(headers: Any) -> float | None:
    value = headers.get("Retry-After") if headers is not None else None
    try:
        return float(value) if value is not None else None
    except ValueError:
        return None  # HTTP 日期格式的 Retry-After 不解析，按退避表等
