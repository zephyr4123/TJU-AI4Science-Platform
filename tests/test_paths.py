"""paths：两种活法（外层 #138）——仓库里出厂件在仓根、数据根缺省仓根；装的包里出厂件在
framework/shipped/、数据根缺省 ~/ai4sci。环境变量永远优先；指向的不是目录当场炸。"""

from __future__ import annotations

from pathlib import Path

import pytest

from framework import paths


def test_source_mode_reads_the_repo(monkeypatch):
    monkeypatch.delenv(paths.HOME_ENV, raising=False)
    monkeypatch.delenv(paths.WORKFLOWS_ROOT_ENV, raising=False)
    assert paths.from_source()
    assert paths.home() == paths.REPO_ROOT
    assert paths.workflows_root() == paths.REPO_ROOT / "workflows"
    assert paths.user_workflows_root() == paths.REPO_ROOT / "studio" / "workflows"
    assert paths.guides_root() == paths.REPO_ROOT / "coordinator"
    assert paths.ui_dir() == paths.REPO_ROOT / "ui" / "web" / "dist"


def test_package_mode_reads_shipped_and_makes_a_home(monkeypatch, tmp_path: Path):
    shipped = tmp_path / "shipped"
    for name in ("workflows", "templates", "domains", "skills", "coordinator", "ui"):
        (shipped / name).mkdir(parents=True)
    monkeypatch.setattr(paths, "from_source", lambda: False)
    monkeypatch.setattr(paths, "SHIPPED_DIR", shipped)
    monkeypatch.setattr(paths, "DEFAULT_HOME", tmp_path / "home" / "ai4sci")
    monkeypatch.delenv(paths.HOME_ENV, raising=False)
    monkeypatch.delenv(paths.SKILLS_ROOT_ENV, raising=False)
    assert paths.skills_root() == shipped / "skills"
    assert paths.guides_root() == shipped / "coordinator"
    assert paths.ui_dir() == shipped / "ui"
    assert not (tmp_path / "home" / "ai4sci").exists()
    assert paths.home() == tmp_path / "home" / "ai4sci"
    assert (tmp_path / "home" / "ai4sci").is_dir()
    # 人存的流程在数据根下，不在 shipped/ 里：装的包升级不会把它们带走（外层 #149）
    assert paths.user_workflows_root() == tmp_path / "home" / "ai4sci" / "studio" / "workflows"
    assert paths.user_workflows_root().is_dir()


def test_user_workflows_root_follows_the_home_it_is_given(monkeypatch, tmp_path: Path):
    """用户库跟着数据根走：AI4SCI_HOME 指哪就在哪的 studio/workflows/，第一次用时建；服务端
    持有自己的数据根时直接给。"""
    monkeypatch.setenv(paths.HOME_ENV, str(tmp_path))
    assert paths.user_workflows_root() == tmp_path.resolve() / "studio" / "workflows"
    assert (tmp_path / "studio" / "workflows").is_dir()
    other = tmp_path / "other"
    assert paths.user_workflows_root(other) == other / "studio" / "workflows"
    assert (tmp_path / "other" / "studio" / "workflows").is_dir()


def test_env_wins_and_a_missing_dir_fails_loudly(monkeypatch, tmp_path: Path):
    monkeypatch.setenv(paths.TEMPLATES_ROOT_ENV, str(tmp_path))
    assert paths.templates_root() == tmp_path.resolve()
    monkeypatch.setenv(paths.HOME_ENV, str(tmp_path / "nowhere"))
    with pytest.raises(AssertionError, match=paths.HOME_ENV):
        paths.home()
