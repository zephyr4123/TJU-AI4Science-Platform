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
    # quick-look 是协调 agent 在实验 #55 / #56 里自己拼出来存下的第三条（外层 #56）
    assert [wf.name for wf in found] == ["auto-research", "intake", "quick-look"]
    for wf in found:
        assert workflows.workflow_problems(wf, catalog()) == [], wf.name
    intake = next(wf for wf in found if wf.name == "intake")
    assert intake.caps == ["init", "design", "baseline"]  # 起任务包是第一颗按钮（外层 #60）
    assert [s.key for s in intake.steps if s.key] == ["publish"]
    auto = next(wf for wf in found if wf.name == "auto-research")
    assert auto.caps == ["start", "experiment", "analysis", "verify"]
    assert auto.assumes == ("harness/", "code/", "run_0/")  # 从基线之后开始，前提写在文件里
    quick = next(wf for wf in found if wf.name == "quick-look")
    assert quick.steps[1].with_ == {"max_iters": 3}  # 「跑 3 轮」不只是句人话，按钮参数也在


def test_shipped_workflows_cover_stages_and_are_looked_up_from_capabilities():
    found = workflows.load_workflows(workflows.workflows_root(REPO_ROOT))
    described = {d["name"]: d for d in workflows.describe(found, catalog())}
    assert described["intake"]["covers"] == ["设计"] and described["intake"]["remarks"] == []
    assert described["auto-research"]["covers"] == ["实验", "分析", "验证"]
    assert described["auto-research"]["remarks"] == []
    assert described["quick-look"]["covers"] == ["实验", "分析"]
    assert "没有验证" in described["quick-look"]["remarks"][0]  # 它自己选的不验证，机器提醒一句
    # 反查：能力上不写"我属于哪条流"，是从工作流文件算回来的
    assert workflows.used_by(found) == {
        "start": ["auto-research", "quick-look"], "experiment": ["auto-research", "quick-look"],
        "analysis": ["auto-research", "quick-look"], "verify": ["auto-research"],
        "init": ["intake"], "design": ["intake"], "baseline": ["intake"]}


def test_step_with_params_are_checked_against_the_descriptor(tmp_path):
    """外层 #63：`with:` 的键要是那颗能力的 Param、值要是那个类型；非能力步骤不许有。"""
    good = GOOD.replace("    cap: design\n", "    cap: design\n    with: {feedback: '@f.md'}\n")
    (tmp_path / "w.yaml").write_text(good, encoding="utf-8")
    [wf] = workflows.load_workflows(tmp_path)
    assert wf.steps[1].with_ == {"feedback": "@f.md"} and wf.to_dict()["steps"][1]["with"]
    assert workflows.workflow_problems(wf, catalog()) == []
    bad = GOOD.replace("    cap: design\n", "    cap: design\n    with: {nope: 1, feedback: 3}\n")
    (tmp_path / "w.yaml").write_text(bad, encoding="utf-8")
    [wf] = workflows.load_workflows(tmp_path)
    problems = workflows.workflow_problems(wf, catalog())
    assert len(problems) == 2 and "没有的参数 'nope'" in problems[0] and "要是 str" in problems[1]
    for wrong in ("    does: 说清楚\n    with: {x: 1}\n", "    cap: design\n    with: [1]\n"):
        (tmp_path / "w.yaml").write_text(GOOD.replace(wrong.splitlines()[0] + "\n", wrong),
                                         encoding="utf-8")
        with pytest.raises(workflows.WorkflowInvalid, match="with"):
            workflows.load_workflows(tmp_path)


def test_load_and_describe(tmp_path):
    (tmp_path / "w.yaml").write_text(GOOD, encoding="utf-8")
    found = workflows.load_workflows(tmp_path)
    assert len(found) == 1 and found[0].summary == "两行的 摘要"
    described = workflows.describe(found, catalog())
    assert described[0]["steps"][1] == {"by": "助理", "does": "接任务", "cap": "design",
                                        "key": None, "with": {}}
    assert described[0]["problems"] == []
    assert described[0]["covers"] == ["设计"] and described[0]["remarks"] == []
    assert workflows.load_workflows(tmp_path / "nowhere") == []


def test_a_flow_that_experiments_without_verifying_gets_a_remark_not_a_problem(tmp_path):
    text = (GOOD.replace("cap: design", "cap: experiment")
            + "  - by: 助理\n    does: 分析\n    cap: analysis\n")
    (tmp_path / "w.yaml").write_text("assumes: [harness/, code/, run_0/]\n" + text,
                                     encoding="utf-8")
    [wf] = workflows.load_workflows(tmp_path)
    [described] = workflows.describe([wf], catalog())
    assert described["covers"] == ["实验", "分析"]
    assert described["problems"] == [] and "没有验证" in described["remarks"][0]


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
