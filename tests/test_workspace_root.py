"""工作区（纲领 P-15、P-19）：起、找、列；id 规矩；需求就是标记；数据根与库目录的读取点
只在 paths.py。"""

from __future__ import annotations

import pytest

from framework import paths
from framework.contracts.stages import STAGE_SLUGS
from framework.workspace import root as workspace

TEMPLATE = "# 课题标题\n\n> 模板说明\n\n## 问题\n\n待填\n"


def test_create_load_list_and_the_layout(tmp_path):
    root = workspace.workspaces_root(tmp_path)
    ws = workspace.create(root, "rahman-nll", title="Rahman 稳定性", template=TEMPLATE)
    assert ws.root == (tmp_path / "workspaces" / "rahman-nll").resolve() and ws.id == "rahman-nll"
    assert (ws.requirement, ws.materials, ws.flows, ws.platform) == tuple(
        ws.root / name for name in ("requirement.md", "materials", "flows", ".ai4sci"))
    assert ws.chats == ws.platform / "chats" and ws.jobs == ws.platform / "jobs"
    assert ws.materials.is_dir() and ws.flows.is_dir() and ws.platform.is_dir()
    # 模板的一级标题换成课题标题，其余照抄；标题从文件读
    text = ws.requirement.read_text(encoding="utf-8")
    assert text.startswith("# Rahman 稳定性\n\n> 模板说明") and "## 问题" in text
    assert ws.title() == "Rahman 稳定性"
    assert ws.to_dict()["requirement"]["confirmed"] is False
    assert workspace.load(ws.root) == ws
    other = workspace.create(root, "b")
    assert other.title() == "b" and other.requirement.read_text(encoding="utf-8") == "# b\n"
    assert [w.id for w in workspace.list_workspaces(root)] == ["b", "rahman-nll"]
    (root / "not-a-workspace").mkdir()
    assert [w.id for w in workspace.list_workspaces(root)] == ["b", "rahman-nll"]
    assert workspace.list_workspaces(tmp_path / "nowhere") == []
    # 阶段目录：流程走到才有；stage_dir 只认七个
    assert ws.stage_dirs() == []
    ws.stage_dir("design").mkdir()
    assert [p.name for p in ws.stage_dirs()] == ["design"]
    with pytest.raises(AssertionError):
        ws.stage_dir("runs")
    assert set(STAGE_SLUGS) == {"literature", "hypothesis", "design", "experiment", "analysis",
                                "writing", "verification"}


def test_template_without_a_heading_gets_one(tmp_path):
    ws = workspace.create(tmp_path / "workspaces", "w", title="T", template="## 问题\n\n待填\n")
    assert ws.requirement.read_text(encoding="utf-8") == "# T\n\n## 问题\n\n待填\n"


def test_create_refuses_bad_ids_and_duplicates(tmp_path):
    root = tmp_path / "workspaces"
    workspace.create(root, "w1")
    with pytest.raises(workspace.WorkspaceInvalid, match="已经有"):
        workspace.create(root, "w1")
    for bad in ("W1", "有空格 x", "1abc", "../x", ""):
        with pytest.raises(workspace.WorkspaceInvalid, match="小写英文"):
            workspace.create(root, bad)
    with pytest.raises(workspace.WorkspaceNotFound, match="不是工作区"):
        workspace.load(tmp_path)


def test_find_walks_up_from_cwd_or_takes_the_env(tmp_path, monkeypatch):
    """像 git 找 .git：从 cwd 往上找 requirement.md；`AI4SCI_WORKSPACE` 指定的优先；
    找不到说清怎么办。"""
    ws = workspace.create(tmp_path / "workspaces", "w1")
    deep = ws.root / "design" / "1"
    deep.mkdir(parents=True)
    monkeypatch.delenv(workspace.WORKSPACE_ENV, raising=False)
    assert workspace.find(deep) == ws and workspace.find(ws.root) == ws
    monkeypatch.chdir(deep)
    assert workspace.find() == ws
    with pytest.raises(workspace.WorkspaceNotFound, match="workspace new"):
        workspace.find(tmp_path)
    monkeypatch.setenv(workspace.WORKSPACE_ENV, str(ws.root))
    assert workspace.find(tmp_path) == ws
    monkeypatch.setenv(workspace.WORKSPACE_ENV, str(tmp_path))
    with pytest.raises(workspace.WorkspaceNotFound):
        workspace.find(deep)


def test_paths_read_each_env_once_and_refuse_non_directories(tmp_path, monkeypatch):
    monkeypatch.setenv(paths.HOME_ENV, str(tmp_path))
    assert paths.home() == tmp_path.resolve()
    monkeypatch.setenv(paths.HOME_ENV, str(tmp_path / "nope"))
    with pytest.raises(AssertionError, match=paths.HOME_ENV):
        paths.home()
    monkeypatch.delenv(paths.HOME_ENV)
    assert paths.home() == paths.REPO_ROOT
    assert paths.workflows_root() == paths.REPO_ROOT / "workflows"
    assert paths.domains_root() == paths.REPO_ROOT / "domains"
    assert paths.templates_root() == paths.REPO_ROOT / "templates"
    assert sorted(p.stem for p in paths.templates_root().glob("*.md")) == ["ai", "cs", "generic",
                                                                          "materials"]
