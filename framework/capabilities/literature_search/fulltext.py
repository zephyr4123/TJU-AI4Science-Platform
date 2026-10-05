"""收录的论文拿原文：有开放获取的 PDF 就交给平台自带的 pdf skill 下载并解析，落在 `papers/<W号>/`。

拿不到不算这一步失败：付费的、链接其实是落地页的（pdf 退出码 3）、超时的，一篇记一条
原因，`sources.md` 列成「没拿到原文」，请研究者自己下好放进 `materials/`。

并行（外层 #229）：原来逐篇串行，一篇慢的拖住后面全部（#226 演练 38 篇 5 分钟，中位一篇 4 秒、最长
79 秒）。现在同时下 `WORKERS` 篇，但同一站点同时不超过 `PER_HOST` 篇：出版社对并发更凶，arXiv 也要求
别猛下。提交顺序按站点轮着排，免得排在前面的一大串 arXiv 把线程全占着等名额、别的站点干等。
"""

from __future__ import annotations

import json
import logging
import subprocess
import threading
import urllib.parse
from collections.abc import Callable, Iterator
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from dataclasses import dataclass
from itertools import chain, zip_longest
from pathlib import Path

from framework import skills
from framework.capabilities.literature_search.papers import Paper
from framework.skills.run import capture_script, pick_script

LOGGER = logging.getLogger("ai4sci.literature")
PAPERS_DIRNAME = "papers"
PDF_SKILL = "pdf"
TIMEOUT_S = 180.0  # 一篇：下载加解析。二十页的论文解析两秒，余下都是给慢的出版社
# 同时下几篇、同一站点同时几篇：#226 演练收录的 39 篇有链接（arxiv.org 23 篇）实测，串行 298 秒；
# 4/2 70 秒、8/2 58 秒、8/4 51 秒，成功都是 35 篇。8/2 之后省得越来越少，同站点再加只是让 arXiv
# 与出版社多吃一倍并发（失败的本来就是出版社的 403），取 8/2
WORKERS = 8
PER_HOST = 2


@dataclass(frozen=True)
class Fulltext:
    path: str | None    # 相对产出目录的 paper.md；没拿到是 None
    pages: int | None
    why: str = ""       # 没拿到的原因


class HostSlots:
    """每个站点一个计数锁：同一站点同时不超过 per_host 个下载，不同站点之间不等。"""

    def __init__(self, per_host: int) -> None:
        self._per_host = per_host
        self._slots: dict[str, threading.Semaphore] = {}
        self._guard = threading.Lock()

    @contextmanager
    def hold(self, url: str) -> Iterator[None]:
        host = _host(url)
        with self._guard:
            slot = self._slots.setdefault(host, threading.Semaphore(self._per_host))
        with slot:
            yield


Fetch = Callable[[Paper, Path, HostSlots], Fulltext]


def fetch_all(papers: list[Paper], output_dir: Path, fetch_one: Fetch | None = None, *,
              workers: int = WORKERS, per_host: int = PER_HOST) -> dict[str, Fulltext]:
    """收录的论文一起下，结果按传进来的顺序回来。`fetch_one` 给测试换成不连网的。"""
    fetch_one = fetch_one or fetch
    slots = HostSlots(per_host)
    by_host: dict[str, list[Paper]] = {}
    for paper in papers:
        links = _links(paper)
        by_host.setdefault(_host(links[0]) if links else "", []).append(paper)
    order = [p for p in chain.from_iterable(zip_longest(*by_host.values())) if p is not None]
    with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="fulltext") as pool:
        futures = {p.key: pool.submit(fetch_one, p, output_dir, slots) for p in order}
    return {p.key: futures[p.key].result() for p in papers}


def fetch(paper: Paper, output_dir: Path, slots: HostSlots) -> Fulltext:
    """先试开放获取的 PDF，不成且有 arXiv 版本再试 arXiv 的：出版社常拦程序下载（403、人机验证），
    arXiv 不拦（外层 #212 真跑：IOP 返回人机验证页的那篇有 arXiv 版本）。"""
    links = _links(paper)
    if not links:
        return Fulltext(None, None, "没有开放获取的 PDF")
    target = Path(PAPERS_DIRNAME) / paper.key
    script = pick_script(skills.find(PDF_SKILL), None)
    for url in links:
        with slots.hold(url):
            got = _one(script, paper.key, url, output_dir, target)
        if got.path:
            return got
    return got  # 每个链接都没成：报最后一个的原因


def _links(paper: Paper) -> list[str]:
    return list(dict.fromkeys(u for u in (
        paper.pdf_url, f"https://arxiv.org/pdf/{paper.arxiv}" if paper.arxiv else None) if u))


def _host(url: str) -> str:
    return urllib.parse.urlsplit(url).netloc


def _one(script: Path, key: str, url: str, output_dir: Path, target: Path) -> Fulltext:
    """下一个链接并解析；没成的 Fulltext 带原因。"""
    try:
        proc = capture_script(script, ["--input", url, "--out", str(output_dir / target)],
                              TIMEOUT_S)
    except subprocess.TimeoutExpired:
        LOGGER.warning("fulltext_timeout key=%s url=%s", key, url)
        return Fulltext(None, None, f"下载与解析超过 {TIMEOUT_S:.0f} 秒")
    if proc.returncode != 0:
        last = (proc.stderr.strip().splitlines() or ["无输出"])[-1][:200]
        LOGGER.warning("fulltext_failed key=%s code=%d url=%s why=%s", key, proc.returncode, url,
                       last)
        return Fulltext(None, None, f"{last}（退出码 {proc.returncode}）")
    try:
        summary = json.loads(proc.stdout.strip().splitlines()[-1])
    except (IndexError, json.JSONDecodeError):
        LOGGER.error("fulltext_bad_stdout key=%s stdout=%r", key, proc.stdout[-300:])
        return Fulltext(None, None, "pdf 的输出不是一行 JSON（skill 的契约坏了，见日志）")
    LOGGER.info("fulltext_ok key=%s pages=%s url=%s", key, summary.get("pages"), url)
    return Fulltext((target / "paper.md").as_posix(), summary.get("pages"))
