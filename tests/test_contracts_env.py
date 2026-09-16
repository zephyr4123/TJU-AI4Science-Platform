"""framework/contracts/env.py 的测试：env/ 怎么读、怎么判、venv 建得对不对。

夹具全长在 tmp_path 上；解释器版本取当前进程的，uv 就地能找到、不下载（P-5，且 CI 不靠网）。
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from framework.contracts import env
from tests.fixtures import packs_factory as pf

THIS_PYTHON = pf.PYTHON_VERSION


def make_env(tmp_path: Path, version: str = THIS_PYTHON, requirements: str = "") -> Path:
    task_dir = tmp_path / "toy"
    task_dir.mkdir()
    pf.write_env(task_dir, python_version=version, requirements=requirements)
    return task_dir


# ── 读与判 ───────────────────────────────────────────────────────────────
def test_minimal_env_is_valid(tmp_path):
    spec, problems = env.read_env(make_env(tmp_path))
    assert problems == []
    assert spec == env.EnvSpec(python_version=THIS_PYTHON, requirements=())


def test_requirements_comments_and_blank_lines_are_skipped(tmp_path):
    task_dir = make_env(tmp_path, requirements="# 注释\n\nnumpy==2.3.1\nscipy[extra]==1.16.0\n")
    spec, problems = env.read_env(task_dir)
    assert problems == []
    assert spec.requirements == ("numpy==2.3.1", "scipy[extra]==1.16.0")


def test_missing_env_dir_is_a_problem(tmp_path):
    (tmp_path / "toy").mkdir()
    spec, problems = env.read_env(tmp_path / "toy")
    assert spec is None and len(problems) == 1
    assert "env/" in problems[0] and "目录缺失" in problems[0]


def test_bad_python_version_is_a_problem(tmp_path):
    spec, problems = env.read_env(make_env(tmp_path, version="3"))
    assert spec is None
    assert "python-version" in problems[0] and "'3'" in problems[0]


@pytest.mark.parametrize("line", ["numpy>=2", "numpy", "-e .", "git+https://x/y.git", "numpy == 2"])
def test_unpinned_requirement_is_a_problem_with_line_number(tmp_path, line):
    task_dir = make_env(tmp_path, requirements=f"# 头\n{line}\n")
    spec, problems = env.read_env(task_dir)
    assert spec is None
    assert "requirements.lock:2" in problems[0] and repr(line) in problems[0]


def test_missing_lock_file_is_a_problem_even_for_zero_deps(tmp_path):
    task_dir = make_env(tmp_path)
    (task_dir / "env" / "requirements.lock").unlink()
    _, problems = env.read_env(task_dir)
    assert any("requirements.lock" in p and "空文件" in p for p in problems)


# ── 建 venv ──────────────────────────────────────────────────────────────
def test_build_venv_creates_an_isolated_interpreter_of_the_declared_version(tmp_path):
    task_dir = make_env(tmp_path)
    python = env.build_venv(task_dir, task_dir / env.VENV_DIRNAME)
    assert python == task_dir / ".venv" / "bin" / "python"
    assert python.is_file()
    # 真的是另一个环境：prefix 落在任务目录下，不是平台 venv 的那个
    out = subprocess.run([str(python), "-c", "import sys; print(sys.prefix)"],
                         capture_output=True, text=True, check=True).stdout.strip()
    assert Path(out).resolve() == (task_dir / ".venv").resolve()
    assert Path(out).resolve() != Path(sys.prefix).resolve()


def test_build_venv_is_idempotent(tmp_path):
    task_dir = make_env(tmp_path)
    first = env.build_venv(task_dir, task_dir / env.VENV_DIRNAME)
    second = env.build_venv(task_dir, task_dir / env.VENV_DIRNAME)
    assert first == second and second.is_file()


def test_build_venv_refuses_an_invalid_env_spec(tmp_path):
    task_dir = make_env(tmp_path, requirements="numpy>=2\n")
    with pytest.raises(env.EnvBuildError, match="requirements.lock"):
        env.build_venv(task_dir, task_dir / env.VENV_DIRNAME)


def test_build_venv_fails_loudly_when_uv_is_missing(tmp_path, monkeypatch):
    """uv 不在就报错退出，不退回到平台 venv 跑任务（P-7）。"""
    import importlib.util

    monkeypatch.setattr(importlib.util, "find_spec", lambda name: None)
    task_dir = make_env(tmp_path)
    with pytest.raises(env.EnvBuildError, match="uv 不在"):
        env.build_venv(task_dir, task_dir / env.VENV_DIRNAME)
    assert not (task_dir / env.VENV_DIRNAME).exists()


def test_build_venv_surfaces_uv_failure_with_stderr(tmp_path, monkeypatch):
    """uv 自己失败（这里用一个不存在的解释器版本）要把它的 stderr 带出来，不吞。"""
    task_dir = make_env(tmp_path, version="3.999")
    with pytest.raises(env.EnvBuildError, match="uv venv --python 3.999"):
        env.build_venv(task_dir, task_dir / env.VENV_DIRNAME)
