"""文献精读：零模型的部分（从上游 sources.md 认出每篇与原文、一篇一个会话、核原句、失败不阻塞、
写清单）用剧本执行层测全，不连模型（外层 #233）。

上游是一次文献检索的产出（literature/1），sources.md 照检索写的样子：

    1. Memory Bank   原文 papers/W1/paper.md
    2. Agent Memory  原文 papers/W2/paper.md
    3. Paywalled     没拿到原文

剧本执行层按会话目录 notes/<n>/ 的名字知道读的是第几篇，几个会话并行也不乱。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from framework.capabilities import literature_read
from framework.capabilities.literature_read import quotes, read
from framework.contracts.capability import CapabilityFailed, Inputs, Ports
from framework.workspace import outputs
from tests.fixtures import packs_factory as pf
from tests.fixtures.scripted_backend import ScriptedRunner

TEXTS = {
    "1": "# MemoryBank\n\nWe propose **MemoryBank**, a long-term memory mechanism.\n"
         "It improves recall by 12.3% on the  SiliconFriend benchmark.\n",
    "2": "# Agentic Memory\n\nWe train a unified memory manager with reinforcement learning.\n",
}

UPSTREAM = """# 材料来源：智能体的长期记忆

文献检索的产出。

- 检索词：`agent memory`

## 纳入标准

- 研究智能体的长期记忆

## 收录（3 篇）

### 1. MemoryBank: Enhancing LLMs with Long-Term Memory（2024）

- 链接：https://arxiv.org/abs/2305.10250
- 为什么收：提出长期记忆机制
- 原文：`papers/W1/paper.md`（9 页）

### 2. Agentic Memory（2026）

- 链接：https://arxiv.org/abs/2601.01885
- 原文：`papers/W2/paper.md`（20 页）

### 3. Paywalled Memory Study（2025）

- 链接：https://doi.org/10.1000/paywalled
- 原文：没拿到，没有开放获取的 PDF

## 没拿到原文的（1 篇）

- 《Paywalled Memory Study》 https://doi.org/10.1000/paywalled
"""


def _note(n: str, *, quotes_: tuple[str, ...]) -> str:
    lines = [f"## 一句话\n\n第 {n} 篇提出了一种长期记忆。\n", "## 问题\n\n记不住。\n",
             "## 方法\n\n记下来。\n", "## 数据与实验\n\n一个基准。\n", "## 主要结果\n"]
    lines += [f"- 结果 {i}\n  > 原文：{q}\n" for i, q in enumerate(quotes_, start=1)]
    lines += ["\n## 局限\n\n原文没说。\n", "## 和本需求的关系\n\n直接相关。\n"]
    return "\n".join(lines)


def write_note(cwd: Path) -> None:
    """照会话目录名写笔记：第 1 篇两句原句都对得上（一句换了大小写、空白与加粗记号），
    第 2 篇一句对得上、一句是编的。"""
    if cwd.name == "1":
        said = ("we propose MemoryBank, a long-term memory mechanism",
                "It improves recall by 12.3% on the SiliconFriend benchmark.")
    else:
        said = ("We train a unified memory manager", "It beats every baseline by 40%.")
    (cwd / "note.md").write_text(_note(cwd.name, quotes_=said), encoding="utf-8")


@pytest.fixture
def ws(tmp_path):
    return pf.make_workspace(tmp_path)


def _upstream(ws, sources: str = UPSTREAM, texts: dict[str, str] = TEXTS) -> Path:
    directory, _ = outputs.open_output(ws, "literature", title="检索", by="literature-search",
                                       inputs=[], params={}, flow=None, step=None,
                                       requirement=1, chat_id=None)
    (directory / "sources.md").write_text(sources, encoding="utf-8")
    for n, text in texts.items():
        paper = directory / "papers" / f"W{n}" / "paper.md"
        paper.parent.mkdir(parents=True)
        paper.write_text(text, encoding="utf-8")
    return directory


def _read(ws, moves, upstream: Path | None = None, **params):
    upstream = upstream or _upstream(ws)
    out, _ = outputs.open_output(ws, "literature", title="精读", by="literature-read",
                                 inputs=["literature/1"], params={}, flow=None, step=None,
                                 requirement=1, chat_id=None)
    runner = ScriptedRunner(list(moves))
    line = literature_read.run(out, Inputs(ws.root, (upstream,), ("literature/1",)),
                               Ports(runner=runner), **params)
    return out, runner, line


def test_each_paper_with_fulltext_gets_its_own_session_and_note(ws):
    out, runner, line = _read(ws, [write_note, write_note])
    assert runner.calls == 2  # 第 3 篇没有原文，不起会话
    assert line.startswith("read ok\tpapers=2\tnotes=2\tquotes=3/4\t")
    assert all((out / "notes" / n / "note.md").is_file() for n in ("1", "2"))
    # 每个会话一个自己的目录：日志搬到 executor/<n>/，不留在笔记旁边
    assert sorted(p.name for p in (out / "executor").iterdir()) == ["1", "2"]
    assert not (out / "notes" / "1" / ".ai4sci").exists()
    prompt = next(p for p in runner.prompts if "MemoryBank" in p)
    note = str(out / "notes" / "1" / "note.md")
    for token in ("把 val_mse 压到最低", "It improves recall by 12.3%", note, "> 原文："):
        assert token in prompt
    sources = (out / "sources.md").read_text(encoding="utf-8")
    assert "### 1. MemoryBank: Enhancing LLMs with Long-Term Memory（2024）" in sources
    assert "- 一句话：第 1 篇提出了一种长期记忆。" in sources
    assert "[notes/1/note.md](notes/1/note.md)（原句 2 条，在原文里找到 2 条）" in sources
    assert "[notes/2/note.md](notes/2/note.md)（原句 2 条，在原文里找到 1 条）" in sources
    assert "## 没有原文的（1 篇）" in sources and "Paywalled Memory Study" in sources
    assert "literature/1" in sources  # 检索过程指回上游


def test_a_paper_that_was_not_read_is_listed_not_fatal(ws):
    """失败不阻塞：一篇会话没写笔记，只记这篇没读成，别的照收。"""
    def first_silent(cwd: Path) -> None:
        if cwd.name != "1":
            write_note(cwd)
    out, _, line = _read(ws, [first_silent, first_silent])
    assert line.startswith("read ok\tpapers=2\tnotes=1\t")
    sources = (out / "sources.md").read_text(encoding="utf-8")
    assert "## 没读成的（1 篇）" in sources and "没有写出笔记" in sources
    assert "[notes/2/note.md](notes/2/note.md)" in sources


def test_writing_outside_the_note_fails_that_paper(ws):
    def second_strays(cwd: Path) -> None:
        write_note(cwd)
        if cwd.name == "2":
            (cwd / "scratch.md").write_text("草稿", encoding="utf-8")
    out, _, line = _read(ws, [second_strays, second_strays])
    assert "\tnotes=1\t" in line
    sources = (out / "sources.md").read_text(encoding="utf-8")
    assert "## 没读成的（1 篇）" in sources and "scratch.md" in sources


def test_progress_follows_each_paper_from_reading_to_note(ws):
    """页面的精读面板照 progress.jsonl 画（外层 #245）：开头一行列出要读的每篇与同时几个会话，
    每篇开始读一行、读完或没读成一行；几个会话并行写，行行完整。"""
    def second_silent(cwd: Path) -> None:
        if cwd.name != "2":
            write_note(cwd)
    out, _, _ = _read(ws, [second_silent, second_silent])
    rows = [json.loads(x) for x in (out / "progress.jsonl").read_text().splitlines()]
    assert all(r.pop("at") for r in rows)
    assert rows[0] == {"papers": [
        {"n": "1", "title": "MemoryBank: Enhancing LLMs with Long-Term Memory（2024）"},
        {"n": "2", "title": "Agentic Memory（2026）"}], "sessions": read.SESSIONS}
    states: dict[str, list[str]] = {}
    for row in rows[1:]:
        states.setdefault(row["paper"], []).append(row["state"])
    assert states == {"1": ["reading", "done"], "2": ["reading", "failed"]}
    done = next(r for r in rows if r.get("state") == "done")
    assert (done["quotes"], done["found"]) == (2, 2)
    failed = next(r for r in rows if r.get("state") == "failed")
    assert "没有写出笔记" in failed["why"]


def test_nothing_read_at_all_fails(ws):
    with pytest.raises(CapabilityFailed, match="一篇都没读成"):
        _read(ws, [lambda cwd: None, lambda cwd: None])


def test_upstream_without_sources_or_fulltext_fails_before_any_session(ws):
    bare = _upstream(ws, sources=UPSTREAM.replace("`papers/W1/paper.md`", "没拿到")
                     .replace("`papers/W2/paper.md`", "没拿到"), texts={})
    with pytest.raises(CapabilityFailed, match="没有一篇有原文"):
        _read(ws, [], upstream=bare)
    (bare / "sources.md").unlink()
    with pytest.raises(CapabilityFailed, match="sources.md"):
        _read(ws, [], upstream=bare)


def test_max_papers_reads_the_first_few_in_upstream_order(ws):
    out, runner, line = _read(ws, [write_note], max_papers=1)
    assert runner.calls == 1 and "papers=1\t" in line
    assert "Agentic Memory" in (out / "sources.md").read_text(encoding="utf-8")  # 列为没读


def test_a_long_paper_is_cut_and_the_prompt_says_so(ws, monkeypatch):
    monkeypatch.setattr(read, "TEXT_MAX", 40)
    _, runner, _ = _read(ws, [write_note, write_note])
    prompt = next(p for p in runner.prompts if "MemoryBank" in p)
    assert "It improves recall" not in prompt
    assert "只有前 40 个字符" in prompt


def test_quotes_are_found_after_normalising_case_space_and_markup():
    text = "We propose **MemoryBank**, a long-term\nmemory   mechanism — “quoted”."
    assert quotes.found("we propose memorybank, a long-term memory mechanism", text)
    assert quotes.found("“quoted”", text) and quotes.found('"quoted"', text)
    assert not quotes.found("We propose a short-term memory", text)
    assert quotes.found("We propose MemoryBank…", text)  # 抄半句带省略号也算
    # PDF 解析进正文的脚注标记与标点前的空格（#233 真跑：LoCoMo 一句真原句因此没对上）
    assert quotes.found("despite high recall accuracies, likely due to loss",
                        "despite high recall accuracies<sup>9</sup> , likely due to loss")
    assert quotes.quoted("- 结果\n  > 原文：A b.\n> 原文: C d\n") == ["A b.", "C d"]
