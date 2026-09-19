"""验证能力：零模型、确定性，所以每条判据都能用一份构造出来的分析证明。

A-10 是核心：编一个数字进去，必须 FAIL。其余是边界（容差、表外正文数、不存在的来源、
账本被动过、没有分析）与产物合约（报告过 schema）。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from framework.capabilities import verify
from framework.contracts.capability import CapabilityFailed, Inputs, Ports
from framework.experiment import layout
from framework.experiment.report import read_report
from framework.workspace import outputs
from tests.fixtures import packs_factory as pf
from tests.fixtures import runs_factory as rf


@pytest.fixture(scope="module")
def made(tmp_path_factory) -> tuple[Path, pf.Pack]:
    return rf.make_run(tmp_path_factory.mktemp("verify"))


def _verify(pack: pf.Pack, analysis_dir: Path, **params) -> tuple[str, Path]:
    """开一次验证产出、跑验证；返回结论行与产出目录。"""
    out, _ = outputs.open_output(pack.workspace, "verification", title="t", by="verify",
                                 inputs=[f"analysis/{analysis_dir.name}", "experiment/1"],
                                 params={}, flow=None, step=None, requirement=1, chat_id=None)
    run_dir = pack.workspace.root / "experiment" / "1"
    inputs = Inputs(pack.workspace.root, (analysis_dir, run_dir),
                    (f"analysis/{analysis_dir.name}", "experiment/1"))
    return verify.run(out, inputs, Ports(), **params), out


def _report(out: Path) -> dict:
    return read_report(out / "report.json")


def _failed_names(out: Path) -> list[str]:
    return [c["name"] for c in _report(out)["checks"] if not c["passed"]]


def test_consistent_analysis_passes(made):
    run_dir, pack = made
    doc = rf.write_analysis(pack, rf.good_analysis(run_dir))
    line, out = _verify(pack, doc)
    assert line == "verify PASS\tchecks=4\tpath=report.json"
    report = _report(out)
    assert report["status"] == "PASS" and report["analysis"] == f"analysis/{doc.name}"
    assert [c["name"] for c in report["checks"]] == [
        "analysis_present", "numbers_traceable", "prose_numbers_in_table",
        "ledger_reconciled:experiment/1"]
    assert any("核对 4 个值" in d for d in report["checks"][1]["details"])


def test_a10_fabricated_table_value_fails(made):
    run_dir, pack = made
    best = repr(rf.metrics_of(run_dir)["iter_3"]["val_mse"])
    text = rf.good_analysis(run_dir).replace(f"| experiment/1/iter_3 | val_mse | {best} |",
                                             "| experiment/1/iter_3 | val_mse | 0.0005 |")
    doc = rf.write_analysis(pack, text)
    with pytest.raises(CapabilityFailed, match="verify FAIL 2/4：numbers_traceable") as exc:
        _verify(pack, doc)
    out = pack.workspace.root / "verification" / str(max(
        int(p.name) for p in (pack.workspace.root / "verification").iterdir()))
    assert _report(out)["status"] == "FAIL" and "report.json" in str(exc.value)
    # 表里的值编了，正文引用它的那句也就对不上表了：两项一起 FAIL，各说各的行号
    assert _failed_names(out) == ["numbers_traceable", "prose_numbers_in_table"]
    detail = _report(out)["checks"][1]["details"][0]
    assert "experiment/1/iter_3 的 val_mse 声称 0.0005" in detail and "超出 1% 容差" in detail


def test_fabricated_prose_number_fails(made):
    run_dir, pack = made
    text = rf.good_analysis(run_dir).replace("共 3 轮", "共 3 轮，另外 0.1234 也不错")
    doc = rf.write_analysis(pack, text)
    with pytest.raises(CapabilityFailed, match="prose_numbers_in_table"):
        _verify(pack, doc)


def test_unknown_source_or_metric_fails(made):
    run_dir, pack = made
    text = rf.good_analysis(run_dir).replace(
        "## 证伪", "| experiment/1/iter_9 | val_mse | 0.1 |\n\n## 证伪", 1)
    doc = rf.write_analysis(pack, text)
    with pytest.raises(CapabilityFailed, match="experiment/1/iter_9 没有指标 val_mse"):
        _verify(pack, doc)


def test_tolerance_is_relative_and_adjustable(made):
    run_dir, pack = made
    best = rf.metrics_of(run_dir)["iter_3"]["val_mse"]
    base = rf.good_analysis(run_dir)
    near = rf.write_analysis(pack, base.replace(repr(best), repr(best * 1.005)))
    assert _verify(pack, near)[0].startswith("verify PASS")
    far = rf.write_analysis(pack, base.replace(repr(best), repr(best * 1.02)))
    with pytest.raises(CapabilityFailed, match="numbers_traceable"):
        _verify(pack, far)
    assert _verify(pack, far, tolerance=0.05)[0].startswith("verify PASS")
    with pytest.raises(AssertionError, match="tolerance"):
        _verify(pack, far, tolerance=1.5)


def test_missing_analysis_fails_with_a_single_check(made):
    run_dir, pack = made
    doc = rf.write_analysis(pack, rf.good_analysis(run_dir))
    (doc / "analysis.md").unlink()
    with pytest.raises(CapabilityFailed, match="analysis_present"):
        _verify(pack, doc)
    out = pack.workspace.root / "verification" / str(max(
        int(p.name) for p in (pack.workspace.root / "verification").iterdir()))
    report = _report(out)
    assert report["status"] == "FAIL" and len(report["checks"]) == 1


def test_inputs_must_include_the_analysis_and_its_experiments(made):
    run_dir, pack = made
    doc = rf.write_analysis(pack, rf.good_analysis(run_dir))
    out, _ = outputs.open_output(pack.workspace, "verification", title="t", by="verify",
                                 inputs=[], params={}, flow=None, step=None, requirement=1,
                                 chat_id=None)
    with pytest.raises(CapabilityFailed, match="要且只要一个「analysis」"):
        verify.run(out, Inputs(pack.workspace.root), Ports())
    with pytest.raises(CapabilityFailed, match="--from experiment/<n>"):
        verify.run(out, Inputs(pack.workspace.root, (doc,), (f"analysis/{doc.name}",)), Ports())


def test_tampered_ledger_fails(tmp_path):
    run_dir, pack = rf.make_run(tmp_path)
    doc = rf.write_analysis(pack, rf.good_analysis(run_dir))
    ledger_path = layout.ledger(run_dir)
    lines = ledger_path.read_text(encoding="utf-8").splitlines()
    cells = lines[-1].split("\t")
    cells[1] = "0" * 40
    lines[-1] = "\t".join(cells)
    ledger_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    with pytest.raises(CapabilityFailed, match="verify FAIL 1/4：ledger_reconciled:experiment/1"):
        _verify(pack, doc)


def test_report_is_valid_json_under_schema(made):
    run_dir, pack = made
    doc = rf.write_analysis(pack, rf.good_analysis(run_dir))
    _, out = _verify(pack, doc)
    report = json.loads((out / "report.json").read_text(encoding="utf-8"))
    assert set(report) == {"status", "generated_at", "analysis", "checks"}
