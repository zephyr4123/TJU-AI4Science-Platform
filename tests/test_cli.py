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

from compute.local import LocalCompute
from framework import gitwork, loop
from tests.fixtures import packs_factory as pf
from tests.fixtures.scripted_backend import ScriptedRunner
from tests.test_loop import start_run, train_for_mse

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


# ── run / loop / status：实验内环的驱动面 ──────────────────────────────
def new_run_via_cli(tmp_path, run_id: str = "r1"):
    pack = pf.make_pack(tmp_path)
    proc = run_cli("run", "new", str(pack.task_dir), "--run-id", run_id,
                   "--runs-root", str(tmp_path / "runs"))
    return pack, proc


def test_run_new_creates_the_run_dir(tmp_path):
    _, proc = new_run_via_cli(tmp_path)
    assert proc.returncode == EXIT_OK, proc.stderr
    assert proc.stdout.startswith("ok r1\t")
    run_dir = tmp_path / "runs" / "r1"
    assert (run_dir / "checkpoint.json").is_file()
    assert (run_dir / "work" / ".git").is_dir()
    assert (run_dir / "manifest.yaml").is_file()
    assert (run_dir / "journal.md").is_file()


def test_run_new_on_broken_pack_exits_one(tmp_path):
    pack = pf.make_pack(tmp_path)
    (pack.task_dir / "harness" / "evaluate.py").write_text("# 改了但没更新 SHA256SUMS\n")
    proc = run_cli("run", "new", str(pack.task_dir), "--runs-root", str(tmp_path / "runs"))
    assert proc.returncode == EXIT_INVALID
    assert "sha256" in proc.stderr.lower()
    assert not (tmp_path / "runs").exists() or not any((tmp_path / "runs").iterdir())


def test_run_new_twice_same_id_exits_two(tmp_path):
    new_run_via_cli(tmp_path)
    pack, proc = new_run_via_cli(tmp_path)
    assert proc.returncode == EXIT_USAGE
    assert "不覆盖" in proc.stderr


def test_run_new_missing_task_dir_exits_two(tmp_path):
    proc = run_cli("run", "new", str(tmp_path / "没有"), "--runs-root", str(tmp_path / "runs"))
    assert proc.returncode == EXIT_USAGE


def test_status_prints_best_and_ledger_tail(tmp_path):
    new_run_via_cli(tmp_path)
    proc = run_cli("status", "r1", "--runs-root", str(tmp_path / "runs"))
    assert proc.returncode == EXIT_OK, proc.stderr
    fields = dict(line.split("\t", 1) for line in proc.stdout.splitlines() if "\t" in line)
    assert fields["run_id"] == "r1"
    assert fields["best_metric"] == "0.5"
    assert fields["stop_reason"] == "-"
    assert fields["ledger_rows"] == "0"


def test_status_reconciles_the_ledger_and_exits_one_when_git_lost_a_row(tmp_path):
    """status 顺手对账：被弃的那一轮的 attempts ref 被删掉，账本就跟 git 对不上了。"""
    run_dir, _ = start_run(tmp_path)  # run_id 是 r1，runs 根是 tmp_path/runs
    loop.run_loop(run_dir, ScriptedRunner([train_for_mse(0.5)]), LocalCompute(), max_iters=1)
    refs = gitwork.attempt_refs(run_dir / "work")
    assert refs, "改坏的那一轮该留在 refs/attempts/ 下"
    ok = run_cli("status", "r1", "--runs-root", str(tmp_path / "runs"))
    assert ok.returncode == EXIT_OK, ok.stderr

    gitwork.git(run_dir / "work", "update-ref", "-d", next(iter(refs)))
    proc = run_cli("status", "r1", "--runs-root", str(tmp_path / "runs"))
    assert proc.returncode == EXIT_INVALID
    assert "refs/attempts" in proc.stderr
    assert "ledger_rows\t1" in proc.stdout, "对账失败也要先把状态打完"


def test_status_unknown_run_exits_two(tmp_path):
    proc = run_cli("status", "没这个 run", "--runs-root", str(tmp_path / "runs"))
    assert proc.returncode == EXIT_USAGE


def test_loop_run_unknown_run_exits_two(tmp_path):
    proc = run_cli("loop", "run", "没这个 run", "--runs-root", str(tmp_path / "runs"))
    assert proc.returncode == EXIT_USAGE


def test_loop_run_unknown_compute_exits_two(tmp_path):
    new_run_via_cli(tmp_path)
    proc = run_cli("loop", "run", "r1", "--compute", "slurm",
                   "--runs-root", str(tmp_path / "runs"))
    assert proc.returncode == EXIT_USAGE
    assert "local" in proc.stderr  # 报错要列出可用的名字，不静默回退


def test_loop_resume_unknown_backend_exits_two(tmp_path):
    new_run_via_cli(tmp_path)
    proc = run_cli("loop", "resume", "r1", "--backend", "codex",
                   "--runs-root", str(tmp_path / "runs"))
    assert proc.returncode == EXIT_USAGE
    assert "claude_code" in proc.stderr
