"""项目（纲领 P-15 改，外层 #136）：起、找、列；工作区在项目里两级之下；id 规矩；老布局说清要搬。"""

from __future__ import annotations

import pytest

from framework.workspace import project
from framework.workspace import root as workspace
from tests.fixtures import spaces


def test_create_load_list_and_the_layout(tmp_path):
    root = project.projects_root(tmp_path)
    made = project.create(root, "paper", title="一篇论文", goal="把综述和实验合成一篇")
    assert made.root == (tmp_path / "projects" / "paper").resolve() and made.id == "paper"
    assert (made.marker, made.materials, made.workspaces_dir, made.platform, made.chats) == (
        made.root / "project.md", made.root / "materials", made.root / "workspaces",
        made.root / ".ai4sci", made.root / ".ai4sci" / "chats")
    assert made.materials.is_dir() and made.workspaces_dir.is_dir() and made.platform.is_dir()
    assert made.text() == "# 一篇论文\n\n把综述和实验合成一篇\n" and made.title() == "一篇论文"
    assert made.to_dict() == {"id": "paper", "title": "一篇论文", "root": str(made.root)}
    assert project.load(made.root) == made
    bare = project.create(root, "b")
    assert bare.title() == "b" and bare.text() == "# b\n"
    assert [p.id for p in project.list_projects(root)] == ["b", "paper"]
    (root / "not-a-project").mkdir()
    assert [p.id for p in project.list_projects(root)] == ["b", "paper"]
    assert project.list_projects(tmp_path / "nowhere") == []
    # 工作区在项目里：起、列、按名字取、找回项目
    assert made.workspaces() == []
    ws = project.new_workspace(made, "survey", title="综述")
    assert ws.root == made.workspaces_dir / "survey" and ws.title() == "综述"
    assert [w.id for w in made.workspaces()] == ["survey"] and made.workspace("survey") == ws
    assert project.of(ws) == made
    with pytest.raises(workspace.WorkspaceNotFound,
                       match="项目 paper 里没有工作区 'nope'（有：survey）"):
        made.workspace("nope")
    with pytest.raises(workspace.WorkspaceInvalid, match="小写英文"):
        made.workspace("../etc")


def test_create_refuses_bad_ids_and_duplicates(tmp_path):
    root = project.projects_root(tmp_path)
    project.create(root, "p1")
    with pytest.raises(project.ProjectInvalid, match="已经有"):
        project.create(root, "p1")
    for bad in ("P1", "有空格 x", "1abc", "../x", ""):
        with pytest.raises(project.ProjectInvalid, match="小写英文"):
            project.create(root, bad)
    with pytest.raises(project.ProjectNotFound, match="不是项目"):
        project.load(tmp_path)


def test_find_walks_up_from_cwd_or_takes_the_env(tmp_path, monkeypatch):
    """助理站在项目里：从 cwd 往上找 project.md（工作区目录里往上也找得到），`AI4SCI_PROJECT`
    指定的优先；找不到说清怎么办。"""
    ws = spaces.make_workspace(tmp_path, "w1")
    made = project.of(ws)
    deep = ws.root / "design" / "1"
    deep.mkdir(parents=True)
    monkeypatch.delenv(project.PROJECT_ENV, raising=False)
    assert project.find(deep) == made and project.find(made.root) == made
    monkeypatch.chdir(deep)
    assert project.find() == made
    with pytest.raises(project.ProjectNotFound, match="project new"):
        project.find(tmp_path)
    monkeypatch.setenv(project.PROJECT_ENV, str(made.root))
    assert project.find(tmp_path) == made
    monkeypatch.setenv(project.PROJECT_ENV, str(tmp_path))
    with pytest.raises(project.ProjectNotFound):
        project.find(deep)


def test_old_layout_workspace_is_told_to_move(tmp_path):
    """搬家前的布局（工作区直接在 workspaces/ 下）：不在任何项目里，信息说清先搬。"""
    ws = workspace.create(tmp_path / "workspaces", "old")
    with pytest.raises(project.ProjectNotFound, match="搬家前的布局"):
        project.of(ws)
