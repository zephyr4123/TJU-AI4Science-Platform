"""文献检索对外的 HTTP：一个 GET、读到结尾、重试、按站点限速。四家接口（OpenAlex、Crossref、arXiv、
Europe PMC）共用这一份，各家只管拼 URL 与解析。

- 读到结尾：一次 `read` 拿不全是常态，连接中途断了它也不报错（外层 #212 真跑，pdf skill 就这样把两篇
  PDF 截在 1 MiB 与 8 MiB）；比 Content-Length 短按失败重试。
- 重试：429、5xx、断网、读不全，退避 1 / 2 / 4 秒，`Retry-After` 优先；调用方可以先看一眼错误
  （OpenAlex 据响应头判额度用完，用完就不重试），也可以给自己的退避表（arXiv 被限速时要等得更久）。
- 限速：同一站点两次请求之间至少隔多久由调用方给（arXiv 要求 3 秒）；同一站点一律串行，不并发
  （Crossref、PubMed 实测并发就 429）。不同站点可以同时查（`gather` 三家各一个线程，外层 #228）：
  按站点记的状态（上次请求的时刻、成功几次）每个站点只有一个线程在写，不用锁。
- 如实报身份：伪装浏览器的 UA 有的站直接 403（Zenodo 实测）。标准库 urllib：不为几个 GET 加库。
"""

from __future__ import annotations

import logging
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
from collections.abc import Callable

LOGGER = logging.getLogger("ai4sci.literature")

USER_AGENT = "ai4sci (+https://github.com/zephyr4123/TJU-AI4Science)"
TIMEOUT_S = 30
BACKOFF_S = (1.0, 2.0, 4.0)
RETRY_AFTER_MAX_S = 30.0
RETRIED_STATUS = frozenset({429, 500, 502, 503, 504})
READ_CHUNK = 1 << 20

# 拿 URL 与额外的请求头发 GET，返回（正文, 小写键的响应头）；测试换成查表的假函数，不连网
Get = Callable[[str, dict[str, str]], tuple[bytes, dict[str, str]]]


class FetchError(RuntimeError):
    """请求失败且重试用完。信息里带 URL 与原因。"""


class ShortRead(OSError):
    """收到的比 Content-Length 短：连接中途断了。按网络错误重试。"""


def http_get(url: str, headers: dict[str, str]) -> tuple[bytes, dict[str, str]]:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, **headers})
    with urllib.request.urlopen(request, timeout=TIMEOUT_S) as response:
        got = {k.lower(): v for k, v in response.headers.items()}
        chunks = []
        while chunk := response.read(READ_CHUNK):
            chunks.append(chunk)
    body = b"".join(chunks)
    declared = got.get("content-length", "")
    if declared.isdigit() and len(body) < int(declared):
        raise ShortRead(f"只收到 {len(body)} / {declared} 字节")
    return body, got


class Web:
    def __init__(self, get: Get = http_get, sleep: Callable[[float], None] = time.sleep,
                 clock: Callable[[], float] = time.monotonic) -> None:
        self._get = get
        self._sleep = sleep
        self._clock = clock
        self._last: dict[str, float] = {}
        self.requests: Counter[str] = Counter()  # 每个站点成功了几次，收尾记日志

    def get(self, url: str, *, spacing_s: float = 0.0, headers: dict[str, str] | None = None,
            on_error: Callable[[urllib.error.HTTPError], None] | None = None,
            backoff_s: tuple[float, ...] = BACKOFF_S) -> tuple[bytes, dict[str, str]]:
        """请求头里放凭据（OpenAlex 的 key），不拼进 URL：URL 要进日志。"""
        host = urllib.parse.urlsplit(url).netloc
        for attempt, backoff in enumerate((*backoff_s, None), start=1):
            self._space(host, spacing_s)
            try:
                body, got = self._get(url, headers or {})
            except urllib.error.HTTPError as err:
                if on_error is not None:
                    on_error(err)  # 调用方要停（额度用完）就在这里抛
                if err.code not in RETRIED_STATUS or backoff is None:
                    raise FetchError(f"{host} 返回 {err.code}（第 {attempt} 次）：{url}") from err
                wait = _retry_after(err.headers, backoff)
                LOGGER.warning("web_retry status=%d attempt=%d wait_s=%.1f url=%s", err.code,
                               attempt, wait, url)
            except (urllib.error.URLError, TimeoutError, OSError) as err:
                if backoff is None:
                    raise FetchError(f"连不上 {host}（第 {attempt} 次）：{err}；{url}") from err
                wait = backoff
                LOGGER.warning("web_retry error=%s attempt=%d wait_s=%.1f url=%s", err, attempt,
                               wait, url)
            else:
                self.requests[host] += 1
                return body, got
            self._sleep(wait)
        raise AssertionError("重试循环不会走到这里")  # 最后一次失败在循环里已经抛了

    def _space(self, host: str, spacing_s: float) -> None:
        last = self._last.get(host)
        if last is not None and spacing_s > 0:
            wait = last + spacing_s - self._clock()
            if wait > 0:
                self._sleep(wait)
        self._last[host] = self._clock()


def _retry_after(headers, fallback: float) -> float:
    value = headers.get("Retry-After") if headers is not None else None
    try:
        return min(float(value), RETRY_AFTER_MAX_S) if value is not None else fallback
    except ValueError:
        return fallback  # HTTP 日期格式的 Retry-After 不解析，按退避表等
