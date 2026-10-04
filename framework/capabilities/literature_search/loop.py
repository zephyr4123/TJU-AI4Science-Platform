"""文献检索的主流程：种子 → 第 0 跳 → 一跳一跳顺着引用扩 → 原文 → sources.md。

分工（外层 #212）：执行层只做两件模型才做得好的事——写检索词与纳入标准、用自带搜索找种子
（一次会话），看摘要判相关不相关（每跳一次会话）；查 OpenAlex、去重、排序、上限、停不停、
下原文、写清单都在这里，零模型。所以换哪家 agent 都一样跑，没有联网搜索的 agent 只是少了
种子这一路。

什么时候停：第 0 跳一篇没收；某一跳新收录的少于停止下限（扩不出新东西了）；到了最多跳数；
没有可筛的候选。只从新收录的论文往外扩，每跳只把关联最多的前 K 篇交给模型——一篇论文就可能有
几百篇引用它，全交给模型筛既贵又没必要。
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from pathlib import Path

from backends import Runner, RunResult
from framework.capabilities.literature_search import fulltext as fulltext_mod
from framework.capabilities.literature_search import report
from framework.capabilities.literature_search.exchange import (
    SEEDS_NAME,
    Seeds,
    parse_decisions,
    parse_seeds,
)
from framework.capabilities.literature_search.fulltext import Fetch, Fulltext
from framework.capabilities.literature_search.openalex import OpenAlex, OpenAlexError
from framework.capabilities.literature_search.papers import Paper, dois_in, from_openalex
from framework.capabilities.literature_search.pool import INCLUDE, Entry, Pool
from framework.contracts import requirement
from framework.contracts.capability import CapabilityFailed, Inputs
from framework.executor import prompting, session
from framework.files import write_atomic
from framework.workspace import loadout

LOGGER = logging.getLogger("ai4sci.literature")

HERE = Path(__file__).resolve().parent
SEED_PROMPT = HERE / "seed.md"
SCREEN_PROMPT = HERE / "screen.md"
SOURCES_NAME = "sources.md"
CANDIDATES_NAME = "candidates.jsonl"
ROUNDS_DIRNAME = "rounds"
LISTING_NAME = "candidates.md"
DECISIONS_NAME = "decisions.md"
LOG_DIRNAME = "executor"

MAX_QUERIES = 5       # 关键词检索一次扣 10 积分（每天 1000），一次检索最多花 50
QUERY_RESULTS = 10    # 每条检索词取前几篇
MAX_SEEDS = 20
CITING_N = 25         # 每篇新收录的取多少篇引用它的（按被引数）
FETCH_CAP = 1000      # 一跳最多给多少条线索取元数据：50 篇一批，扣 1 积分
ABSTRACT_MAX = 1500   # 给模型筛的摘要截到这么长：够判相关，不让一跳的提示无限长


@dataclass(frozen=True)
class Limits:
    max_hops: int
    per_hop: int
    min_new: int


def search(output_dir: Path, inputs: Inputs, runner: Runner, limits: Limits, *, fulltext: bool,
           client: OpenAlex | None = None, fetch: Fetch = fulltext_mod.fetch,
           excluded: frozenset[str] = frozenset()) -> str:
    """跑完整个检索，写 sources.md，返回一行结论。`client` / `fetch` 给测试换成不连网的；
    `excluded` 给召回实测挡住当标准答案的那篇综述。"""
    output_dir = Path(output_dir).resolve()
    _check_limits(limits)
    need = requirement.read(inputs.workspace).strip()
    client = client or OpenAlex()
    costs: list[float] = []
    seeds = _seed_session(output_dir, runner, need, costs)
    pool = Pool(excluded)
    try:
        unresolved = _hop_zero(pool, client, seeds)
        hop, stop = _hops(output_dir, runner, need, seeds, pool, client, limits, costs)
    except OpenAlexError as err:
        pool.save(output_dir / CANDIDATES_NAME)
        raise CapabilityFailed(f"查 OpenAlex 失败，检索停在半路：{err}") from err
    texts = _fulltexts(output_dir, pool, fetch) if fulltext else {}
    write_atomic(output_dir / SOURCES_NAME, report.render(
        title=requirement.title(need, "文献检索"), seeds=seeds, pool=pool, stop=stop,
        texts=texts, fulltext=fulltext, unresolved=unresolved))
    included = pool.included()
    got = sum(1 for t in texts.values() if t.path)
    cost = sum(costs)
    LOGGER.info("literature_done out=%s screened=%d included=%d hops=%d fulltext=%d "
                "openalex_requests=%d remaining=%s", output_dir, len(pool.entries), len(included),
                hop, got, client.requests, client.remaining)
    return (f"literature ok\tincluded={len(included)}\tscreened={len(pool.entries)}\thops={hop}"
            f"\tfulltext={got}\tcost_usd={'nan' if math.isnan(cost) else f'{cost:.4f}'}"
            f"\tpath={SOURCES_NAME}")


def _check_limits(limits: Limits) -> None:
    if limits.max_hops < 0 or limits.per_hop < 1 or limits.min_new < 1:
        raise CapabilityFailed(
            f"参数不对：最多跳数不能小于 0，每跳筛选数与停止下限至少 1，得到 {limits}")


# ── 种子与第 0 跳 ─────────────────────────────────────────────────────────
def _seed_session(output_dir: Path, runner: Runner, need: str, costs: list[float]) -> Seeds:
    prompt = prompting.build_prompt(
        SEED_PROMPT, {"requirement": need, "max_queries": MAX_QUERIES, "max_seeds": MAX_SEEDS},
        loadout=loadout.around(output_dir))
    result = session.run_session(runner, prompt, cwd=output_dir, allowed_paths=[output_dir],
                                 log_dir=output_dir / LOG_DIRNAME / "seeds")
    costs.append(result.cost_usd)
    _check_outcome(result, SEEDS_NAME)
    seeds, problems = parse_seeds(_read(output_dir / SEEDS_NAME))
    if seeds is None:
        raise CapabilityFailed(f"{SEEDS_NAME} 不合形状：" + "；".join(problems))
    return seeds


def _hop_zero(pool: Pool, client: OpenAlex, seeds: Seeds) -> list[str]:
    """种子按 DOI 一次批量取，检索词一条一条查；返回认不出编号、或 OpenAlex 里查不到的种子行。"""
    lines = list(seeds.seeds[:MAX_SEEDS])
    wanted = {line: dois_in(line) for line in lines}
    works = client.by_dois(sorted({d for dois in wanted.values() for d in dois}))
    by_doi = {p.doi: p for p in map(from_openalex, works) if p.doi}
    unresolved: list[str] = []
    for line, dois in wanted.items():
        hits = [by_doi[d] for d in dois if d in by_doi]
        unresolved += [] if hits else [line]
        for paper in hits:
            pool.admit(paper, 0, "seed")
    for query in seeds.queries[:MAX_QUERIES]:
        for work in client.search(query, QUERY_RESULTS):
            pool.admit(from_openalex(work), 0, f"query:{query}")
    LOGGER.info("hop_zero seeds=%d unresolved=%d queries=%d candidates=%d", len(lines),
                len(unresolved), min(len(seeds.queries), MAX_QUERIES), len(pool.entries))
    return unresolved


# ── 一跳一跳 ──────────────────────────────────────────────────────────────
def _hops(output_dir: Path, runner: Runner, need: str, seeds: Seeds, pool: Pool,
          client: OpenAlex, limits: Limits, costs: list[float]) -> tuple[int, str]:
    """筛第 0 跳，然后扩一跳筛一跳，直到停；返回（停在第几跳, 为什么停）。"""
    asked: set[str] = set()  # 取过元数据的线索：OpenAlex 没返回的（合并、删掉的）不再问
    hop = 0
    while True:
        batch = pool.of_hop(hop)
        if not batch:
            return hop, "没有可筛的候选了" if hop else "检索词与种子一篇论文都没查到"
        _screen(output_dir, runner, need, seeds.criteria, pool, hop, costs)
        pool.save(output_dir / CANDIDATES_NAME)
        new = [e.paper for e in batch if e.verdict == INCLUDE]
        LOGGER.info("hop_done hop=%d screened=%d included=%d remaining=%s", hop, len(batch),
                    len(new), client.remaining)
        if hop == 0 and not new:
            return hop, "第 0 跳一篇都没收：检索词与种子没找到相关的"
        if hop > 0 and len(new) < limits.min_new:
            return hop, f"第 {hop} 跳新收录 {len(new)} 篇，少于停止下限 {limits.min_new}"
        if hop == limits.max_hops:
            return hop, f"到了最多跳数 {limits.max_hops}"
        hop += 1
        _expand(pool, client, new, hop, limits.per_hop, asked)


def _expand(pool: Pool, client: OpenAlex, frontier: list[Paper], hop: int, per_hop: int,
            asked: set[str]) -> None:
    for paper in frontier:
        pool.note_refs(paper)
        pool.note_citing(paper.key, [from_openalex(w) for w in client.citing(paper.key, CITING_N)])
    missing = [k for k in pool.open_leads() if k not in pool.cache and k not in asked][:FETCH_CAP]
    asked.update(missing)
    for work in client.by_keys(missing):
        found = from_openalex(work)
        pool.cache[found.key] = found
    for paper in pool.next_batch(per_hop):
        for mark in pool.found_of(paper.key):
            pool.admit(paper, hop, mark)
    LOGGER.info("expand hop=%d frontier=%d fetched=%d admitted=%d leads_left=%d", hop,
                len(frontier), len(missing), len(pool.of_hop(hop)), len(pool.open_leads()))


def _screen(output_dir: Path, runner: Runner, need: str, criteria: str, pool: Pool, hop: int,
            costs: list[float]) -> None:
    entries = pool.of_hop(hop)
    round_dir = output_dir / ROUNDS_DIRNAME / str(hop)
    round_dir.mkdir(parents=True, exist_ok=True)
    listing = "\n\n".join(_listing(entry, pool) for entry in entries)
    (round_dir / LISTING_NAME).write_text(listing + "\n", encoding="utf-8")
    decisions = f"{ROUNDS_DIRNAME}/{hop}/{DECISIONS_NAME}"
    prompt = prompting.build_prompt(
        SCREEN_PROMPT, {"hop": hop, "count": len(entries), "requirement": need,
                        "criteria": criteria, "candidates": listing, "decisions": decisions},
        loadout=loadout.around(output_dir))
    result = session.run_session(runner, prompt, cwd=output_dir, allowed_paths=[output_dir],
                                 log_dir=output_dir / LOG_DIRNAME / f"hop-{hop}")
    costs.append(result.cost_usd)
    _check_outcome(result, decisions)
    decided, problems = parse_decisions(_read(output_dir / decisions),
                                        [e.paper.key for e in entries])
    if problems:
        raise CapabilityFailed(f"{decisions} 不合形状：" + "；".join(problems[:8]))
    for key, (verdict, reason) in decided.items():
        pool.decide(key, verdict, reason)


def _listing(entry: Entry, pool: Pool) -> str:
    paper = entry.paper
    facts = " · ".join(x for x in (str(paper.year or "年份不详"), paper.venue,
                                   f"被引 {paper.cited_by}") if x)
    abstract = paper.abstract[:ABSTRACT_MAX] + ("…" if len(paper.abstract) > ABSTRACT_MAX else "")
    return "\n".join([
        f"### {paper.key}",
        f"- 题目：{paper.title or '（没有题目）'}",
        f"- 年份 · 出处 · 被引：{facts}",
        f"- 怎么找到的：{'；'.join(pool.describe(m) for m in entry.found)}",
        f"- 摘要：{abstract or '（OpenAlex 没有摘要）'}",
    ])


def _fulltexts(output_dir: Path, pool: Pool, fetch: Fetch) -> dict[str, Fulltext]:
    return {e.paper.key: fetch(e.paper, output_dir) for e in pool.included()}


# ── 会话的事后判定 ────────────────────────────────────────────────────────
def _check_outcome(result: RunResult, allowed: str) -> None:
    """先判越界（只许写 allowed 那一个文件），再判会话死没死。文件留着当证据。"""
    outside = [f for f in result.changed_files
               if f != allowed and not f.startswith(f"{LOG_DIRNAME}/")]
    if outside:
        raise CapabilityFailed(f"执行层改了 {allowed} 之外的文件：{', '.join(sorted(outside))}")
    if result.timed_out or result.exit_code != 0:
        tail = result.stdout_tail.strip().splitlines()
        why = "超时" if result.timed_out else f"退出码 {result.exit_code}"
        raise CapabilityFailed(f"执行层会话没走完（{why}）：{tail[-1] if tail else '无输出'}")


def _read(path: Path) -> str:
    if not path.is_file():
        raise CapabilityFailed(f"执行层没有写出 {path.name}")
    return path.read_text(encoding="utf-8")
