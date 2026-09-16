"""工作流文件：仓里预装的那几条读得出来、能力步骤和清单对得上；坏文件当场报，不静默跳过。"""

from __future__ import annotations

import pytest

from framework.capabilities import discover
from framework.chat.guide import REPO_ROOT
from framework.contracts import workflows

GOOD = """\
name: w
title: 一条
summary: >
  两行的
  摘要
steps:
  - by: 人
    does: 说清楚
  - by: 助理
    does: 接任务
    cap: design
  - by: 人
    does: 发布
    key: publish
"""


def catalog():
    return {name: module.DESCRIPTOR for name, module in discover().items()}


def test_shipped_workflows_load_and_connect():
    found = workflows.load_workflows(workflows.workflows_root(REPO_ROOT))
    assert [wf.name for wf in found] == ["auto-research", "intake"]
    for wf in found:
        assert workflows.workflow_problems(wf, catalog()) == [], wf.name
    intake = next(wf for wf in found if wf.name == "intake")
    assert intake.caps == ["design", "baseline"]
    assert [s.key for s in intake.steps if s.key] == ["publish"]
    auto = next(wf for wf in found if wf.name == "auto-research")
    assert auto.caps == ["start", "experiment", "analysis", "verify"]
    assert auto.assumes == ("harness/", "code/", "run_0/")  # 从基线之后开始，前提写在文件里


def test_load_and_describe(tmp_path):
    (tmp_path / "w.yaml").write_text(GOOD, encoding="utf-8")
    found = workflows.load_workflows(tmp_path)
    assert len(found) == 1 and found[0].summary == "两行的 摘要"
    described = workflows.describe(found, catalog())
    assert described[0]["steps"][1] == {"by": "助理", "does": "接任务", "cap": "design",
                                        "key": None}
    assert described[0]["problems"] == []
    assert workflows.load_workflows(tmp_path / "nowhere") == []


def test_bad_shapes_are_named(tmp_path):
    cases = {
        "name 要等于文件名": GOOD.replace("name: w", "name: other"),
        "缺 title": GOOD.replace("title: 一条\n", ""),
        "缺 summary": GOOD.replace("summary: >\n  两行的\n  摘要\n", ""),
        "by 要是「助理」": GOOD.replace("- by: 助理\n    does: 接任务",
                                      "- by: 人\n    does: 接任务"),
        "by 要是「人」": GOOD.replace("- by: 人\n    does: 发布", "- by: 助理\n    does: 发布"),
        "assumes 要是路径列表": GOOD.replace("steps:", "assumes: harness/\nsteps:"),
    }
    for message, text in cases.items():
        (tmp_path / "w.yaml").write_text(text, encoding="utf-8")
        with pytest.raises(workflows.WorkflowInvalid, match=message):
            workflows.load_workflows(tmp_path)


def test_unknown_capability_and_broken_order_are_problems(tmp_path):
    (tmp_path / "w.yaml").write_text(GOOD.replace("cap: design", "cap: nope"), encoding="utf-8")
    [wf] = workflows.load_workflows(tmp_path)
    assert "没有这些能力" in workflows.workflow_problems(wf, catalog())[0]
    (tmp_path / "w.yaml").write_text(
        GOOD.replace("cap: design", "cap: verify"), encoding="utf-8")
    [wf] = workflows.load_workflows(tmp_path)
    problems = workflows.workflow_problems(wf, catalog())
    assert problems and "verify" in problems[0]
