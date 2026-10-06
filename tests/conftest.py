"""全套测试共用的夹具。

平台的家（`~/.ai4sci`，外层 #263）绝不让测试读到：每个测试都把 `AI4SCI_HOME` 指到 tmp 下一个空目录。
里面的算力清单（纲领 P-23）因此只有 local——开发机上缺省算力若是一台远端机器，`cap design` /
`cap auto-research` 这类测试会真的 ssh 过去跑（第一次就撞上了，整套挂住）；真要连机器的测试自己
`AI4SCI_LIVE_SSH` 门控并显式选名字。底座清单（`agents.yaml`，P-25）同理：两层都是 claude_code、
每家用起点，不读开发机的选择；两家 CLI 的私有目录、key、uv 缓存也都落在 tmp 下。
"""

from __future__ import annotations

import pytest

from framework import paths


@pytest.fixture(autouse=True)
def _isolated_home(tmp_path_factory, monkeypatch):
    # 家不放在用例自己的 tmp_path 里：有的用例要数 tmp_path 下有哪些文件
    monkeypatch.setenv(paths.HOME_ENV, str(tmp_path_factory.mktemp("ai4sci-home")))
