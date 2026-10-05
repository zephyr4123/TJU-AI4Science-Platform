"""文献精读的主流程：认上游 → 一篇一个会话并行读 → 核原句 → 写 sources.md（外层 #233）。

为什么一篇一个会话：#226 演练里研究助理面对 34 篇原文（约 246 万字符）只读了两篇的开头，一轮
塞不下；一篇一个会话，每篇都按需求读完、写成固定形状的笔记，助理之后只读笔记。
为什么每篇一个自己的目录（`notes/<n>/`，会话就在里面）：会话回来后按前后快照判它改了哪些文件，
几个会话同时在一个目录里写会互相误判成越界。
失败不阻塞：某篇会话超时、没写笔记、写了笔记之外的文件，只记这篇没读成；一篇都没读成才判失败。
"""

from __future__ import annotations

import logging
import math
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from functools import partial
from pathlib import Path

from backends import Runner, RunResult
from framework.capabilities.literature_read import quotes
from framework.capabilities.literature_read import sources as sources_mod
from framework.capabilities.literature_read.sources import Entry, Read
from framework.contracts import requirement
from framework.contracts.capability import CapabilityFailed, Inputs
from framework.executor import prompting, session
from framework.files import append_event, write_atomic
from framework.workspace import loadout

LOGGER = logging.getLogger("ai4sci.literature")

HERE = Path(__file__).resolve().parent
PROMPT = HERE / "prompt.md"
SOURCES_NAME = "sources.md"
NOTES_DIRNAME = "notes"
NOTE_NAME = "note.md"
LOG_DIRNAME = "executor"
# 原文放进提示最多这么多字符：#226 演练 34 篇中位 5.6 万、最长的综述 46 万；再长的只放前面，
# 提示里注明
TEXT_MAX = 100_000
SESSIONS = 4  # 同时几个会话
GIST_HEADING = "## 一句话"
# 边跑边追加的进度，页面的精读面板照它画（外层 #245）：开头一行列出要读的每篇与同时几个会话，
# 之后每篇开始读一行、读完或没读成一行
PROGRESS_NAME = "progress.jsonl"


def read_all(output_dir: Path, inputs: Inputs, runner: Runner, *, max_papers: int) -> str:
    output_dir = Path(output_dir).resolve()
    if max_papers < 0:
        raise CapabilityFailed(f"最多读几篇不能小于 0（0 是全读），得到 {max_papers}")
    upstream = inputs.one_of("literature", "文献精读")
    upstream_id = inputs.ids[inputs.outputs.index(upstream)]
    listing = upstream / SOURCES_NAME
    if not listing.is_file():
        raise CapabilityFailed(f"文献精读要上游文献产出的 {SOURCES_NAME}，{upstream_id} 里没有")
    entries = sources_mod.parse(listing.read_text(encoding="utf-8"), upstream)
    with_text = [e for e in entries if e.fulltext]
    if not with_text:
        raise CapabilityFailed(
            f"{upstream_id} 的 {SOURCES_NAME} 里没有一篇有原文（{len(entries)} 篇），没东西可读："
            "先拿到原文，或请研究者把下好的原文放进 materials/")
    chosen = with_text[:max_papers] if max_papers else with_text
    need = requirement.read(inputs.workspace).strip()
    progress = partial(append_event, output_dir / PROGRESS_NAME)
    progress(papers=[{"n": e.n, "title": e.title} for e in chosen], sessions=SESSIONS)
    with ThreadPoolExecutor(max_workers=SESSIONS, thread_name_prefix="read") as pool:
        reads = list(pool.map(lambda e: _read_one(output_dir, runner, need, e, progress), chosen))
    write_atomic(output_dir / SOURCES_NAME, sources_mod.render(
        title=requirement.title(need, "文献精读"), upstream_id=upstream_id, reads=reads,
        no_text=[e for e in entries if not e.fulltext], not_reached=with_text[len(chosen):]))
    done = [r for r in reads if r.note]
    if not done:
        raise CapabilityFailed(f"{len(reads)} 篇一篇都没读成：" + "；".join(
            f"{r.entry.n}. {r.why}" for r in reads[:5]))
    cost = sum(r.cost_usd for r in reads)
    total, found = sum(r.quotes for r in done), sum(r.found for r in done)
    LOGGER.info("read_done out=%s papers=%d notes=%d quotes=%d/%d", output_dir, len(reads),
                len(done), found, total)
    return (f"read ok\tpapers={len(reads)}\tnotes={len(done)}\tquotes={found}/{total}"
            f"\tcost_usd={'nan' if math.isnan(cost) else f'{cost:.4f}'}\tpath={SOURCES_NAME}")


def _read_one(output_dir: Path, runner: Runner, need: str, entry: Entry,
              progress: Callable[..., None]) -> Read:
    cwd = output_dir / NOTES_DIRNAME / entry.n
    cwd.mkdir(parents=True)
    note = cwd / NOTE_NAME
    assert entry.fulltext is not None
    text = entry.fulltext.read_text(encoding="utf-8")
    length = (f"原文 {len(text)} 个字符，全文都在下面。" if len(text) <= TEXT_MAX else
              f"原文 {len(text)} 个字符，太长，下面只有前 {TEXT_MAX} 个字符。")
    prompt = prompting.build_prompt(
        PROMPT, {"requirement": need, "title": entry.title, "note": str(note), "length": length,
                 "text": text[:TEXT_MAX]},
        loadout=loadout.around(output_dir))
    progress(paper=entry.n, state="reading")
    result = session.run_session(runner, prompt, cwd=cwd, allowed_paths=[cwd],
                                 log_dir=output_dir / LOG_DIRNAME / entry.n)
    why = _problem(result, note)
    if why:
        LOGGER.warning("read_failed n=%s why=%s", entry.n, why)
        progress(paper=entry.n, state="failed", why=why)
        return Read(entry, why=why, cost_usd=result.cost_usd)
    body = note.read_text(encoding="utf-8")
    said = quotes.quoted(body)
    found = sum(quotes.found(q, text) for q in said)
    LOGGER.info("read_ok n=%s quotes=%d/%d", entry.n, found, len(said))
    progress(paper=entry.n, state="done", quotes=len(said), found=found)
    return Read(entry, note=f"{NOTES_DIRNAME}/{entry.n}/{NOTE_NAME}", gist=_gist(body),
                quotes=len(said), found=found, cost_usd=result.cost_usd)


def _problem(result: RunResult, note: Path) -> str:
    """这篇没读成的原因；读成了是空串。先判越界，再判会话死没死，最后判笔记在不在。"""
    outside = sorted(f for f in result.changed_files if f != NOTE_NAME)
    if outside:
        return f"会话改了笔记之外的文件：{', '.join(outside)}"
    if result.timed_out or result.exit_code != 0:
        return "会话超时" if result.timed_out else f"会话没走完（退出码 {result.exit_code}）"
    if not note.is_file():
        return "没有写出笔记"
    return ""


def _gist(body: str) -> str:
    """笔记里「一句话」那一节，压成一行。"""
    _, found, rest = body.partition(GIST_HEADING)
    if not found:
        return ""
    return " ".join(rest.split("\n## ", 1)[0].split())
