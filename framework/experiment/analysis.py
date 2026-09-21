"""`analysis.md` 的契约：三节固定，数据表是数字回溯的锚（纲领 workflow.md §3）。

分析是执行层写的长文本，机器没法判"结论对不对"，但能判"数字有没有来源"：
执行层必须把它引用的每个指标值列进 `## 数据` 表（来源、指标、值三列，来源写成
`experiment/<n>/baseline` 或 `experiment/<n>/iter_N`；复现性分析读的是设计那包，来源写成
`design/<n>/baseline`、`design/<n>/repeat_<seed>`、`design/<n>/scoring`（论文值）或
`design/<n>/sigma`（重复的标准差），值原样抄），
正文里带小数点或指数的数只许出现表里有的值。分析能力在交产物前校验形状，
验证能力拿同一个解析器去 results.json 里逐条回溯——两个能力互不 import，共用的只有这份契约。

整数不当指标看（轮次、行数、样本量都是整数），百分比是相对变化、没有绝对来源，也不查：
这两条是 0.2.0 的已知边界，写在纲领里，不在这里静默放宽。
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from backends import RunResult
from framework.contracts.capability import CapabilityFailed

REQUIRED_HEADINGS = ("## 结论", "## 数据", "## 证伪与未决")
DATA_HEADING = "## 数据"
TABLE_COLUMNS = ("来源", "指标", "值")
# 来源：实验的一轮，或（复现性分析）设计那包的基线 / 某次重复 / scoring 里的论文值
SOURCE_RE = re.compile(
    r"^(experiment/\d+/(baseline|iter_\d+)|design/\d+/(baseline|repeat_\d+|scoring|sigma))$")
# 带小数点或指数的数；前后不能贴着字母、数字、点（避免切开 iter_0.5、v1.2.3 这类标识），
# 后面紧跟 % 的是百分比，不算
NUMBER_RE = re.compile(
    r"(?<![\w.])[-+]?(?:\d+\.\d+(?:[eE][-+]?\d+)?|\d+[eE][-+]?\d+)(?![\w.]|\s*%)")
_FENCE_RE = re.compile(r"^\s*```")
_INLINE_CODE_RE = re.compile(r"`[^`]*`")


@dataclass(frozen=True)
class Claim:
    """数据表的一行：某个来源（<实验 id>/baseline 或 iter_N）的某个指标是这个值。
    line_no 是在 analysis.md 里的行号。"""

    source: str
    metric: str
    value: float
    line_no: int


@dataclass(frozen=True)
class ProseNumber:
    token: str
    value: float
    line_no: int


def validate_analysis(text: str) -> list[str]:
    """形状校验：三节齐全、数据表存在且至少一行能解析。空清单表示合约。"""
    problems = [f"缺少小节 {h}" for h in REQUIRED_HEADINGS if not _has_heading(text, h)]
    if _has_heading(text, DATA_HEADING):
        claims, table_problems = parse_claims(text)
        problems += table_problems
        if not claims and not table_problems:
            problems.append(f"{DATA_HEADING} 里没有数据表，或表里一行都没有")
    return problems


def parse_claims(text: str) -> tuple[list[Claim], list[str]]:
    """解析 `## 数据` 节里的表。返回（行, 问题）：坏行报问题不跳过，跳过等于放过编造。"""
    claims: list[Claim] = []
    problems: list[str] = []
    header_seen = False
    for line_no, line in _section_lines(text, DATA_HEADING):
        stripped = line.strip()
        if not stripped.startswith("|"):
            continue
        cells = [c.strip() for c in stripped.strip("|").split("|")]
        if not header_seen:
            if [c.lower() for c in cells[:3]] == [c.lower() for c in TABLE_COLUMNS]:
                header_seen = True
            else:
                expected = " | ".join(TABLE_COLUMNS)
                problems.append(f"第 {line_no} 行：数据表表头必须是 | {expected} |")
                return claims, problems
            continue
        if all(set(c) <= set(":- ") for c in cells):
            continue  # 表头下面的分隔线
        if len(cells) < 3:
            problems.append(f"第 {line_no} 行：数据表要三列，得到 {len(cells)} 列")
            continue
        source, metric, raw = cells[:3]
        if not SOURCE_RE.match(source):
            problems.append(f"第 {line_no} 行：来源列要形如 experiment/<n>/baseline 或 "
                            f"experiment/<n>/iter_N，得到 {source!r}")
            continue
        try:
            value = float(raw)
        except ValueError:
            problems.append(f"第 {line_no} 行：值列不是数字：{raw!r}")
            continue
        claims.append(Claim(source=source, metric=metric, value=value, line_no=line_no))
    return claims, problems


def prose_numbers(text: str) -> list[ProseNumber]:
    """正文里带小数点或指数的数：不含数据表、代码块与行内代码。验证能力拿它对照数据表。"""
    found: list[ProseNumber] = []
    in_fence = False
    data_lines = {n for n, _ in _section_lines(text, DATA_HEADING)}
    for line_no, line in enumerate(text.splitlines(), start=1):
        if _FENCE_RE.match(line):
            in_fence = not in_fence
            continue
        if in_fence or line_no in data_lines:
            continue
        for match in NUMBER_RE.finditer(_INLINE_CODE_RE.sub("", line)):
            token = match.group()
            found.append(ProseNumber(token=token, value=float(token), line_no=line_no))
    return found


def _has_heading(text: str, heading: str) -> bool:
    return any(line.strip() == heading for line in text.splitlines())


def _section_lines(text: str, heading: str) -> list[tuple[int, str]]:
    """某个二级标题下、直到下一个二级标题之前的行（带行号）。"""
    lines: list[tuple[int, str]] = []
    inside = False
    for line_no, line in enumerate(text.splitlines(), start=1):
        stripped = line.strip()
        if stripped.startswith("## "):
            inside = stripped == heading
            continue
        if inside:
            lines.append((line_no, line))
    return lines


def check_session_outcome(output_dir: Path, result: RunResult, *, doc_name: str,
                          log_dirname: str) -> list[Claim]:
    """写分析的两颗能力共用的事后判定，顺序固定：先判越界，再判会话死没死，最后判产物形状。
    文件一律留着当证据；不合就 CapabilityFailed。"""
    outside = [f for f in result.changed_files
               if f != doc_name and not f.startswith(f"{log_dirname}/")]
    if outside:
        raise CapabilityFailed(f"执行层改了 {doc_name} 之外的文件：{', '.join(sorted(outside))}")
    if result.timed_out or result.exit_code != 0:
        tail = result.stdout_tail.strip().splitlines()
        why = "超时" if result.timed_out else f"退出码 {result.exit_code}"
        raise CapabilityFailed(f"执行层会话没走完（{why}）：{tail[-1] if tail else '无输出'}")
    doc = Path(output_dir) / doc_name
    if not doc.is_file():
        raise CapabilityFailed(f"执行层没有写出 {doc_name}")
    text = doc.read_text(encoding="utf-8")
    problems = validate_analysis(text)
    if problems:
        raise CapabilityFailed(f"{doc_name} 不合约：" + "；".join(problems))
    claims, _ = parse_claims(text)
    return claims
