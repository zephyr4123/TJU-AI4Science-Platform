"""收录的论文拿原文：有开放获取的 PDF 就交给平台自带的 pdf skill 下载并解析，落在 `papers/<W号>/`。

拿不到不算这一步失败：付费的、链接其实是落地页的（pdf 退出码 3）、超时的，一篇记一条
原因，`sources.md` 列成「没拿到原文」，请研究者自己下好放进 `materials/`。串行一篇一篇来：
出版社对并发更凶。
"""

from __future__ import annotations

import json
import logging
import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from framework import skills
from framework.capabilities.literature_search.papers import Paper
from framework.skills.run import capture_script, pick_script

LOGGER = logging.getLogger("ai4sci.literature")
PAPERS_DIRNAME = "papers"
PDF_SKILL = "pdf"
TIMEOUT_S = 180.0  # 一篇：下载加解析。二十页的论文解析两秒，余下都是给慢的出版社


@dataclass(frozen=True)
class Fulltext:
    path: str | None    # 相对产出目录的 paper.md；没拿到是 None
    pages: int | None
    why: str = ""       # 没拿到的原因


Fetch = Callable[[Paper, Path], Fulltext]


def fetch(paper: Paper, output_dir: Path) -> Fulltext:
    """先试开放获取的 PDF，不成且有 arXiv 版本再试 arXiv 的：出版社常拦程序下载（403、人机验证），
    arXiv 不拦（外层 #212 真跑：IOP 返回人机验证页的那篇有 arXiv 版本）。"""
    links = list(dict.fromkeys(u for u in (
        paper.pdf_url, f"https://arxiv.org/pdf/{paper.arxiv}" if paper.arxiv else None) if u))
    if not links:
        return Fulltext(None, None, "没有开放获取的 PDF")
    target = Path(PAPERS_DIRNAME) / paper.key
    script = pick_script(skills.find(PDF_SKILL), None)
    for url in links:
        got = _one(script, paper.key, url, output_dir, target)
        if got.path:
            return got
    return got  # 每个链接都没成：报最后一个的原因


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
