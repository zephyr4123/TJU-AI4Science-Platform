"""文献检索：零模型的部分（查接口、去重、多跳排序、停的条件、核执行层交回的文件、写清单）用
假 OpenAlex 与剧本执行层测全，不连网、不连模型。

假网络（`FakeWeb`）走真客户端的 URL 拼法，OpenAlex 按查询参数从一份小语料里答，Crossref、
arXiv、Europe PMC 按检索词从 `FREE` 里答（缺省什么都没查到）：

    W1 种子（DOI 10.1016/j.seed.2022），引用 W3 W4 W9
    W2、W8 是检索词「pinn inverse」的结果，W2 引用 W5
    W6 引用 W1 与 W2（关联两篇）；W7 引用 W1
    W9 在 W1 的参考文献里，但 OpenAlex 不返回它（合并或删掉的记录）

相关的是 W1 W2 W3 W5 W6；剧本执行层照这份名单筛。
"""

from __future__ import annotations

import io
import json
import re
import subprocess
import urllib.error
import urllib.parse
from pathlib import Path

import pytest

from framework.capabilities import literature_search
from framework.capabilities.literature_search import fulltext, indexes, loop, openalex, papers, web
from framework.capabilities.literature_search.fulltext import Fulltext
from framework.capabilities.literature_search.pool import Entry
from framework.contracts.capability import CapabilityFailed, Inputs, Ports
from framework.workspace import outputs
from tests.fixtures import packs_factory as pf
from tests.fixtures.scripted_backend import ScriptedRunner


def _work(key: str, title: str, *, doi: str | None = None, refs: tuple[str, ...] = (),
          cited: int = 0, abstract: str = "", pdf: str | None = None,
          landings: tuple[str, ...] = (), pmid: str | None = None) -> dict:
    words = abstract.split()
    return {
        "id": f"https://openalex.org/{key}", "doi": f"https://doi.org/{doi}" if doi else None,
        "ids": {"pmid": f"https://pubmed.ncbi.nlm.nih.gov/{pmid}"} if pmid else {},
        "display_name": title, "publication_year": 2022,
        "authorships": [{"author": {"display_name": "A. Author"}}],
        "primary_location": {"source": {"display_name": "J. Comput. Phys."},
                             "landing_page_url": None},
        "cited_by_count": cited,
        "abstract_inverted_index": {w: [i] for i, w in enumerate(words)} if words else None,
        "referenced_works": [f"https://openalex.org/{r}" for r in refs],
        "best_oa_location": {"pdf_url": pdf} if pdf else None,
        "locations": [{"landing_page_url": u, "pdf_url": None} for u in landings],
    }


CORPUS = {w["id"].rsplit("/", 1)[1]: w for w in (
    _work("W1", "Seed paper on PINN inverse problems", doi="10.1016/j.seed.2022",
          refs=("W3", "W4", "W9"), cited=100, abstract="We solve inverse problems with PINNs",
          pdf="https://x.org/1.pdf"),
    _work("W2", "PINN parameter estimation", refs=("W5",), cited=50,
          abstract="Estimate parameters"),
    _work("W8", "Unrelated fluid simulation", cited=500),
    _work("W3", "Classic inverse PDE method", cited=300),
    _work("W4", "Unrelated optimizer", cited=900),
    _work("W5", "Bayesian PINN", doi="10.1016/j.bpinn.2021", cited=40, pmid="31415"),
    _work("W6", "PINN inverse follow-up on both", refs=("W1", "W2"), cited=10),
    _work("W7", "Unrelated citing paper", refs=("W1",), cited=5),
    # 期刊版的 DOI 是主 DOI，arXiv 只挂在 locations 里：按 arXiv 的 DOI 查不到（实测 B-PINNs 就是）
    _work("W10", "Journal version of an arXiv preprint", doi="10.1016/j.jcp.2020.109913",
          landings=("http://arxiv.org/abs/2003.06097",)),
)}
SEARCHES = {"pinn inverse": ["W2", "W8"]}
# 不扣额度的三家：（哪家, 检索词）→ 命中的编号
FREE: dict[tuple[str, str], list[str]] = {}
RELEVANT = {"W1", "W2", "W3", "W5", "W6"}
HIDDEN = {"W9"}


class FakeWeb:
    """按主机与查询参数答；记下每个 URL，测试对账查了什么。`fail` 里的主机一律回 500。"""

    def __init__(self, fail: tuple[str, ...] = ()) -> None:
        self.urls: list[str] = []
        self.fail = fail

    def __call__(self, url: str, headers: dict[str, str]) -> tuple[bytes, dict[str, str]]:
        self.urls.append(url)
        self.headers = headers
        parts = urllib.parse.urlsplit(url)
        query = {k: v[0] for k, v in urllib.parse.parse_qs(parts.query).items()}
        if parts.netloc in self.fail:
            raise urllib.error.HTTPError(url, 500, "boom", {}, io.BytesIO(b""))
        if parts.netloc == "api.crossref.org":
            items = [{"DOI": d, "type": "journal-article"}
                     for d in FREE.get(("Crossref", query["query"]), [])]
            return json.dumps({"message": {"items": items}}).encode(), {}
        if parts.netloc == "export.arxiv.org":
            q = query["search_query"].replace("all:", "").replace(" AND ", " ")
            entries = "".join(f"<entry><id>http://arxiv.org/abs/{a}v1</id></entry>"
                              for a in FREE.get(("arXiv", q), []))
            return f"<feed><id>http://arxiv.org/api/x</id>{entries}</feed>".encode(), {}
        if parts.netloc == "www.ebi.ac.uk":
            rows = [{"pmid": m} for m in FREE.get(("Europe PMC", query["query"]), [])]
            return json.dumps({"resultList": {"result": rows}}).encode(), {}
        assert parts.netloc == "api.openalex.org" and query["select"] == openalex.SELECT
        return json.dumps({"results": [CORPUS[k] for k in _openalex(query)]}).encode(), {
            "x-ratelimit-remaining": "900"}


def _openalex(query: dict[str, str]) -> list[str]:
    if "search" in query:
        return SEARCHES.get(query["search"], [])
    field, _, value = query["filter"].partition(":")
    wanted = value.split("|")
    if field == "doi":
        return [k for k, w in CORPUS.items() if w["doi"] and w["doi"][16:] in wanted]
    if field == "openalex_id":
        return [k for k in wanted if k in CORPUS and k not in HIDDEN]
    if field == "pmid":
        return [k for k, w in CORPUS.items() if w["ids"].get("pmid", "").rsplit("/", 1)[-1]
                in wanted]
    if field == "locations.landing_page_url":
        return [k for k, w in CORPUS.items()
                if any(loc["landing_page_url"] in wanted for loc in w["locations"])]
    assert field == "cites" and query["per-page"] == "200" and query["cursor"] == "*"
    return [k for k, w in CORPUS.items()
            if any(f"https://openalex.org/{v}" in w["referenced_works"] for v in wanted)]


def _client(get) -> openalex.OpenAlex:
    ticks = iter(range(10**6))
    return openalex.OpenAlex(web.Web(get=get, sleep=lambda s: None, clock=lambda: next(ticks)))


def _seeds_move(extra: str = "") -> dict[str, str]:
    return {"seeds.md": (
        "## 检索词\n- pinn inverse\n\n## 纳入标准\n- 用 PINN 做参数反演\n\n## 种子\n"
        "- https://doi.org/10.1016/J.SEED.2022. 种子综述\n"
        "- https://example.com/blog 一篇博客\n" + extra)}


def _screen(cwd: Path) -> None:
    """照 RELEVANT 筛最新那一跳的候选：候选清单是框架写的，W 号从里面读。"""
    rounds = sorted((cwd / "rounds").iterdir(), key=lambda p: int(p.name))
    current = rounds[-1]
    keys = re.findall(r"^### (W\d+)$", (current / "candidates.md").read_text(), re.M)
    lines = [f"{k} | {'收' if k in RELEVANT else '不收'} | 理由 {k}" for k in keys]
    (current / "decisions.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def _fake_fetch(paper: papers.Paper, output_dir: Path) -> Fulltext:
    if not paper.pdf_url:
        return Fulltext(None, None, "没有开放获取的 PDF")
    return Fulltext(f"papers/{paper.key}/paper.md", 12)


@pytest.fixture
def ws(tmp_path):
    return pf.make_workspace(tmp_path)


def _out(ws) -> tuple[Path, Inputs]:
    directory, _ = outputs.open_output(ws, "literature", title="t", by="literature-search",
                                       inputs=[], params={}, flow=None, step=None,
                                       requirement=1, chat_id=None)
    return directory, Inputs(ws.root)


def _search(ws, moves, *, max_hops=2, per_hop=10, min_new=1, get=None, **kw):
    out, inputs = _out(ws)
    runner = ScriptedRunner(list(moves))
    client = _client(get or FakeWeb())
    line = loop.search(out, inputs, runner, loop.Limits(max_hops, per_hop, min_new),
                         fulltext=True, client=client, fetch=_fake_fetch, **kw)
    return out, runner, line


def _pool(out: Path) -> dict[str, dict]:
    rows = [json.loads(x) for x in (out / "candidates.jsonl").read_text().splitlines()]
    return {r["paper"]["key"]: r for r in rows}


def test_hops_expand_from_included_papers_and_stop_when_nothing_is_left(ws):
    out, runner, line = _search(ws, [_seeds_move(), _screen, _screen])
    # 种子一次、第 0 跳一次、第 1 跳一次；第 2 跳没有候选，不起会话
    assert runner.calls == 3
    assert line.startswith("literature ok\tincluded=5\tscreened=8\thops=2\tfulltext=1\t")
    pool = _pool(out)
    assert {k for k, r in pool.items() if r["hop"] == 0} == {"W1", "W2", "W8"}
    assert {k for k, r in pool.items() if r["hop"] == 1} == {"W3", "W4", "W5", "W6", "W7"}
    assert "W9" not in pool  # OpenAlex 不返回的线索不进池
    assert {k for k, r in pool.items() if r["verdict"] == "收"} == RELEVANT
    assert sorted(pool["W6"]["found"]) == ["cites:W1", "cites:W2"]
    assert pool["W1"]["found"] == ["seed"]
    assert pool["W8"]["found"] == ["query:OpenAlex:pinn inverse"]
    sources = (out / "sources.md").read_text()
    assert "停在：没有可筛的候选了" in sources
    assert "引用了收录的《Seed paper on PINN inverse problems》" in sources
    assert "被收录的《PINN parameter estimation》引用" in sources
    assert "`papers/W1/paper.md`（12 页）" in sources
    assert "https://example.com/blog 一篇博客" in sources  # 认不出编号的种子列在文末
    assert "## 没拿到原文的（4 篇）" in sources
    # 每一跳的候选清单、结论、执行层日志都留档
    assert (out / "rounds" / "1" / "decisions.md").is_file()
    assert sorted(p.name for p in (out / "executor").iterdir()) == ["hop-0", "hop-1", "seeds"]


def test_next_hop_takes_the_most_linked_leads_first(ws):
    out, runner, _ = _search(ws, [_seeds_move(), _screen, _screen], max_hops=1, per_hop=1)
    pool = _pool(out)
    # W6 关联两篇收录的，排在只关联一篇的前面（哪怕 W4 被引 900）
    assert [k for k, r in pool.items() if r["hop"] == 1] == ["W6"]
    prompt = runner.prompts[2]
    assert "### W6" in prompt and "### W4" not in prompt


def test_leads_with_query_words_outrank_more_cited_ones_at_equal_links(ws):
    """同样只关联一篇收录的：W3（题目有 inverse，被引 300）、W5（有 PINN，被引 40）排在 W4（检索词
    一个都不沾，被引 900）前面。外层 #212 两道召回实测：乘上字面相关度，第 1 跳前 30 篇的答案
    11→15、6→7。"""
    out, _, _ = _search(ws, [_seeds_move(), _screen, _screen], max_hops=1, per_hop=3)
    assert [k for k, r in _pool(out).items() if r["hop"] == 1] == ["W6", "W3", "W5"]


def test_stops_when_a_hop_adds_fewer_than_the_floor(ws):
    out, runner, _ = _search(ws, [_seeds_move(), _screen, _screen], min_new=4)
    assert runner.calls == 3
    assert "停在：第 1 跳新收录 3 篇，少于停止下限 4" in (out / "sources.md").read_text()


def test_zero_hops_screens_only_seeds_and_queries(ws):
    out, runner, line = _search(ws, [_seeds_move(), _screen], max_hops=0)
    assert runner.calls == 2 and "\thops=0\t" in line
    assert set(_pool(out)) == {"W1", "W2", "W8"}
    assert "停在：到了最多跳数 0" in (out / "sources.md").read_text()


def test_nothing_included_at_hop_zero_stops_without_expanding(ws):
    def reject_all(cwd: Path) -> None:
        current = cwd / "rounds" / "0"
        keys = re.findall(r"^### (W\d+)$", (current / "candidates.md").read_text(), re.M)
        (current / "decisions.md").write_text("".join(f"{k} | 不收 | 无关\n" for k in keys))
    fake = FakeWeb()
    out, runner, line = _search(ws, [_seeds_move(), reject_all], get=fake)
    assert "included=0" in line and runner.calls == 2
    assert not any("cites" in u for u in fake.urls)
    assert "第 0 跳一篇都没收" in (out / "sources.md").read_text()


def test_excluded_paper_never_enters_the_pool(ws):
    out, _, _ = _search(ws, [_seeds_move(), _screen, _screen], excluded=frozenset({"W6"}))
    assert "W6" not in _pool(out)


def test_screening_prompt_carries_criteria_abstract_and_origin(ws):
    """结论文件给绝对路径：给相对的，执行层拼路径时丢了 rounds/2/、写到产出目录根上，
    整次作废（外层 #219）。"""
    out, runner, _ = _search(ws, [_seeds_move(), _screen], max_hops=0)
    prompt = runner.prompts[1]
    for token in ("用 PINN 做参数反演", "We solve inverse problems with PINNs",
                  "- 怎么找到的：种子", "检索词 1 条", f"`{out / 'rounds' / '0' / 'decisions.md'}`",
                  "（OpenAlex 没有摘要）"):
        assert token in prompt
    assert runner.bash_rules == ("ai4sci skill",)


def test_screening_listing_counts_origins_and_cuts_long_abstracts():
    """给筛选看的清单只数每种来路几条、摘要截到 500 字：清单砍掉六成，筛得一样准（外层 #219）。"""
    paper = papers.Paper("W1", "A PINN study", 2024, (), "J", None, None, None, "x" * 900, 3, (),
                         None, None)
    entry = Entry(paper, 1, ["query:OpenAlex:pinn", "query:arXiv:pinn", "ref:W7", "ref:W8",
                             "cites:W9"])
    listing = loop._listing(entry)
    assert "- 怎么找到的：检索词 2 条；被 2 篇已收录的引用；引用了 1 篇已收录的" in listing
    assert "- 摘要：" + "x" * 500 + "…" in listing
    assert "x" * 501 not in listing
    assert "《" not in listing and "「" not in listing


def test_undecided_papers_are_rescreened_once_and_only_they(ws):
    """一字抄错不该让整次检索作废（外层 #216）：漏写的、抄错号的、同一篇两条相反结论的，单独补筛
    一次；不在候选里的号忽略；同一篇重复写了一样的结论不算错。"""
    def sloppy(cwd: Path) -> None:
        (cwd / "rounds" / "0" / "decisions.md").write_text(
            "W1 | 收 | 相关\nW1 | 收 | 相关\nW9999 | 收 | 抄错的号\n"
            "W2 | 收 | 相关\nW2 | 不收 | 无关\n")

    def rest(cwd: Path) -> None:
        listing = (cwd / "rounds" / "0" / "candidates-rest.md").read_text()
        keys = re.findall(r"^### (W\d+)$", listing, re.M)
        (cwd / "rounds" / "0" / "decisions-rest.md").write_text(
            "".join(f"{k} | 不收 | 补筛 {k}\n" for k in keys))
    out, runner, _ = _search(ws, [_seeds_move(), sloppy, rest], max_hops=0)
    assert "### W1" not in runner.prompts[2]
    assert "### W2" in runner.prompts[2] and "### W8" in runner.prompts[2]
    pool = _pool(out)
    assert pool["W1"]["verdict"] == "收"
    assert (pool["W2"]["verdict"], pool["W2"]["reason"]) == ("不收", "补筛 W2")
    assert pool["W8"]["reason"] == "补筛 W8"


def test_still_undecided_after_the_rescreen_fails_with_the_key(ws):
    def half(cwd: Path) -> None:
        (cwd / "rounds" / "0" / "decisions.md").write_text("W1 | 收 | 相关\n")

    def still_half(cwd: Path) -> None:
        (cwd / "rounds" / "0" / "decisions-rest.md").write_text("W2 | 收 | 相关\n")
    with pytest.raises(CapabilityFailed, match="补筛之后还有 1 篇没有结论：W8"):
        _search(ws, [_seeds_move(), half, still_half])


def test_writing_outside_the_decisions_file_fails(ws):
    def sneaky(cwd: Path) -> None:
        _screen(cwd)
        (cwd / "notes.md").write_text("x")
    with pytest.raises(CapabilityFailed, match="之外的文件：notes.md"):
        _search(ws, [_seeds_move(), sneaky])


def test_seeds_without_queries_fail(ws):
    bad = {"seeds.md": "## 检索词\n\n## 纳入标准\n- x\n\n## 种子\n"}
    with pytest.raises(CapabilityFailed, match="「检索词」一节一条都没有"):
        _search(ws, [bad])


def test_quota_exhausted_fails_and_keeps_what_was_seen(ws):
    def broke(url: str, headers: dict[str, str]):
        raise urllib.error.HTTPError(url, 429, "Too Many Requests",
                                     {"x-ratelimit-remaining": "0"}, io.BytesIO(b""))
    with pytest.raises(CapabilityFailed, match="额度用完"):
        _search(ws, [_seeds_move()], get=broke)


def test_run_without_an_executor_is_refused(ws):
    out, inputs = _out(ws)
    with pytest.raises(CapabilityFailed, match="要执行层"):
        literature_search.run(out, inputs, Ports())


# ── 客户端与解析 ──────────────────────────────────────────────────────────
def test_client_retries_rate_limits_then_succeeds():
    calls, waits = [], []

    def flaky(url: str, headers: dict[str, str]):
        calls.append(url)
        if len(calls) < 3:
            raise urllib.error.HTTPError(url, 429, "slow down", {"Retry-After": "2",
                                         "x-ratelimit-remaining": "500"}, io.BytesIO(b""))
        return b'{"results": []}', {"x-ratelimit-remaining": "499"}
    client = openalex.OpenAlex(web.Web(get=flaky, sleep=waits.append))
    assert client.search("q", 5) == []
    assert waits == [2.0, 2.0] and client.remaining == 499 and client.requests == 1


def test_arxiv_rate_limit_waits_long_enough_for_a_busy_neighbour():
    """同一台机器上几次检索同时查 arXiv 会被 429，1 / 2 / 4 秒退避三次就放弃，一批检索词白丢
    （外层 #216）。arXiv 不给 Retry-After，按它的限速退避得更久、多等一次。"""
    calls, waits = [], []

    def busy(url: str, headers: dict[str, str]):
        calls.append(url)
        if len(calls) <= 4:
            raise urllib.error.HTTPError(url, 429, "slow down", {}, io.BytesIO(b""))
        return b"<feed><entry><id>http://arxiv.org/abs/2003.06097v1</id></entry></feed>", {}
    hits = indexes.arxiv(web.Web(get=busy, sleep=waits.append), "pinn inverse", 5)
    assert [h.arxiv for h in hits] == ["2003.06097"]
    assert [w for w in waits if w >= 5] == list(indexes.ARXIV_BACKOFF_S)


def test_client_gives_up_after_retries():
    def down(url: str, headers: dict[str, str]):
        raise urllib.error.HTTPError(url, 503, "down", {}, io.BytesIO(b""))
    client = _client(down)
    with pytest.raises(web.FetchError, match="返回 503（第 4 次）"):
        client.by_keys(["W1"])


def test_short_read_is_retried():
    """比 Content-Length 短：连接中途断了，按网络错误重试（pdf skill 就吃过这个亏）。"""
    replies = [ConnectionResetError("cut"), (b'{"results": []}', {})]

    def flaky(url: str, headers: dict[str, str]):
        reply = replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return reply
    assert _client(flaky).by_keys(["W1"]) == []


def test_same_host_requests_are_spaced():
    """arXiv 要求两次请求隔 3 秒：同一站点按调用方给的间隔等，别的站点不受影响。"""
    now, waits = [0.0], []

    def sleep(s: float) -> None:
        waits.append(s)
        now[0] += s
    w = web.Web(get=lambda url, headers: (b"", {}), sleep=sleep, clock=lambda: now[0])
    w.get("https://export.arxiv.org/a", spacing_s=3)
    now[0] += 1
    w.get("https://export.arxiv.org/b", spacing_s=3)
    w.get("https://api.crossref.org/c")
    assert waits == [2.0]


def test_batches_split_at_a_hundred():
    fake = FakeWeb()
    _client(fake).by_keys([f"W{i}" for i in range(120)])
    assert len(fake.urls) == 2


def test_key_goes_in_the_header_never_the_url(monkeypatch):
    """P-27：不要 key 也能用，有 key 用得更多。key 只从环境变量读，放请求头：URL 要进日志。"""
    fake = FakeWeb()
    monkeypatch.setenv(openalex.KEY_ENV, "sekrit")
    openalex.OpenAlex(web.Web(get=fake), key=openalex.api_key()).by_keys(["W1"])
    assert fake.headers == {"Authorization": "Bearer sekrit"}
    assert "sekrit" not in fake.urls[0]
    monkeypatch.setenv(openalex.KEY_ENV, " ")
    openalex.OpenAlex(web.Web(get=fake), key=openalex.api_key()).by_keys(["W1"])
    assert fake.headers == {}


def test_citing_is_one_query_per_hop_not_one_per_paper(ws):
    """「谁引用了它」原来一篇一次，占一次检索花费的三分之一；改成一跳合成一次 OR 查询。"""
    fake = FakeWeb()
    _search(ws, [_seeds_move(), _screen, _screen], max_hops=1, get=fake)
    assert sum("cites%3A" in u for u in fake.urls) == 1


def test_ids_are_read_from_seed_lines():
    line = ("见 https://doi.org/10.1016/J.JCP.2022.111402. 与 https://arxiv.org/abs/2504.05248v2，"
            "还有 arXiv:2209.03276 和 https://doi.org/10.48550/arXiv.2304.12541")
    assert papers.dois_in(line) == ["10.1016/j.jcp.2022.111402"]
    assert papers.arxivs_in(line) == ["2504.05248", "2209.03276", "2304.12541"]
    assert papers.dois_in("https://www.sciencedirect.com/science/article/pii/S0021999") == []


def test_arxiv_seed_resolves_through_locations_when_the_main_doi_is_the_journal(ws):
    seeds = {"seeds.md": "## 检索词\n- nothing\n\n## 纳入标准\n- x\n\n## 种子\n"
                         "- https://arxiv.org/abs/2003.06097v3 贝叶斯 PINN\n"}
    out, _, _ = _search(ws, [seeds, _screen], max_hops=0)
    pool = _pool(out)
    assert pool["W10"]["found"] == ["seed"] and pool["W10"]["paper"]["arxiv"] == "2003.06097"
    assert pool["W10"]["paper"]["pdf_url"] == "https://arxiv.org/pdf/2003.06097"
    assert "查不到的种子" not in (out / "sources.md").read_text()


def test_paper_from_openalex_rebuilds_abstract_and_arxiv_pdf():
    work = _work("W5", "t", doi="10.48550/arXiv.2504.05248", abstract="b a c")
    work["abstract_inverted_index"] = {"a": [1], "b": [0], "c": [2]}
    paper = papers.from_openalex(work)
    assert paper.abstract == "b a c"
    assert paper.arxiv == "2504.05248"
    assert paper.pdf_url == "https://arxiv.org/pdf/2504.05248"


def test_fulltext_falls_back_to_arxiv_when_the_publisher_refuses(tmp_path, monkeypatch):
    """出版社的 PDF 被人机验证拦住（真跑：IOP 返回 Radware 的页面），有 arXiv 版本就换它再试。"""
    tried = []

    def fake_capture(script, args, timeout_s):
        url = args[args.index("--input") + 1]
        tried.append(url)
        if "arxiv" not in url:
            return subprocess.CompletedProcess(args, 3, "", "链接返回的不是 PDF：captcha\n")
        return subprocess.CompletedProcess(args, 0, '{"pages": 9}\n', "")
    monkeypatch.setattr(fulltext, "capture_script", fake_capture)
    work = _work("W10", "t", doi="10.1088/2632-2153/ac3712", pdf="https://iopscience.iop.org/x/pdf",
                 landings=("http://arxiv.org/abs/2107.00940",))
    got = fulltext.fetch(papers.from_openalex(work), tmp_path)
    assert tried == ["https://iopscience.iop.org/x/pdf", "https://arxiv.org/pdf/2107.00940"]
    assert got == Fulltext("papers/W10/paper.md", 9)


def test_fulltext_reports_the_last_failure_when_every_link_fails(tmp_path, monkeypatch):
    monkeypatch.setattr(fulltext, "capture_script", lambda script, args, timeout_s:
                        subprocess.CompletedProcess(args, 3, "", "HTTP Error 403: Forbidden\n"))
    work = _work("W11", "t", pdf="https://publisher.org/x.pdf")
    got = fulltext.fetch(papers.from_openalex(work), tmp_path)
    assert got.path is None and "403" in got.why


def test_queries_fan_out_to_free_indexes_and_resolve_through_openalex(ws, monkeypatch):
    """检索词过 Crossref、arXiv、Europe PMC：命中的 DOI / arXiv 号 / PMID 回 OpenAlex 取元数据；
    OpenAlex 里没有的命中不算；同一篇被几路查到，来源都记上。"""
    monkeypatch.setitem(FREE, ("Crossref", "pinn inverse"), ["10.1016/j.bpinn.2021",
                                                              "10.9999/not-in-openalex"])
    monkeypatch.setitem(FREE, ("arXiv", "pinn inverse"), ["2003.06097"])
    monkeypatch.setitem(FREE, ("Europe PMC", "pinn inverse"), ["31415"])
    out, _, _ = _search(ws, [_seeds_move(), _screen], max_hops=0)
    pool = _pool(out)
    assert {k for k, r in pool.items() if r["hop"] == 0} == {"W1", "W2", "W8", "W5", "W10"}
    assert sorted(pool["W5"]["found"]) == ["query:Crossref:pinn inverse",
                                           "query:Europe PMC:pinn inverse"]
    sources = (out / "sources.md").read_text()
    assert "命中 Crossref 2 条、Europe PMC 1 条、OpenAlex 2 条、arXiv 1 条" in sources
    assert "OpenAlex 里取不到的 1 条不算" in sources
    assert "检索词「pinn inverse」（Europe PMC）" in sources


def test_a_free_index_failing_is_recorded_not_fatal(ws):
    out, _, line = _search(ws, [_seeds_move(), _screen], max_hops=0,
                           get=FakeWeb(fail=("api.crossref.org",)))
    assert line.startswith("literature ok")
    sources = (out / "sources.md").read_text()
    assert "## 没查成的检索" in sources and "Crossref「pinn inverse」" in sources


def test_hop_zero_keeps_the_best_ranked_query_hits(ws, monkeypatch):
    """第 0 跳取每跳筛选数的两倍：W2 被两家查到排第一；W8 与 W5 都只一家，W5 的题目沾检索词。"""
    monkeypatch.setitem(FREE, ("Crossref", "pinn inverse"), ["10.1016/j.bpinn.2021"])
    monkeypatch.setitem(FREE, ("Europe PMC", "pinn inverse"), [])
    w2 = CORPUS["W2"]["doi"]
    monkeypatch.setitem(CORPUS["W2"], "doi", "https://doi.org/10.1016/j.w2.2020")
    monkeypatch.setitem(FREE, ("Crossref", "pinn inverse"), ["10.1016/j.bpinn.2021",
                                                              "10.1016/j.w2.2020"])
    out, _, _ = _search(ws, [_seeds_move(), _screen], max_hops=0, per_hop=1)
    assert w2 is None
    hop0 = [k for k, r in _pool(out).items() if r["hop"] == 0]
    assert hop0 == ["W1", "W2", "W5"]  # 种子不占名额，检索命中取前 2


def test_opening_batch_alternates_fresh_and_classic():
    """第 0 跳两种排法轮流取：按命中与相关度（新论文多在这头），与再乘被引数（经典论文）。
    召回实测：只按前者，前 60 篇里 2026 年的新论文占一半、答案 4 篇；只按后者答案 9 篇但新论文
    只剩 15 篇；轮流取 6 篇、新论文 26 篇。"""
    from framework.capabilities.literature_search.pool import Pool

    def paper(key, title, cited, year):
        return papers.from_openalex({**_work(key, title, cited=cited), "publication_year": year})
    pool = Pool(queries=("pinn blood pressure",))
    fresh = paper("W1", "PINN for cuffless blood pressure", 0, 2026)
    middle = paper("W2", "PINN for blood flow", 3, 2025)
    classic = paper("W3", "Physics-informed neural networks", 9000, 2019)
    for p in (fresh, middle, classic):
        pool.note_query(p, "Crossref", "pinn blood pressure")
    assert [p.key for p in pool.next_batch(2)] == ["W1", "W2"]
    assert [p.key for p in pool.opening_batch(2)] == ["W1", "W3"]
