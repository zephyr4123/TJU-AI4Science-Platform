"""账本模块的单测：与内环解耦，只用 tmp_path 里的一个小 git 仓。

账本是唯一活过 `git reset --hard` 的记录，所以这里重点验两件事：
拿不到的值写 `-` 不写 0；每一行都能跟 git 对上账（P-3）。
"""

from __future__ import annotations

import math
from pathlib import Path

import pytest

from framework.memory import ledger
from framework.run import gitwork


def row(**kw) -> ledger.LedgerRow:
    base = dict(iter=1, commit="-", parent="-", metric=0.5, direction="minimize",
                elapsed_s=1.25, seed=42, status="keep", sigma=0.005, harness_sha="ab" * 32,
                note="baseline", cost_usd=0.01, executor_s=2.0)
    return ledger.LedgerRow(**{**base, **kw})


def test_append_writes_header_once_and_reads_back(tmp_path):
    path = tmp_path / "ledger.tsv"
    ledger.append(path, row(iter=1))
    ledger.append(path, row(iter=2, status="discard", metric=0.4))
    lines = path.read_text(encoding="utf-8").splitlines()
    assert lines[0].split("\t") == list(ledger.COLUMNS)
    assert len(lines) == 3
    rows = ledger.read(path)
    assert [r.iter for r in rows] == [1, 2]
    assert rows[1].status == "discard" and rows[1].metric == pytest.approx(0.4)


def test_missing_values_are_dashes_not_zero(tmp_path):
    path = tmp_path / "ledger.tsv"
    ledger.append(path, row(iter=1, metric=None, sigma=None, status="crash", commit=""))
    line = path.read_text(encoding="utf-8").splitlines()[1].split("\t")
    assert line[1] == "-" and line[3] == "-" and line[8] == "-"
    back = ledger.read(path)[0]
    assert back.metric is None and back.sigma is None


def test_nan_cost_survives_roundtrip_and_is_excluded_from_total(tmp_path):
    path = tmp_path / "ledger.tsv"
    ledger.append(path, row(iter=1, cost_usd=math.nan, status="interrupted"))
    ledger.append(path, row(iter=2, cost_usd=0.25))
    assert math.isnan(ledger.read(path)[0].cost_usd)
    assert ledger.total_cost(path) == pytest.approx(0.25)


def test_note_with_tabs_is_flattened(tmp_path):
    path = tmp_path / "ledger.tsv"
    ledger.append(path, row(note="lr 0.04\t→\n0.045"))
    assert len(path.read_text(encoding="utf-8").splitlines()[1].split("\t")) == len(ledger.COLUMNS)
    assert ledger.read(path)[0].note == "lr 0.04 → 0.045"


def test_unknown_status_is_rejected(tmp_path):
    with pytest.raises(AssertionError):
        ledger.append(tmp_path / "ledger.tsv", row(status="差不多得了"))


def test_read_missing_file_is_empty(tmp_path):
    assert ledger.read(tmp_path / "没有这个文件.tsv") == []


def test_unknown_elapsed_and_cost_round_trip_as_none(tmp_path):
    """harness 没跑起来的行（noop / readonly_violated / interrupted）三列都是未知。"""
    path = tmp_path / "ledger.tsv"
    ledger.append(path, row(iter=1, status="noop", metric=None,
                            elapsed_s=None, cost_usd=None, executor_s=None))
    line = path.read_text(encoding="utf-8").splitlines()[1].split("\t")
    assert line[5] == "-" and line[11] == "-" and line[12] == "-"
    back = ledger.read(path)[0]
    assert back.elapsed_s is None and back.cost_usd is None and back.executor_s is None
    assert ledger.total_cost(path) == 0.0, "未知的成本不计入总额，也不许把总额变成 NaN"


def test_nan_elapsed_round_trips(tmp_path):
    path = tmp_path / "ledger.tsv"
    ledger.append(path, row(iter=1, status="interrupted", elapsed_s=math.nan))
    assert math.isnan(ledger.read(path)[0].elapsed_s)


def test_broken_line_raises_rather_than_being_skipped(tmp_path):
    path = tmp_path / "ledger.tsv"
    ledger.append(path, row())
    with path.open("a", encoding="utf-8") as fh:
        fh.write("2\t只有两列\n")
    with pytest.raises(ValueError):
        ledger.read(path)


# ── 与 git 对账 ─────────────────────────────────────────────────────────
def _repo(tmp_path: Path) -> Path:
    work = tmp_path / "work"
    (work / "code").mkdir(parents=True)
    (work / "code" / "train.py").write_text("print(0)\n", encoding="utf-8")
    gitwork.init_repo(work, "基线")
    return work


def _commit(work: Path, text: str) -> str:
    (work / "code" / "train.py").write_text(text, encoding="utf-8")
    sha = gitwork.commit_paths(work, ["code"], "改一行")
    assert sha is not None
    return sha


def test_reconcile_accepts_keep_on_branch_and_discard_in_attempts(tmp_path):
    work = _repo(tmp_path)
    base = gitwork.head(work)
    kept = _commit(work, "print(1)\n")
    dropped = _commit(work, "print(2)\n")
    gitwork.keep_attempt(work, 2, dropped)
    gitwork.revert_to(work, kept)

    path = tmp_path / "ledger.tsv"
    ledger.append(path, row(iter=1, commit=kept, parent=base, status="keep"))
    ledger.append(path, row(iter=2, commit=dropped, parent=kept, status="discard"))
    assert ledger.reconcile(path, work) == []
    assert gitwork.is_ancestor(work, kept) and not gitwork.is_ancestor(work, dropped)


def test_reconcile_reports_unknown_commit_and_lost_attempt(tmp_path):
    work = _repo(tmp_path)
    dropped = _commit(work, "print(2)\n")
    gitwork.revert_to(work, gitwork.rev_parse(work, "HEAD~1"))  # 不留档就 reset
    path = tmp_path / "ledger.tsv"
    ledger.append(path, row(iter=1, commit=dropped, status="discard"))
    ledger.append(path, row(iter=2, commit="0" * 40, status="keep"))
    problems = ledger.reconcile(path, work)
    assert any("refs/attempts" in p for p in problems)
    assert any("找不到" in p for p in problems)


def test_reconcile_flags_a_broken_keep_parent_chain(tmp_path):
    """keep 行的 parent 必须接上一条 keep；写成自己就是结算顺序错了（H2 的病根）。"""
    work = _repo(tmp_path)
    base = gitwork.head(work)
    first = _commit(work, "print(1)\n")
    second = _commit(work, "print(2)\n")

    broken = tmp_path / "broken.tsv"
    ledger.append(broken, row(iter=1, commit=first, parent=base, status="keep"))
    ledger.append(broken, row(iter=2, commit=second, parent=second, status="keep"))
    problems = ledger.reconcile(broken, work)
    assert any("parent" in p and "iter 2" in p for p in problems), problems

    good = tmp_path / "good.tsv"
    ledger.append(good, row(iter=1, commit=first, parent=base, status="keep"))
    ledger.append(good, row(iter=2, commit=second, parent=first, status="keep"))
    assert ledger.reconcile(good, work) == []


def test_reconcile_flags_a_first_keep_row_that_misses_the_baseline(tmp_path):
    work = _repo(tmp_path)
    first = _commit(work, "print(1)\n")
    path = tmp_path / "ledger.tsv"
    ledger.append(path, row(iter=1, commit=first, parent="0" * 40, status="keep"))
    assert any("基线" in p for p in ledger.reconcile(path, work))


def test_root_commit_is_the_baseline(tmp_path):
    work = _repo(tmp_path)
    base = gitwork.head(work)
    _commit(work, "print(1)\n")
    assert gitwork.root_commit(work) == base


def test_reconcile_flags_non_increasing_iters(tmp_path):
    work = _repo(tmp_path)
    path = tmp_path / "ledger.tsv"
    ledger.append(path, row(iter=2, status="noop"))
    ledger.append(path, row(iter=2, status="noop"))
    assert any("递增" in p for p in ledger.reconcile(path, work))


def test_commit_paths_returns_none_when_nothing_changed(tmp_path):
    work = _repo(tmp_path)
    assert gitwork.commit_paths(work, ["code"], "空提交") is None


def test_git_failure_is_not_swallowed(tmp_path):
    work = _repo(tmp_path)
    with pytest.raises(RuntimeError):
        gitwork.git(work, "checkout", "根本没有这个分支")
