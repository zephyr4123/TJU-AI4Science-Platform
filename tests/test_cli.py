"""`ai4sci` CLI 的测试：用退出码说话。

用 subprocess 起真进程而不是直接调 main()，因为协调层拿到的就是退出码与两个流，
进程边界上的行为（0 / 1 / 2、问题走 stderr、ok 走 stdout）才是契约。
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from tests.fixtures import packs_factory as pf

REPO_ROOT = Path(__file__).resolve().parent.parent

EXIT_OK = 0
EXIT_INVALID = 1
EXIT_USAGE = 2


def run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    env = {**os.environ, "PYTHONPATH": str(REPO_ROOT)}
    return subprocess.run(
        [sys.executable, "-m", "framework.cli", *args],
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
        cwd=REPO_ROOT,
        env=env,
    )


def test_validate_ok_exits_zero(tmp_path):
    pack = pf.make_pack(tmp_path)
    proc = run_cli("task", "validate", str(pack.task_dir), "--domains", str(pack.domains_root))
    assert proc.returncode == EXIT_OK, proc.stderr
    assert proc.stdout.strip() == "ok toy"


def test_validate_problems_exit_one_and_print_one_per_line(tmp_path):
    manifest = pf.default_manifest()
    manifest["metrics"][0]["direction"] = "沿着感觉走"
    del manifest["metrics"][0]["primary"]
    pack = pf.make_pack(tmp_path, manifest=manifest)
    proc = run_cli("task", "validate", str(pack.task_dir), "--domains", str(pack.domains_root))
    assert proc.returncode == EXIT_INVALID
    assert proc.stdout == ""
    lines = [ln for ln in proc.stderr.splitlines() if ln.strip()]
    assert len(lines) == 2, proc.stderr
    assert any("direction" in ln for ln in lines)
    assert any("primary" in ln for ln in lines)


def test_validate_missing_dir_exits_two(tmp_path):
    proc = run_cli("task", "validate", str(tmp_path / "不存在"))
    assert proc.returncode == EXIT_USAGE
    assert "不存在" in proc.stderr


def test_validate_default_domains_root(tmp_path):
    """不给 --domains 时按 <task_dir>/../../domains 找，夹具正是这个形状。"""
    pack = pf.make_pack(tmp_path)
    proc = run_cli("task", "validate", str(pack.task_dir))
    assert proc.returncode == EXIT_OK, proc.stderr


def test_task_list(tmp_path):
    pack = pf.make_pack(tmp_path)
    proc = run_cli("task", "list", "--root", str(pack.root))
    assert proc.returncode == EXIT_OK, proc.stderr
    assert proc.stdout.strip() == f"toy\t{pack.task_dir}"


def test_task_list_duplicate_id_exits_two(tmp_path):
    pack = pf.make_pack(tmp_path)
    pf.make_pack(tmp_path, task_id="toy", dir_name="toy-copy")
    proc = run_cli("task", "list", "--root", str(pack.root))
    assert proc.returncode == EXIT_USAGE
    assert "id 重复" in proc.stderr


def test_task_list_missing_root_exits_two(tmp_path):
    proc = run_cli("task", "list", "--root", str(tmp_path / "没有这个目录"))
    assert proc.returncode == EXIT_USAGE


def test_real_task_pack_validates_via_cli():
    if not (REPO_ROOT / "tasks" / "mlp-regression").is_dir():
        pytest.skip("仓里没有 tasks/mlp-regression，框架测试不依赖它")
    proc = run_cli("task", "validate", str(REPO_ROOT / "tasks" / "mlp-regression"))
    assert proc.returncode == EXIT_OK, proc.stderr
    assert proc.stdout.strip() == "ok mlp-regression"
