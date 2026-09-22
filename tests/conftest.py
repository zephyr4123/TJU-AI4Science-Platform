"""全套测试共用的夹具。

按人的算力清单（`~/.config/ai4sci/computes.yaml`，纲领 P-23）绝不让测试读到：开发机上缺省算力若是
一台远端机器，`cap design` / `cap auto-research` 这类测试会真的 ssh 过去跑（第一次就撞上了，
整套挂住）。每个测试都指到 tmp 下一个不存在的文件——清单里只有 local。真要连机器的测试自己
`AI4SCI_LIVE_SSH` 门控并显式选名字。
按人的底座清单（`agents.yaml`，纲领 P-25）同理：测试里两层都是 claude_code、每家用起点，
不读开发机的选择；
Codex 的私有 CODEX_HOME 也指到 tmp 下，测试不碰 `~/.config/ai4sci/codex-home`。
"""

from __future__ import annotations

import pytest

from backends import codex
from framework import agents, computes


@pytest.fixture(autouse=True)
def _isolated_computes(tmp_path, monkeypatch):
    monkeypatch.setenv(computes.PATH_ENV, str(tmp_path / ".ai4sci-computes.yaml"))
    monkeypatch.setenv(agents.PATH_ENV, str(tmp_path / ".ai4sci-agents.yaml"))
    monkeypatch.setenv(codex.HOME_ENV, str(tmp_path / ".codex-home"))
