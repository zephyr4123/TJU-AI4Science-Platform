"""验证能力：零模型、确定性，所以每条判据都能用一份构造出来的分析证明。

A-10 是核心：编一个数字进去，必须 FAIL。其余是边界（容差、表外正文数、不存在的 run、
账本被动过、没有分析）与产物合约（报告过 schema、重跑轮转）。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from framework.capabilities import verify
from framework.contracts.capability import CapabilityFailed, Ports
from framework.contracts.report import read_report
from framework.run import layout
from tests.fixtures import runs_factory as rf


@pytest.fixture(scope="module")
def run_dir(tmp_path_factory) -> Path:
    return rf.make_run(tmp_path_factory.mktemp("verify"))


def _report(run_dir: Path) -> dict:
    return read_report(layout.verify_report(run_dir))


def _failed_names(run_dir: Path) -> list[str]:
    return [c["name"] for c in _report(run_dir)["checks"] if not c["passed"]]


def test_consistent_analysis_passes(run_dir):
    rf.write_analysis(run_dir, rf.good_analysis(run_dir))
    line = verify.run(run_dir, Ports())
    assert line == "verify PASS\tchecks=4\tpath=verify/report.json"
    report = _report(run_dir)
    assert report["status"] == "PASS"
    assert [c["name"] for c in report["checks"]] == [
        "analysis_present", "numbers_traceable", "prose_numbers_in_table", "ledger_reconciled"]
    assert any("核对 4 个值" in d for d in report["checks"][1]["details"])


def test_a10_fabricated_table_value_fails(run_dir):
    best = repr(rf.metrics_of(run_dir)["run_3"]["val_mse"])
    text = rf.good_analysis(run_dir).replace(f"| run_3 | val_mse | {best} |",
                                             "| run_3 | val_mse | 0.0005 |")
    rf.write_analysis(run_dir, text)
    with pytest.raises(CapabilityFailed, match="verify FAIL 2/4：numbers_traceable"):
        verify.run(run_dir, Ports())
    assert _report(run_dir)["status"] == "FAIL"
    # 表里的值编了，正文引用它的那句也就对不上表了：两项一起 FAIL，各说各的行号
    assert _failed_names(run_dir) == ["numbers_traceable", "prose_numbers_in_table"]
    detail = _report(run_dir)["checks"][1]["details"][0]
    assert "run_3 的 val_mse 声称 0.0005" in detail and "超出 1% 容差" in detail


def test_fabricated_prose_number_fails(run_dir):
    text = rf.good_analysis(run_dir).replace("共 3 轮", "共 3 轮，另外 0.1234 也不错")
    rf.write_analysis(run_dir, text)
    with pytest.raises(CapabilityFailed, match="prose_numbers_in_table"):
        verify.run(run_dir, Ports())
    assert _failed_names(run_dir) == ["prose_numbers_in_table"]
    assert any("0.1234 不在数据表里" in d
               for d in _report(run_dir)["checks"][2]["details"])


def test_unknown_run_or_metric_fails(run_dir):
    text = rf.good_analysis(run_dir).replace("## 证伪", "| run_9 | val_mse | 0.1 |\n\n## 证伪", 1)
    rf.write_analysis(run_dir, text)
    with pytest.raises(CapabilityFailed, match="run_9 没有指标 val_mse"):
        verify.run(run_dir, Ports())


def test_tolerance_is_relative_and_adjustable(run_dir):
    best = rf.metrics_of(run_dir)["run_3"]["val_mse"]
    base = rf.good_analysis(run_dir)
    near = base.replace(repr(best), repr(best * 1.005))
    rf.write_analysis(run_dir, near)
    assert verify.run(run_dir, Ports()).startswith("verify PASS")
    far = base.replace(repr(best), repr(best * 1.02))
    rf.write_analysis(run_dir, far)
    with pytest.raises(CapabilityFailed, match="numbers_traceable"):
        verify.run(run_dir, Ports())
    assert verify.run(run_dir, Ports(), tolerance=0.05).startswith("verify PASS")
    with pytest.raises(AssertionError, match="tolerance"):
        verify.run(run_dir, Ports(), tolerance=1.5)


def test_missing_analysis_fails_with_a_single_check(run_dir):
    doc = layout.analysis_doc(run_dir)
    saved = doc.read_text(encoding="utf-8")
    doc.unlink()
    try:
        with pytest.raises(CapabilityFailed, match="analysis_present"):
            verify.run(run_dir, Ports())
        report = _report(run_dir)
        assert report["status"] == "FAIL" and len(report["checks"]) == 1
    finally:
        doc.write_text(saved, encoding="utf-8")


def test_rerun_rotates_previous_report(run_dir):
    rf.write_analysis(run_dir, rf.good_analysis(run_dir))
    verify.run(run_dir, Ports())
    verify.run(run_dir, Ports())
    versions = sorted(p.name for p in run_dir.iterdir() if p.name.startswith("verify_v"))
    assert versions and (run_dir / versions[-1] / "report.json").is_file()


def test_tampered_ledger_fails(tmp_path):
    run_dir = rf.make_run(tmp_path)
    rf.write_analysis(run_dir, rf.good_analysis(run_dir))
    ledger_path = layout.ledger(run_dir)
    lines = ledger_path.read_text(encoding="utf-8").splitlines()
    cells = lines[-1].split("\t")
    cells[1] = "0" * 40
    lines[-1] = "\t".join(cells)
    ledger_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    with pytest.raises(CapabilityFailed, match="verify FAIL 1/4：ledger_reconciled"):
        verify.run(run_dir, Ports())


def test_report_is_valid_json_under_schema(run_dir):
    rf.write_analysis(run_dir, rf.good_analysis(run_dir))
    verify.run(run_dir, Ports())
    doc = json.loads(layout.verify_report(run_dir).read_text(encoding="utf-8"))
    assert set(doc) == {"status", "generated_at", "analysis", "checks"}
