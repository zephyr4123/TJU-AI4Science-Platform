"""清除平台的家（外层 #263）：三道闸、先登出两家、清空后留一个带标记的空家；命令只给人。"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

from framework import paths
from framework.chat import reset
from framework.cli import main
from framework.workspace import jobs
from framework.workspace.root import Workspace
from tests.fixtures import spaces


def _home(tmp_path: Path) -> tuple[Path, Workspace]:
    home = tmp_path / "home"
    home.mkdir()
    paths.mark(home)
    ws = spaces.make_workspace(home, "w1")
    (home / "keys.yaml").write_text("deepseek: sk-test\n", encoding="utf-8")
    (home / "claude_code" / "projects").mkdir(parents=True)
    return home, ws


def test_reset_logs_out_both_clis_then_leaves_an_empty_marked_home(tmp_path: Path):
    home, _ = _home(tmp_path)
    seen: list[str] = []

    def logout(name: str) -> tuple[list[str], dict[str, str]]:
        seen.append(name)
        return [sys.executable, "-c", "print('logged out')"], dict(os.environ)

    done = reset.reset(home, logout=logout)
    assert seen == ["claude_code", "codex"]  # 登录记在钥匙串里：不登出，删目录也留着它
    assert done[:2] == ["claude_code：已登出（logged out）", "codex：已登出（logged out）"]
    assert sorted(p.name for p in home.iterdir()) == [paths.MARKER_NAME]
    assert done[-1] == f"已清空 {home.resolve()}"


def test_reset_keeps_what_the_installer_put_there(tmp_path: Path):
    """外层 #277：清除是回到刚装好的样子，一行命令装的程序（`bin/` `tools/`）留着；卸载才删
    整个家。"""
    home, _ = _home(tmp_path)
    (home / paths.BIN_DIRNAME).mkdir()
    (home / paths.BIN_DIRNAME / "ai4sci").write_text("#!/bin/sh\n", encoding="utf-8")
    (home / paths.TOOLS_DIRNAME / "claude_code").mkdir(parents=True)
    reset.reset(home, logout=lambda name: ([sys.executable, "-c", "pass"], dict(os.environ)))
    assert sorted(p.name for p in home.iterdir()) == sorted(
        [paths.MARKER_NAME, paths.BIN_DIRNAME, paths.TOOLS_DIRNAME])
    assert (home / paths.TOOLS_DIRNAME / "claude_code").is_dir()


def test_reset_refuses_a_directory_the_platform_did_not_make(tmp_path: Path):
    stranger = tmp_path / "someone-else"
    stranger.mkdir()
    (stranger / "thesis.tex").write_text("别人的论文", encoding="utf-8")
    with pytest.raises(reset.ResetRefused, match="没有平台的标记"):
        reset.reset(stranger, logout=lambda name: pytest.fail("不该走到登出"))
    assert (stranger / "thesis.tex").is_file()
    with pytest.raises(reset.ResetRefused, match="主目录"):
        reset.check(Path.home())


def test_reset_refuses_while_a_job_is_running(tmp_path: Path):
    home, ws = _home(tmp_path)
    jobs._save(ws.jobs, jobs.Job(job_id="job-1", cap="design", stage="design", argv=[],
                                 pid=os.getpid(), started_at="t", output="design/1"))
    with pytest.raises(reset.ResetRefused, match="1 个作业在跑.*p/w1/job-1"):
        reset.reset(home, logout=lambda name: pytest.fail("不该走到登出"))
    assert (home / "keys.yaml").is_file()


def test_reset_and_login_commands_are_for_people_at_a_terminal(capsys):
    """agent 起的子进程没有终端：清除与登录都拒（P-14：助理面前的 `ai4sci` 不该能清空人的家）。"""
    assert main(["reset"]) == 2
    assert "终端" in capsys.readouterr().err
    assert main(["agent", "login", "claude_code"]) == 2
    assert "终端" in capsys.readouterr().err
