"""两位助理的指南（纲领 P-16）：各一段前言 + 各自的原文；分权的机器判据在这里；指南不在就明说。"""

from __future__ import annotations

import re

import pytest

from framework import paths
from framework.chat import guide, scope
from framework.workspace import root as workspace


def _commands(text: str) -> list[str]:
    return [line.strip() for block in re.findall(r"```bash\n(.*?)```", text, re.S)
            for line in block.splitlines() if line.strip() and not line.startswith("#")]


def test_tool_guide_goes_right_after_the_preamble(tmp_path):
    """P-25：「工具怎么用」是这家 CLI 自己的一段（`Chat.tool_guide`），插在前言之后、指南原文之前；
    空的不插。真跑时 Codex 的助理照「只能运行 ai4sci」办，连 materials/ 都不敢看，就缺这一段。"""
    path = tmp_path / "guide.md"
    path.write_text("# 指南\n\n正文", encoding="utf-8")
    tool = "## 工具怎么用\n\n- 看文件用 ls / cat\n"
    text = guide.system_prompt(guide.STUDIO, path, tool_guide=tool)
    head, tail = text.split("## 工具怎么用", 1)
    assert "# 你在服务里" in head and "# 指南" not in head
    assert tail.strip().startswith("- 看文件用 ls / cat") and "# 指南" in tail
    assert "## 工具怎么用" not in guide.system_prompt(guide.STUDIO, path, tool_guide="  ")


def test_system_prompt_is_preamble_plus_guide(tmp_path):
    path = tmp_path / "README.md"
    path.write_text("# 指南正文\n", encoding="utf-8")
    text = guide.system_prompt(guide.WORKSPACE, path)
    assert text.startswith("# 你在服务里") and text.rstrip().endswith("# 指南正文")
    assert "流程实例在 `flows/`" in text and "--detach" in text
    studio = guide.system_prompt(guide.STUDIO, path)
    assert studio.startswith("# 你在服务里") and "流程助理" in studio and "--detach" not in studio
    with pytest.raises(AssertionError, match="指南只有"):
        guide.system_prompt("nope", path)


def test_missing_or_empty_guide_is_an_error(tmp_path):
    with pytest.raises(guide.GuideMissing, match="不在"):
        guide.system_prompt(guide.WORKSPACE, tmp_path / "nope.md")
    empty = tmp_path / "README.md"
    empty.write_text("  \n", encoding="utf-8")
    with pytest.raises(guide.GuideMissing, match="空的"):
        guide.system_prompt(guide.STUDIO, empty)


def test_the_two_scopes_write_to_disjoint_places(tmp_path, monkeypatch):
    """分权靠白名单：研究助理只写自己的工作区，流程助理只写库；两组没有交集。"""
    ws = workspace.create(tmp_path / "workspaces", "w1")
    library = tmp_path / "lib" / "workflows"
    library.mkdir(parents=True)
    templates = tmp_path / "lib" / "templates"
    templates.mkdir()
    monkeypatch.setenv(paths.WORKFLOWS_ROOT_ENV, str(library))
    monkeypatch.setenv(paths.TEMPLATES_ROOT_ENV, str(templates))
    research = scope.for_workspace(ws)
    studio = scope.studio(tmp_path)
    assert research.kind == "workspace" and research.cwd == ws.root
    assert research.allowed_paths == (ws.root,) and research.chats == ws.platform / "chats"
    assert studio.kind == "studio" and studio.cwd == library.parent
    assert studio.allowed_paths == (library,) and studio.chats == tmp_path / "studio" / "chats"
    assert not set(research.allowed_paths) & set(studio.allowed_paths)
    # 两个库对研究助理是只读的：在可读清单里、不在可写清单里；流程助理反过来
    assert research.readable_paths == (library, templates) and studio.readable_paths == ()


def test_bash_rules_only_allow_bare_ai4sci():
    """纲领 P-14：指南只教裸 `ai4sci`；带路径的老写法也放行（老会话照自己以前的写法来，别设坎）。"""
    # 与 CLI 无关的命令前缀（P-25 两家适配器各自翻）：Claude Code 翻成 `Bash(ai4sci *)`
    assert guide.BASH_RULES == ("ai4sci", ".venv/bin/ai4sci")
    for kind in guide.KINDS:
        preamble = guide.PREAMBLES[kind]
        assert "不加路径、不在前面挂环境变量" in preamble and "按按钮" not in preamble
    assert "现在一律写 `ai4sci`" in guide.PREAMBLES[guide.WORKSPACE]
    assert "平台还没有这个功能" in guide.PREAMBLES[guide.WORKSPACE]
    assert "去编辑台拼一条" in guide.PREAMBLES[guide.WORKSPACE]
    assert "不拼 `find`" in guide.PREAMBLES[guide.WORKSPACE]
    assert "去主页面找研究助理" in guide.PREAMBLES[guide.STUDIO]


@pytest.mark.parametrize("kind", guide.KINDS)
def test_shipped_guides_never_show_the_agent_a_raw_command(kind):
    """纲领 P-14 的机器判据：两份指南里给 agent 抄的每条命令都以 `ai4sci ` 开头——不带路径、
    不挂环境变量、不接管道。指南教一种白名单跑不了的写法，agent 照抄就撞墙（实验 #59 第 3 轮）。"""
    text = guide.system_prompt(kind)
    assert ".venv/bin/ai4sci" not in guide.GUIDE_PATHS[kind].read_text(encoding="utf-8")
    assert not re.search(r"AI4SCI_[A-Z_]+=\S+\s+ai4sci", text)
    commands = _commands(text)
    if kind == guide.WORKSPACE:
        assert commands, "研究助理的指南里总该有几条命令"
    for line in commands:
        head = line.split("#", 1)[0].rstrip()
        assert head.startswith("ai4sci "), line
        assert not re.search(r"[|;&]", head), line


def test_research_guide_takes_flows_and_never_builds_them():
    """纲领 P-16 的机器判据：研究助理的指南没有「拼一条自己的流程」、没有往库里写文件的写法；
    只教取流程、改实例；命令里不带任务包路径（P-15）。"""
    text = guide.system_prompt(guide.WORKSPACE)
    assert "## 取一条流程，按需求改" in text and "ai4sci flow take" in text
    assert f"库在 `{paths.workflows_root()}`：你能读不能写" in text  # 路径写实，agent 不用去找
    assert "## 拼一条自己的流程" not in text and "workflows/<name>.yaml" not in text
    assert "不要造流程" in text and "去编辑台" in text
    assert "不要自己把 `ai4sci cap` 放后台" in text
    assert "ai4sci show templates" in text and "你不做" in text  # 需求：只写不确认
    for line in _commands(text):
        assert "task/" not in line and "workspaces/" not in line, line


def test_studio_guide_builds_flows_and_never_runs_experiments():
    text = guide.system_prompt(guide.STUDIO)
    assert "workflows/<name>.yaml" in text and "ai4sci show workflows" in text
    assert "断点" in text and "不做数据流校验" in text
    assert "不跑实验" in text and "不碰任何工作区" in text
    assert "ai4sci cap " not in "\n".join(_commands(text))


def test_the_studio_guides_example_workflow_actually_loads_and_passes(tmp_path):
    """流程助理指南里给它抄的样例必须真能过 `show workflows`，否则它照抄就撞墙。"""
    from framework.capabilities import discover
    from framework.contracts import workflows

    text = guide.GUIDE_PATHS[guide.STUDIO].read_text(encoding="utf-8")
    block = re.search(r"```yaml\n(name: quick-look\n.*?)```", text, re.S).group(1)
    (tmp_path / "quick-look.yaml").write_text(block, encoding="utf-8")
    [wf] = workflows.load_workflows(tmp_path)
    catalog = {name: module.DESCRIPTOR for name, module in discover().items()}
    assert workflows.workflow_problems(wf, catalog) == []
    [described] = workflows.describe([wf], catalog)
    assert described["covers"] == ["实验", "分析"] and len(described["remarks"]) == 1
    assert wf.stages[0].picks[0].with_ == {"max_iters": 2}
