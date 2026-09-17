"""指南注入：前言 + 指南原文；可写目录含 workflows/（拼得出来还要存得下来）；指南不在就明说。"""

from __future__ import annotations

import pytest

from framework.chat import guide


def test_system_prompt_is_preamble_plus_guide(tmp_path):
    path = tmp_path / "README.md"
    path.write_text("# 指南正文\n", encoding="utf-8")
    text = guide.system_prompt(path)
    assert text.startswith("# 你在服务里") and text.rstrip().endswith("# 指南正文")
    assert "工作流在 `workflows/`" in text and "前台跑" in text  # 外层 #56 #57 的两句补充


def test_missing_or_empty_guide_is_an_error(tmp_path):
    with pytest.raises(guide.GuideMissing, match="不在"):
        guide.system_prompt(tmp_path / "nope.md")
    empty = tmp_path / "README.md"
    empty.write_text("  \n", encoding="utf-8")
    with pytest.raises(guide.GuideMissing, match="空的"):
        guide.system_prompt(empty)


def test_agent_may_write_tasks_runs_and_workflows_only(tmp_path):
    assert guide.allowed_paths(tmp_path) == [tmp_path / "tasks", tmp_path / "runs",
                                             tmp_path / "workflows"]


def test_shipped_guide_teaches_how_to_save_a_custom_workflow():
    text = guide.system_prompt()
    assert "## 拼一条自己的流" in text and "workflows/<name>.yaml" in text
    assert "不要把 `ai4sci cap` 放后台" in text


def test_the_guides_example_workflow_actually_loads_and_connects(tmp_path):
    """指南里给 agent 抄的样例必须真能过 `show workflows`，否则它照抄就撞墙。"""
    import re

    from framework.capabilities import discover
    from framework.contracts import workflows

    text = guide.GUIDE_PATH.read_text(encoding="utf-8")
    block = re.search(r"```yaml\n(name: quick-look\n.*?)```", text, re.S).group(1)
    (tmp_path / "quick-look.yaml").write_text(block, encoding="utf-8")
    [wf] = workflows.load_workflows(tmp_path)
    catalog = {name: module.DESCRIPTOR for name, module in discover().items()}
    assert workflows.workflow_problems(wf, catalog) == []
    [described] = workflows.describe([wf], catalog)
    assert described["covers"] == ["实验", "分析"] and described["remarks"]
