"""上游清单怎么读、自己的清单怎么写（外层 #233）。

读：上游是文献阶段的一次产出，只认它的主文件 `sources.md`（纲领 P-20）。一篇一块，从 `### `
标题行起到下一个标题；标题前面的编号留着当这一篇的号，原文取块里反引号括起、在上游目录里真存在
的第一个文件——文献检索写的是 `papers/<W号>/paper.md`，研究助理手写的清单只要把原文路径用反引号
括起来也认。

写：本步骤的 `sources.md` 也是文献阶段的主文件，下游当文本读。读了哪些、每篇一句话、笔记在哪、
原句对上几条；没读成的、没有原文的、按篇数上限没轮到的列在文末；检索过程不抄，指回上游。
笔记写成相对这份文件的链接，页面上点得开（外层 #236）。
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

HEADING_RE = re.compile(r"^###\s+(?:(\d+)\.\s*)?(.+?)\s*$")
TICK_RE = re.compile(r"`([^`]+)`")
LINK_PREFIX = "- 链接："


@dataclass(frozen=True)
class Entry:
    n: str                        # 上游清单里的编号，也是笔记目录名
    title: str                    # 标题行（带年份），原样
    lines: tuple[str, ...]        # 块里其余的行，原样
    fulltext: Path | None         # 原文的绝对路径；没有是 None

    @property
    def link(self) -> str:
        return next((ln.strip() for ln in self.lines if ln.strip().startswith(LINK_PREFIX)), "")


@dataclass
class Read:
    """一篇读的结果。"""

    entry: Entry
    note: str | None = None       # 相对产出目录的笔记；没读成是 None
    gist: str = ""                # 笔记里的「一句话」
    quotes: int = 0
    found: int = 0
    why: str = ""                 # 没读成的原因
    cost_usd: float = float("nan")


def parse(text: str, upstream: Path) -> list[Entry]:
    blocks: list[tuple[str, str, list[str]]] = []
    current: list[str] | None = None
    for line in text.splitlines():
        heading = HEADING_RE.match(line)
        if heading:
            current = []
            blocks.append((heading.group(1) or str(len(blocks) + 1), heading.group(2), current))
        elif line.startswith("#"):
            current = None
        elif current is not None:
            current.append(line)
    return [Entry(n, title, tuple(lines), _fulltext(lines, upstream)) for n, title, lines in blocks]


def _fulltext(lines: list[str], upstream: Path) -> Path | None:
    root = upstream.resolve()
    for token in TICK_RE.findall("\n".join(lines)):
        path = (root / token).resolve()
        if path.is_relative_to(root) and path.is_file():
            return path
    return None


def render(*, title: str, upstream_id: str, reads: list[Read], no_text: list[Entry],
           not_reached: list[Entry]) -> str:
    done = [r for r in reads if r.note]
    failed = [r for r in reads if not r.note]
    total, found = sum(r.quotes for r in done), sum(r.found for r in done)
    skipped = f"没有原文 {len(no_text)} 篇" + (
        f"，按最多读几篇没轮到 {len(not_reached)} 篇" if not_reached else "")
    lines = [
        f"# 材料来源：{title}（精读）",
        "",
        f"文献精读的产出：上游 {upstream_id} 收录的论文里有原文的，逐篇交给执行层按需求读，"
        "每篇一份笔记；笔记里每条结果抄了一句原文，框架逐条在原文里核过。"
        f"检索词、纳入标准、每篇怎么找到的，见 {upstream_id} 的 sources.md。",
        "",
        f"- 读了 {len(reads)} 篇：写出笔记 {len(done)} 篇，没读成 {len(failed)} 篇"
        + ("（列在文末）" if failed else ""),
        f"- 原句核对：笔记里抄的原句 {total} 条，在原文里找到 {found} 条",
        f"- 没读的：{skipped}",
        "",
        f"## 笔记（{len(done)} 篇）",
    ]
    for r in done:
        lines += ["", f"### {r.entry.n}. {r.entry.title}", ""]
        lines += [r.entry.link] if r.entry.link else []
        lines += [f"- 一句话：{r.gist or '（笔记里没有「一句话」那一节）'}",
                  f"- 笔记：[{r.note}]({r.note})（原句 {r.quotes} 条，在原文里找到 {r.found} 条）"]
    tails = ((f"没读成的（{len(failed)} 篇）", [f"{_name(r.entry)}：{r.why}" for r in failed]),
             (f"没有原文的（{len(no_text)} 篇）", [_named_link(e) for e in no_text]),
             (f"没轮到的（{len(not_reached)} 篇）", [_named_link(e) for e in not_reached]))
    for heading, rows in tails:
        if rows:
            lines += ["", f"## {heading}", ""] + [f"- {row}" for row in rows]
    return "\n".join(lines) + "\n"


def _name(entry: Entry) -> str:
    return f"{entry.n}. {entry.title}"


def _named_link(entry: Entry) -> str:
    link = entry.link.removeprefix(LINK_PREFIX).strip()
    return f"{_name(entry)}" + (f"　{link}" if link else "")
