"""工作区（纲领 P-15）：起、找、列；id 规矩；数据根与库目录的读取点只在 paths.py。"""

from __future__ import annotations

import pytest

from framework import paths
from framework.run import workspace


def test_create_load_list_and_the_layout(tmp_path):
    root = workspace.workspaces_root(tmp_path)
    ws = workspace.create(root, "rahman-nll", title="Rahman 稳定性")
    assert ws.root == (tmp_path / "workspaces" / "rahman-nll").resolve() and ws.id == "rahman-nll"
    assert (ws.task, ws.flows, ws.chats, ws.runs, ws.jobs) == tuple(
        ws.root / name for name in ("task", "flows", "chats", "runs", "jobs"))
    assert ws.meta()["title"] == "Rahman 稳定性" and ws.to_dict()["created_at"]
    assert workspace.load(ws.root) == ws
    other = workspace.create(root, "b")
    assert other.to_dict()["title"] == "b"  # 没给标题就叫 id
    assert [w.id for w in workspace.list_workspaces(root)] == ["b", "rahman-nll"]
    (root / "not-a-workspace").mkdir()
    assert [w.id for w in workspace.list_workspaces(root)] == ["b", "rahman-nll"]
    assert workspace.list_workspaces(tmp_path / "nowhere") == []


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
    """像 git 找 .git：从 cwd 往上找标记；`AI4SCI_WORKSPACE` 指定的优先；找不到说清怎么办。"""
    ws = workspace.create(tmp_path / "workspaces", "w1")
    deep = ws.task / "code"
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
