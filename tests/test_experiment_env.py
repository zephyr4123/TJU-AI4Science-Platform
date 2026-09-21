"""framework/contracts/env.py 的测试：env/ 怎么读、怎么判、venv 建得对不对。

夹具全长在 tmp_path 上；解释器版本取当前进程的，uv 就地能找到、不下载（P-5，且 CI 不靠网）。
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from framework.experiment import env
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


# ── 清单要完整（外层 #117）：会联网（PyPI），CI 有网 ─────────────────────
def test_resolve_lock_pins_transitive_deps_and_incomplete_lock_fails_before_running(tmp_path):
    """按包名算出的清单带传递依赖；只钉顶层包的手写清单建完 venv 就报「不完整」，不等 import 炸。"""
    target = tmp_path / "materials" / "env"
    lock = env.resolve_lock(target, THIS_PYTHON, ["requests"])
    assert lock == target / "requirements.lock"
    assert (target / "python-version").read_text(encoding="utf-8") == THIS_PYTHON + "\n"
    spec, problems = env.read_env(tmp_path / "materials")
    assert problems == [] and spec is not None
    names = [line.split("==")[0] for line in spec.requirements]
    assert "requests" in names and "urllib3" in names and "idna" in names
    assert lock.read_text(encoding="utf-8").startswith("# 由 ai4sci env resolve")
    with pytest.raises(AssertionError, match="X.Y"):
        env.resolve_lock(target, "3", ["requests"])

    only_top = [line for line in spec.requirements if line.startswith("requests==")]
    (tmp_path / "task").mkdir()
    task_dir = make_env(tmp_path / "task", requirements="\n".join(only_top) + "\n")
    with pytest.raises(env.EnvBuildError, match="不完整") as exc:
        env.build_venv(task_dir, task_dir / env.VENV_DIRNAME)
    assert "env resolve" in str(exc.value) and "urllib3" in str(exc.value)


# ── 用机器上现成的环境（P-23 的两问）─────────────────────────────────────
def test_interpreter_file_makes_build_use_the_existing_python_only_on_that_compute(tmp_path):
    from compute.local import LocalCompute

    task_dir = make_env(tmp_path, requirements="")
    (task_dir / "env" / "interpreter").write_text(f"local:{sys.executable}\n", encoding="utf-8")
    spec, problems = env.read_env(task_dir)
    assert problems == [] and spec.interpreter == ("local", sys.executable)
    python = env.build_venv_on(LocalCompute(), str(task_dir), str(task_dir / ".venv"))
    assert python == sys.executable and not (task_dir / ".venv").exists()  # 没建 venv
    other = LocalCompute()
    other.name = "autodl"
    with pytest.raises(env.EnvBuildError, match="换了机器要重选"):
        env.build_venv_on(other, str(task_dir), str(task_dir / ".venv"))
    (task_dir / "env" / "python-version").write_text("3.9\n", encoding="utf-8")
    with pytest.raises(env.EnvBuildError, match="版本对不上"):
        env.build_venv_on(LocalCompute(), str(task_dir), str(task_dir / ".venv"))
    (task_dir / "env" / "interpreter").write_text("nocolon\n", encoding="utf-8")
    _, problems = env.read_env(task_dir)
    assert any("interpreter" in p and "绝对路径" in p for p in problems)


def test_use_interpreter_freezes_the_existing_env_and_resolve_switches_back(tmp_path):
    from compute.local import LocalCompute

    target = tmp_path / "materials" / "env"
    env.use_interpreter(target, LocalCompute(), sys.executable)
    assert (target / "interpreter").read_text(encoding="utf-8") == f"local:{sys.executable}\n"
    assert (target / "python-version").read_text(encoding="utf-8").strip() == THIS_PYTHON
    lock = (target / "requirements.lock").read_text(encoding="utf-8")
    assert lock.startswith("# 算力 local 上现成的环境") and "pyyaml==" in lock.lower()
    spec, problems = env.read_env(tmp_path / "materials")
    assert problems == [] and spec.interpreter == ("local", sys.executable)
    with pytest.raises(env.EnvBuildError, match="起不来"):
        env.use_interpreter(target, LocalCompute(), "/nope/python")


def test_add_packages_installs_into_the_existing_interpreter_and_refreezes(tmp_path):
    """P-24：镜像自带的环境缺论文仓库要的几个小包——pip 装进 env use 登记的那个解释器，重新 freeze，
    清单头部记下补了什么。只对「用现成的」环境；不是那台机器的、没登记过的都拒。
    装进一个一次性 venv，不碰平台 venv（会联网）。"""
    from compute.local import LocalCompute

    venv = tmp_path / "throwaway"
    subprocess.run([sys.executable, "-m", "venv", str(venv)], check=True)
    python = str(venv / "bin" / "python")
    target = tmp_path / "materials" / "env"
    with pytest.raises(env.EnvBuildError, match="先 ai4sci env use"):
        env.add_packages(target, LocalCompute(), ["six"])
    env.use_interpreter(target, LocalCompute(), python)
    assert "six==" not in (target / "requirements.lock").read_text(encoding="utf-8")
    (target / "interpreter").write_text(f"other:{python}\n", encoding="utf-8")
    with pytest.raises(env.EnvBuildError, match="'other'"):
        env.add_packages(target, LocalCompute(), ["six"])
    (target / "interpreter").write_text(f"local:{python}\n", encoding="utf-8")
    env.add_packages(target, LocalCompute(), ["six"])
    lock = (target / "requirements.lock").read_text(encoding="utf-8")
    assert lock.startswith("# ai4sci env add 于 ") and "补装：six" in lock and "six==" in lock
    assert (target / "interpreter").read_text(encoding="utf-8") == f"local:{python}\n"
    with pytest.raises(env.EnvBuildError, match="pip install"):
        env.add_packages(target, LocalCompute(), ["definitely-not-a-package-zz9"])
    env.resolve_lock(target, THIS_PYTHON, ["packaging"])  # 回到隔离新建：interpreter 文件删掉
    assert not (target / "interpreter").exists()
