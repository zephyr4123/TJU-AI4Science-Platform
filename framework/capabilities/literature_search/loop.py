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

import datetime
import logging
import math
from collections import Counter
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
from framework.capabilities.literature_search.gather import MAX_QUERIES, MAX_SEEDS, gather
from framework.capabilities.literature_search.openalex import OpenAlex, OpenAlexError
from framework.capabilities.literature_search.openalex import api_key as openalex_key
from framework.capabilities.literature_search.papers import Paper, from_openalex
from framework.capabilities.literature_search.pool import INCLUDE, Entry, Pool
from framework.capabilities.literature_search.web import FetchError
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
REST_SUFFIX = "-rest"  # 补筛那次的清单与结论：candidates-rest.md、decisions-rest.md
LOG_DIRNAME = "executor"

CITING_PAGES = 2      # 「谁引用了它」：一跳的新收录合成一次查询，按被引数取前几页（每页 200）
FETCH_CAP = 1000      # 一跳最多给多少条线索取元数据：50 篇一批，扣 1 积分
# 给模型筛的摘要截到这么长。钱跟读进去的字数走：从 1500 降到 500、来路只数个数，清单砍掉六成、
# 筛选省三分之一，判得和原来一样准（外层 #219 的重放实验）
ABSTRACT_MAX = 500


@dataclass(frozen=True)
class Limits:
    max_hops: int
    per_hop: int
    min_new: int


def search(output_dir: Path, inputs: Inputs, runner: Runner, limits: Limits, *, fulltext: bool,
           since: int = 0, client: OpenAlex | None = None, fetch: Fetch = fulltext_mod.fetch,
           excluded: frozenset[str] = frozenset()) -> str:
    """跑完整个检索，写 sources.md，返回一行结论。`since` 是起始年份，0 不限（外层 #227）。
    `client` / `fetch` 给测试换成不连网的（四家接口共用 `client.web`）；`excluded` 给召回实测挡住
    当标准答案的那篇综述。第 0 跳取每跳筛选数的两倍：它要铺开题目的各个侧面。"""
    output_dir = Path(output_dir).resolve()
    _check_limits(limits)
    _check_since(since)
    need = requirement.read(inputs.workspace).strip()
    client = client or OpenAlex(key=openalex_key())
    costs: list[float] = []
    seeds = _seed_session(output_dir, runner, need, since, costs)
    pool = Pool(excluded, seeds.queries[:MAX_QUERIES], since)
    try:
        gathered = gather(pool, client, seeds, 2 * limits.per_hop)
        hop, stop = _hops(output_dir, runner, need, seeds, pool, client, limits, costs)
    except (OpenAlexError, FetchError) as err:
        pool.save(output_dir / CANDIDATES_NAME)
        raise CapabilityFailed(f"查 OpenAlex 失败，检索停在半路：{err}") from err
    texts = _fulltexts(output_dir, pool, fetch) if fulltext else {}
    write_atomic(output_dir / SOURCES_NAME, report.render(
        title=requirement.title(need, "文献检索"), seeds=seeds, pool=pool, stop=stop,
        texts=texts, fulltext=fulltext, gathered=gathered))
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


def _check_since(since: int) -> None:
    """「近三年」要换算成年份再给：写成 3 当场拒，不当成公元 3 年、悄悄等于不筛。"""
    this_year = datetime.date.today().year
    if since and not 1000 <= since <= this_year:
        raise CapabilityFailed(
            f"起始年份写四位的年份（比如近三年是 {this_year - 2}），0 是不限；得到 {since}")


# ── 种子与第 0 跳 ─────────────────────────────────────────────────────────
def _seed_session(output_dir: Path, runner: Runner, need: str, since: int,
                  costs: list[float]) -> Seeds:
    period = (f"只要 {since} 年及以后发表的论文：平台去学术库查时按这个年份查，更早的不交给你筛；"
              "种子也只找这之后发表的。" if since else "不限年份。")
    prompt = prompting.build_prompt(
        SEED_PROMPT, {"requirement": need, "period": period, "max_queries": MAX_QUERIES,
                      "max_seeds": MAX_SEEDS},
        loadout=loadout.around(output_dir))
    result = session.run_session(runner, prompt, cwd=output_dir, allowed_paths=[output_dir],
                                 log_dir=output_dir / LOG_DIRNAME / "seeds")
    costs.append(result.cost_usd)
    _check_outcome(result, SEEDS_NAME)
    seeds, problems = parse_seeds(_read(output_dir / SEEDS_NAME))
    if seeds is None:
        raise CapabilityFailed(f"{SEEDS_NAME} 不合形状：" + "；".join(problems))
    return seeds


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
    keys = {paper.key for paper in frontier}
    for paper in frontier:
        pool.note_refs(paper)
    for work in client.citing(sorted(keys), CITING_PAGES, pool.since):
        citer = from_openalex(work)
        pool.note_citing(citer, keys & set(citer.refs))
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
    """一跳一次筛选会话。没拿到合格结论的几篇（漏写、抄错号、同一篇两条相反的）单独补筛一次，
    补完还缺才判失败：四十篇里抄错一个号就让整次检索作废，前面几分钟的检索全白费（外层 #216）。"""
    entries = pool.of_hop(hop)
    decided = _ask(output_dir, runner, need, criteria, pool, hop, entries, "", costs)
    rest = [e for e in entries if e.paper.key not in decided]
    if rest:
        decided |= _ask(output_dir, runner, need, criteria, pool, hop, rest, REST_SUFFIX, costs)
        missing = [e.paper.key for e in rest if e.paper.key not in decided]
        if missing:
            raise CapabilityFailed(f"第 {hop} 跳补筛之后还有 {len(missing)} 篇没有结论："
                                   + ", ".join(missing[:10]) + (" 等" if len(missing) > 10 else ""))
    for key, (verdict, reason) in decided.items():
        pool.decide(key, verdict, reason)


def _ask(output_dir: Path, runner: Runner, need: str, criteria: str, pool: Pool, hop: int,
         entries: list[Entry], suffix: str, costs: list[float]) -> dict[str, tuple[str, str]]:
    """把 entries 交给执行层筛一次，返回拿到合格结论的那些；不合格的记日志，由调用方补筛。"""
    round_dir = output_dir / ROUNDS_DIRNAME / str(hop)
    round_dir.mkdir(parents=True, exist_ok=True)
    listing = "\n\n".join(_listing(entry) for entry in entries)
    (round_dir / _suffixed(LISTING_NAME, suffix)).write_text(listing + "\n", encoding="utf-8")
    decisions = f"{ROUNDS_DIRNAME}/{hop}/{_suffixed(DECISIONS_NAME, suffix)}"
    prompt = prompting.build_prompt(
        SCREEN_PROMPT, {"hop": hop, "count": len(entries), "requirement": need,
                        "criteria": criteria, "candidates": listing,
                        "decisions": str(output_dir / decisions)},
        loadout=loadout.around(output_dir))
    result = session.run_session(runner, prompt, cwd=output_dir, allowed_paths=[output_dir],
                                 log_dir=output_dir / LOG_DIRNAME / f"hop-{hop}{suffix}")
    costs.append(result.cost_usd)
    _check_outcome(result, decisions)
    decided, problems = parse_decisions(_read(output_dir / decisions),
                                        [e.paper.key for e in entries])
    if problems:
        LOGGER.warning("screen_problems hop=%d file=%s decided=%d/%d %s", hop, decisions,
                       len(decided), len(entries), "；".join(problems[:8]))
    return decided


def _suffixed(name: str, suffix: str) -> str:
    stem, dot, ext = name.rpartition(".")
    return f"{stem}{suffix}{dot}{ext}"


def _listing(entry: Entry) -> str:
    paper = entry.paper
    facts = " · ".join(x for x in (str(paper.year or "年份不详"), paper.venue,
                                   f"被引 {paper.cited_by}") if x)
    abstract = paper.abstract[:ABSTRACT_MAX] + ("…" if len(paper.abstract) > ABSTRACT_MAX else "")
    return "\n".join([
        f"### {paper.key}",
        f"- 题目：{paper.title or '（没有题目）'}",
        f"- 年份 · 出处 · 被引：{facts}",
        f"- 怎么找到的：{_origins(entry.found)}",
        f"- 摘要：{abstract or '（OpenAlex 没有摘要）'}",
    ])


def _origins(marks: list[str]) -> str:
    """来路只数每种几条，不列检索词与父论文题目：原来那样写占清单四分之一，筛得并不更准（外层
    #219）。给人看的 sources.md 照旧写全（pool.describe）。"""
    kinds = Counter(mark.partition(":")[0] for mark in marks)
    says = (("seed", "种子"), ("query", "检索词 {n} 条"), ("ref", "被 {n} 篇已收录的引用"),
            ("cites", "引用了 {n} 篇已收录的"))
    return "；".join(say.format(n=kinds[kind]) for kind, say in says if kinds[kind])


def _fulltexts(output_dir: Path, pool: Pool, fetch: Fetch) -> dict[str, Fulltext]:
    return fulltext_mod.fetch_all([e.paper for e in pool.included()], output_dir, fetch)


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
