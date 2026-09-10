"""账本 `experiment/ledger.tsv`：每轮一行，活过 reset，不进 git（纲领 workflow.md §2）。

账本是唯一活过 `git reset --hard` 的那份记录，所以它必须是纯追加的文本、能被人直接
读、也能跟 git 逐行对账（`reconcile`）。为什么不进 git：它记的正是 git 里被销毁的
东西，跟着仓一起被 reset 就等于没记。

拿不到的值一律写 `-`（未知），绝不写 0：0 是一个成绩，未知不是（P-7）。
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path

from framework import gitwork

COLUMNS = ("iter", "commit", "parent", "metric", "direction", "elapsed_s", "seed", "status",
           "sigma", "harness_sha", "note", "cost_usd", "executor_s")

# keep / discard 是裁决，其余是这一轮没能产生可比成绩的原因（六类失败 + noop + interrupted）。
STATUSES = frozenset({"keep", "discard", "noop", "readonly_violated", "timeout",
                      "missing_dependency", "crash", "no_results", "nan_metric", "interrupted",
                      "executor_failed"})
MISSING = "-"


@dataclass
class LedgerRow:
    """一行账。

    `elapsed_s` / `cost_usd` / `executor_s` 都可以是 None（写成 `-`）或 NaN：harness 压根
    没跑起来的那几种行（noop、readonly_violated、interrupted）根本没有耗时与成本可言，
    它们是**未知**，不是 0（P-7）。
    """

    iter: int
    commit: str
    parent: str
    metric: float | None
    direction: str
    elapsed_s: float | None
    seed: int
    status: str
    sigma: float | None
    harness_sha: str
    note: str
    cost_usd: float | None
    executor_s: float | None


def _fmt(value: float | None) -> str:
    if value is None:
        return MISSING
    # NaN 原样写成 nan：它是"未知成本"的约定值（backends 的成本在超时时就是 NaN）
    return f"{value:.12g}"


def _parse(token: str) -> float | None:
    return None if token == MISSING else float(token)


def _one_line(text: str) -> str:
    """note 里出现制表符或换行会把 TSV 撕开，这里压平。"""
    return " ".join(str(text).split())


def append(path: Path, row: LedgerRow) -> None:
    """追加一行；文件不存在时先写表头。"""
    assert row.status in STATUSES, f"未知的 status {row.status!r}，允许的是 {sorted(STATUSES)}"
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = [str(row.iter), row.commit or MISSING, row.parent or MISSING, _fmt(row.metric),
              row.direction, _fmt(row.elapsed_s), str(row.seed), row.status, _fmt(row.sigma),
              row.harness_sha or MISSING, _one_line(row.note), _fmt(row.cost_usd),
              _fmt(row.executor_s)]
    assert len(fields) == len(COLUMNS), "列数与 COLUMNS 对不上"
    with path.open("a", encoding="utf-8") as fh:
        if path.stat().st_size == 0:
            fh.write("\t".join(COLUMNS) + "\n")
        fh.write("\t".join(fields) + "\n")


def read(path: Path) -> list[LedgerRow]:
    """读回全部行；文件不存在按空账本处理（还没跑过第一轮）。"""
    path = Path(path)
    if not path.is_file():
        return []
    rows: list[LedgerRow] = []
    for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip() or line.startswith(COLUMNS[0] + "\t"):
            continue
        parts = line.split("\t")
        if len(parts) != len(COLUMNS):
            raise ValueError(f"{path}:{lineno}: 期望 {len(COLUMNS)} 列，实际 {len(parts)} 列")
        # 三个耗时 / 成本列统一走 _parse：它们既可能是 `-`（未知）也可能是 nan（量过但没拿到）
        rows.append(LedgerRow(
            iter=int(parts[0]), commit=parts[1], parent=parts[2], metric=_parse(parts[3]),
            direction=parts[4], elapsed_s=_parse(parts[5]), seed=int(parts[6]), status=parts[7],
            sigma=_parse(parts[8]), harness_sha=parts[9], note=parts[10],
            cost_usd=_parse(parts[11]), executor_s=_parse(parts[12])))
    return rows


def total_cost(path: Path) -> float:
    """已花的成本。未知（None / NaN）不计入求和，否则一条未知会把总额变成 NaN。"""
    return sum(r.cost_usd for r in read(path)
               if r.cost_usd is not None and not math.isnan(r.cost_usd))


def reconcile(path: Path, work: Path, baseline: str | None = None) -> list[str]:
    """账本 × git 对账，返回问题清单；空清单表示对得上（P-3 的机器判据）。

    规则：每行的 commit 必须在仓里找得到；keep 行必须在当前分支上（它就是 best 那条线），
    其余带 commit 的行必须在 `refs/attempts/` 下留着——被 reset 不等于可以消失。

    keep 行还要首尾相接：第一条 keep 的 parent 是基线 commit，之后每条 keep 的 parent 是
    上一条 keep 的 commit。best 只沿着 keep 往前走，链断了就说明有一次前进没被记下来、
    或者 parent 记错了（H2 的病根：结算完再读 best_commit，会把自己写成自己的 parent）。
    `baseline` 缺省从 git 的首个 commit 取（调用方手里有 checkpoint 时也可以直接传）。
    """
    problems: list[str] = []
    attempts = set(gitwork.attempt_refs(work).values())
    expected_parent = baseline or gitwork.root_commit(work)
    previous = 0
    for row in read(path):
        if row.iter <= previous:
            problems.append(f"账本 iter 必须递增，第 {row.iter} 行出现在 {previous} 之后")
        previous = row.iter
        if row.commit == MISSING:
            continue
        sha = gitwork.rev_parse(work, row.commit)
        if sha is None:
            problems.append(f"iter {row.iter}: commit {row.commit} 在 {work} 的 git 里找不到")
            continue
        on_branch = gitwork.is_ancestor(work, sha)
        if row.status == "keep" and not on_branch:
            problems.append(f"iter {row.iter}: keep 行的 commit {row.commit} 不在分支上")
        if row.status != "keep" and sha not in attempts:
            problems.append(
                f"iter {row.iter}: {row.status} 行的 commit {row.commit} 不在 refs/attempts/ 下"
            )
        if row.status == "keep" and expected_parent is not None:
            if row.parent != expected_parent:
                problems.append(
                    f"iter {row.iter}: keep 行的 parent 期望 {expected_parent}"
                    f"（上一条 keep 的 commit，首条是基线），实际 {row.parent}"
                )
            expected_parent = row.commit
    return problems
