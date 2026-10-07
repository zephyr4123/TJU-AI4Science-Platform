"""paths：出厂件两种活法（外层 #138）——仓库里在仓根，装的包里在 framework/shipped/；平台的家
与活法无关，缺省 ~/.ai4sci（外层 #263）。环境变量永远优先；指向的不是目录当场炸。"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from framework import paths
from tests.fixtures.fake_cli import fake_cli


def test_source_mode_reads_shipped_from_the_repo_but_lives_in_the_home(monkeypatch, tmp_path):
    """外层 #263：在仓库里跑也不再把仓库当家——家只有一个，`~/.ai4sci`。"""
    monkeypatch.delenv(paths.HOME_ENV, raising=False)
    monkeypatch.delenv(paths.WORKFLOWS_ROOT_ENV, raising=False)
    monkeypatch.setattr(paths, "DEFAULT_HOME", tmp_path / ".ai4sci")
    assert paths.from_source()
    assert paths.home() == tmp_path / ".ai4sci"
    assert paths.workflows_root() == paths.REPO_ROOT / "workflows"
    assert paths.user_workflows_root() == tmp_path / ".ai4sci" / "studio" / "workflows"
    assert paths.guides_root() == paths.REPO_ROOT / "coordinator"
    assert paths.ui_dir() == paths.REPO_ROOT / "ui" / "web" / "dist"


def test_package_mode_reads_shipped_and_makes_a_home(monkeypatch, tmp_path: Path):
    shipped = tmp_path / "shipped"
    for name in paths.SHIPPED:
        (shipped / name).mkdir(parents=True)
    monkeypatch.setattr(paths, "from_source", lambda: False)
    monkeypatch.setattr(paths, "SHIPPED_DIR", shipped)
    monkeypatch.setattr(paths, "DEFAULT_HOME", tmp_path / "home" / "ai4sci")
    monkeypatch.delenv(paths.HOME_ENV, raising=False)
    monkeypatch.delenv(paths.SKILLS_ROOT_ENV, raising=False)
    monkeypatch.delenv(paths.CURATED_SKILLS_ROOT_ENV, raising=False)
    assert paths.skills_root() == shipped / "skills"
    assert paths.curated_skills_root() == shipped / "skills-curated"
    assert paths.guides_root() == shipped / "coordinator"
    assert paths.ui_dir() == shipped / "ui"
    assert not (tmp_path / "home" / "ai4sci").exists()
    assert paths.home() == tmp_path / "home" / "ai4sci"
    assert (tmp_path / "home" / "ai4sci").is_dir()
    # 人存的流程在家里，不在 shipped/ 里：装的包升级不会把它们带走（外层 #149）
    assert paths.user_workflows_root() == tmp_path / "home" / "ai4sci" / "studio" / "workflows"
    assert paths.user_workflows_root().is_dir()


def test_user_workflows_root_follows_the_home_it_is_given(monkeypatch, tmp_path: Path):
    """用户库跟着家走：AI4SCI_HOME 指哪就在哪的 studio/workflows/，第一次用时建；服务端
    持有自己的家时直接给。"""
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


def test_everything_private_lives_in_one_home(monkeypatch, tmp_path: Path):
    """外层 #263：设置、key、两家 CLI 的私有目录、uv 缓存都在家里；一处给路径。"""
    monkeypatch.setenv(paths.HOME_ENV, str(tmp_path))
    assert paths.agents_file() == tmp_path / "agents.yaml"
    assert paths.computes_file() == tmp_path / "computes.yaml"
    assert paths.keys_file() == tmp_path / "keys.yaml"
    assert paths.agent_home("codex") == tmp_path / "codex" and (tmp_path / "codex").is_dir()
    assert paths.uv_cache_dir() == tmp_path / "cache" / "uv"


def test_only_a_home_the_platform_made_carries_the_marker(monkeypatch, tmp_path: Path):
    """清除只删有标记的家：新建的、空的才放标记；指到一个已有东西的目录（比如误设成 ~）不放。"""
    monkeypatch.delenv(paths.HOME_ENV, raising=False)
    monkeypatch.setattr(paths, "DEFAULT_HOME", tmp_path / "fresh")
    assert (paths.home() / paths.MARKER_NAME).is_file()
    busy = tmp_path / "busy"
    busy.mkdir()
    (busy / "notes.txt").write_text("别人的东西", encoding="utf-8")
    monkeypatch.setenv(paths.HOME_ENV, str(busy))
    assert paths.home() == busy and not (busy / paths.MARKER_NAME).exists()
    empty = tmp_path / "empty"
    empty.mkdir()
    monkeypatch.setenv(paths.HOME_ENV, str(empty))
    assert (paths.home() / paths.MARKER_NAME).is_file()


def _script(folder: Path) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    return Path(fake_cli(folder / "ai4sci", ""))


def test_cli_names_this_install_not_whatever_ai4sci_is_first_on_path(monkeypatch, tmp_path: Path):
    """外层 #274：页面让人照抄的命令要跑到起服务的这一份安装上。源码跑的 `.venv/bin` 多半不在
    PATH 上，PATH 上还可能留着以前装的旧 wheel（照抄 `ai4sci agent login` 报没有 login）：
    不是同一份就写全路径。入口脚本与解释器在同一个 bin 目录（venv、`uv tool` 都是）。"""
    mine = _script(tmp_path / "my env" / "bin")
    old = _script(tmp_path / "old" / "bin")
    (old.with_suffix(".py") if os.name == "nt" else old).write_text("old = 1\n", encoding="utf-8")
    if os.name == "nt":  # 壳一样、旁边的脚本不一样：Windows 上比的是入口本身，换成不一样的入口
        old.write_bytes(old.read_bytes() + b"old")
    monkeypatch.setattr(paths.sys, "executable", str(mine.parent / "python"))
    monkeypatch.setenv("PATH", str(mine.parent))
    assert paths.cli() == "ai4sci"
    # uv tool 放进 bin 的入口：POSIX 是工具目录里那个的软链，Windows 是一份逐字节相同的复制
    linked = tmp_path / "local" / "bin"
    linked.mkdir(parents=True)
    if os.name == "nt":
        (linked / mine.name).write_bytes(mine.read_bytes())
    else:
        (linked / "ai4sci").symlink_to(mine)
    monkeypatch.setenv("PATH", str(linked))
    assert paths.cli() == "ai4sci"
    # 路径里有空格，照抄也得跑得通：POSIX 的 shell 加引号，PowerShell 要 `& "…"`
    typed = f'& "{mine}"' if os.name == "nt" else f"'{mine}'"
    monkeypatch.setenv("PATH", f"{old.parent}{os.pathsep}{mine.parent}")
    assert os.path.normcase(paths.cli()) == os.path.normcase(typed)
    monkeypatch.setenv("PATH", str(tmp_path / "nothing"))
    assert os.path.normcase(paths.cli()) == os.path.normcase(typed)
    mine.unlink()  # 只有 `python -m framework.cli` 能跑的安装
    python = mine.parent / "python"
    module = f'& "{python}"' if os.name == "nt" else f"'{python}'"
    assert paths.cli() == f"{module} -m framework.cli"
