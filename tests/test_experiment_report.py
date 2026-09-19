"""report.json 契约：写报告的与读报告的用同一把尺子，不合约就当没有报告。"""

from __future__ import annotations

import json

import pytest

from framework.experiment.report import read_report, validate_report

GOOD = {"status": "PASS", "generated_at": "2026-09-15T00:00:00+00:00",
        "analysis": "analysis/analysis.md",
        "checks": [{"name": "analysis_present", "passed": True, "details": ["ok"]}]}


def test_good_report_passes():
    assert validate_report(GOOD) == []


@pytest.mark.parametrize("patch", [
    {"status": "MAYBE"}, {"checks": []}, {"extra": 1},
    {"checks": [{"name": "Bad Name", "passed": True, "details": []}]},
    {"checks": [{"name": "x", "passed": "yes", "details": []}]},
])
def test_bad_reports_are_rejected(patch):
    assert validate_report({**GOOD, **patch})


def test_read_report_raises_with_path_and_reason(tmp_path):
    path = tmp_path / "report.json"
    path.write_text(json.dumps({**GOOD, "status": "MAYBE"}), encoding="utf-8")
    with pytest.raises(ValueError, match="report.json 不合 schema"):
        read_report(path)
    path.write_text(json.dumps(GOOD), encoding="utf-8")
    assert read_report(path)["status"] == "PASS"
