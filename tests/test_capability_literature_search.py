"""文献检索：零模型的部分（查接口、去重、多跳排序、停的条件、核执行层交回的文件、写清单）用
假 OpenAlex 与剧本执行层测全，不连网、不连模型。

假 OpenAlex 走真客户端的 URL 拼法（`OpenAlex(get=...)`），按查询参数从一份小语料里答：

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
import urllib.error
import urllib.parse
from pathlib import Path

import pytest

from framework.capabilities import literature_search
from framework.capabilities.literature_search import loop, openalex, papers
from framework.capabilities.literature_search.fulltext import Fulltext
from framework.contracts.capability import CapabilityFailed, Inputs, Ports
from framework.workspace import outputs
from tests.fixtures import packs_factory as pf
from tests.fixtures.scripted_backend import ScriptedRunner


def _work(key: str, title: str, *, doi: str | None = None, refs: tuple[str, ...] = (),
          cited: int = 0, abstract: str = "", pdf: str | None = None,
          landings: tuple[str, ...] = ()) -> dict:
    words = abstract.split()
    return {
        "id": f"https://openalex.org/{key}", "doi": f"https://doi.org/{doi}" if doi else None,
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
    _work("W5", "Bayesian PINN", cited=40),
    _work("W6", "Follow-up on both", refs=("W1", "W2"), cited=10),
    _work("W7", "Unrelated citing paper", refs=("W1",), cited=5),
    # 期刊版的 DOI 是主 DOI，arXiv 只挂在 locations 里：按 arXiv 的 DOI 查不到（实测 B-PINNs 就是）
    _work("W10", "Journal version of an arXiv preprint", doi="10.1016/j.jcp.2020.109913",
          landings=("http://arxiv.org/abs/2003.06097",)),
)}
SEARCHES = {"pinn inverse": ["W2", "W8"]}
RELEVANT = {"W1", "W2", "W3", "W5", "W6"}
HIDDEN = {"W9"}


class FakeOpenAlex:
    """按 URL 的查询参数答；记下每个 URL，测试对账查了什么。"""

    def __init__(self) -> None:
        self.urls: list[str] = []

    def __call__(self, url: str) -> tuple[dict, dict[str, str]]:
        self.urls.append(url)
        query = urllib.parse.parse_qs(urllib.parse.urlsplit(url).query)
        assert query["select"] == [openalex.SELECT]
        if "search" in query:
            keys = SEARCHES.get(query["search"][0], [])
        else:
            field, _, value = query["filter"][0].partition(":")
            wanted = value.split("|")
            if field == "doi":
                keys = [k for k, w in CORPUS.items() if w["doi"] and w["doi"][16:] in wanted]
            elif field == "openalex_id":
                keys = [k for k in wanted if k in CORPUS and k not in HIDDEN]
            elif field == "locations.landing_page_url":
                keys = [k for k, w in CORPUS.items()
                        if any(loc["landing_page_url"] in wanted for loc in w["locations"])]
            else:
                assert field == "cites"
                keys = [k for k, w in CORPUS.items()
                        if f"https://openalex.org/{value}" in w["referenced_works"]]
        return {"results": [CORPUS[k] for k in keys]}, {"x-ratelimit-remaining": "900"}


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
    client = openalex.OpenAlex(get=get or FakeOpenAlex(), sleep=lambda s: None)
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
    assert pool["W1"]["found"] == ["seed"] and pool["W8"]["found"] == ["query:pinn inverse"]
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
    fake = FakeOpenAlex()
    out, runner, line = _search(ws, [_seeds_move(), reject_all], get=fake)
    assert "included=0" in line and runner.calls == 2
    assert not any("cites" in u for u in fake.urls)
    assert "第 0 跳一篇都没收" in (out / "sources.md").read_text()


def test_excluded_paper_never_enters_the_pool(ws):
    out, _, _ = _search(ws, [_seeds_move(), _screen, _screen], excluded=frozenset({"W6"}))
    assert "W6" not in _pool(out)


def test_screening_prompt_carries_criteria_abstract_and_origin(ws):
    _, runner, _ = _search(ws, [_seeds_move(), _screen], max_hops=0)
    prompt = runner.prompts[1]
    for token in ("用 PINN 做参数反演", "We solve inverse problems with PINNs",
                  "种子（联网搜索找到）", "检索词「pinn inverse」", "rounds/0/decisions.md",
                  "（OpenAlex 没有摘要）"):
        assert token in prompt
    assert runner.bash_rules == ("ai4sci skill",)


def test_missing_decision_fails_with_the_key(ws):
    def half(cwd: Path) -> None:
        (cwd / "rounds" / "0" / "decisions.md").write_text("W1 | 收 | 相关\n")
    with pytest.raises(CapabilityFailed, match="2 篇没有结论：W2, W8"):
        _search(ws, [_seeds_move(), half])


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
    def broke(url: str):
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

    def flaky(url: str):
        calls.append(url)
        if len(calls) < 3:
            raise urllib.error.HTTPError(url, 429, "slow down", {"Retry-After": "2",
                                         "x-ratelimit-remaining": "500"}, io.BytesIO(b""))
        return {"results": []}, {"x-ratelimit-remaining": "499"}
    client = openalex.OpenAlex(get=flaky, sleep=waits.append)
    assert client.search("q", 5) == []
    assert waits == [2.0, 2.0] and client.remaining == 499 and client.requests == 1


def test_client_gives_up_after_retries():
    def down(url: str):
        raise urllib.error.HTTPError(url, 503, "down", {}, io.BytesIO(b""))
    client = openalex.OpenAlex(get=down, sleep=lambda s: None)
    with pytest.raises(openalex.OpenAlexError, match="返回 503（第 4 次）"):
        client.by_keys(["W1"])


def test_batches_split_at_fifty():
    fake = FakeOpenAlex()
    openalex.OpenAlex(get=fake).by_keys([f"W{i}" for i in range(120)])
    assert len(fake.urls) == 3


def test_ids_are_read_from_seed_lines():
    line = ("见 https://doi.org/10.1016/J.JCP.2022.111402. 与 https://arxiv.org/abs/2504.05248v2，"
            "还有 arXiv:2209.03276 和 https://doi.org/10.48550/arXiv.2304.12541")
    assert papers.dois_in(line) == ["10.1016/j.jcp.2022.111402"]
    assert papers.arxivs_in(line) == ["2504.05248", "2209.03276", "2304.12541"]
    assert papers.dois_in("https://www.sciencedirect.com/science/article/pii/S0021999") == []


def test_arxiv_seed_resolves_through_locations_when_the_main_doi_is_the_journal(ws):
    seeds = {"seeds.md": "## 检索词\n- nothing\n\n## 纳入标准\n- x\n\n## 种子\n"
                         "- https://arxiv.org/abs/2003.06097v3 贝叶斯 PINN\n"}
    fake = FakeOpenAlex()
    out, _, _ = _search(ws, [seeds, _screen], max_hops=0, get=fake)
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
