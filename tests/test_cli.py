"""`ai4sci` CLI 的测试：用退出码说话。

用 subprocess 起真进程而不是直接调 main()，因为协调层拿到的就是退出码与两个流，
进程边界上的行为（0 / 1 / 2、问题走 stderr、ok 走 stdout）才是契约。
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from compute.local import LocalCompute
from framework.capabilities.experiment import run_loop
from framework.run import gitwork
from tests.fixtures import packs_factory as pf
from tests.fixtures.scripted_backend import ScriptedRunner
from tests.test_experiment_loop import start_run, train_for_mse

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


def test_show_task_ok_exits_zero(tmp_path):
    pack = pf.make_pack(tmp_path)
    proc = run_cli("show", "task", str(pack.task_dir), "--domains", str(pack.domains_root))
    assert proc.returncode == EXIT_OK, proc.stderr
    assert proc.stdout.strip() == "ok toy"


def test_show_task_problems_exit_one_and_print_one_per_line(tmp_path):
    manifest = pf.default_manifest()
    manifest["metrics"][0]["direction"] = "沿着感觉走"
    del manifest["metrics"][0]["primary"]
    pack = pf.make_pack(tmp_path, manifest=manifest)
    proc = run_cli("show", "task", str(pack.task_dir), "--domains", str(pack.domains_root))
    assert proc.returncode == EXIT_INVALID
    assert proc.stdout == ""
    lines = [ln for ln in proc.stderr.splitlines() if ln.strip()]
    assert len(lines) == 2, proc.stderr
    assert any("direction" in ln for ln in lines)
    assert any("primary" in ln for ln in lines)


def test_show_task_missing_dir_exits_two(tmp_path):
    proc = run_cli("show", "task", str(tmp_path / "不存在"))
    assert proc.returncode == EXIT_USAGE
    assert "不存在" in proc.stderr


def test_show_task_default_domains_root(tmp_path):
    """不给 --domains 时按 <task_dir>/../../domains 找，夹具正是这个形状。"""
    pack = pf.make_pack(tmp_path)
    proc = run_cli("show", "task", str(pack.task_dir))
    assert proc.returncode == EXIT_OK, proc.stderr


def test_show_tasks(tmp_path):
    pack = pf.make_pack(tmp_path)
    proc = run_cli("show", "tasks", "--root", str(pack.root))
    assert proc.returncode == EXIT_OK, proc.stderr
    assert proc.stdout.strip() == f"toy\t{pack.task_dir}"


def test_show_tasks_duplicate_id_exits_two(tmp_path):
    pack = pf.make_pack(tmp_path)
    pf.make_pack(tmp_path, task_id="toy", dir_name="toy-copy")
    proc = run_cli("show", "tasks", "--root", str(pack.root))
    assert proc.returncode == EXIT_USAGE
    assert "id 重复" in proc.stderr


def test_show_tasks_missing_root_exits_two(tmp_path):
    proc = run_cli("show", "tasks", "--root", str(tmp_path / "没有这个目录"))
    assert proc.returncode == EXIT_USAGE


def test_real_task_pack_validates_via_cli():
    if not (REPO_ROOT / "tasks" / "mlp-regression").is_dir():
        pytest.skip("仓里没有 tasks/mlp-regression，框架测试不依赖它")
    proc = run_cli("show", "task", str(REPO_ROOT / "tasks" / "mlp-regression"))
    assert proc.returncode == EXIT_OK, proc.stderr
    assert proc.stdout.strip() == "ok mlp-regression"


# ── run / loop / status：实验内环的驱动面 ──────────────────────────────
def new_run_via_cli(tmp_path, run_id: str = "r1"):
    pack = pf.make_pack(tmp_path)
    proc = run_cli("cap", "start", str(pack.task_dir), "--run-id", run_id,
                   "--runs-root", str(tmp_path / "runs"))
    return pack, proc


def test_start_creates_the_run_dir(tmp_path):
    _, proc = new_run_via_cli(tmp_path)
    assert proc.returncode == EXIT_OK, proc.stderr
    assert proc.stdout.startswith("ok r1\t")
    run_dir = tmp_path / "runs" / "r1"
    assert (run_dir / "checkpoint.json").is_file()
    assert (run_dir / "work" / ".git").is_dir()
    assert (run_dir / "manifest.yaml").is_file()
    assert (run_dir / "journal.md").is_file()


def test_start_on_broken_pack_exits_one(tmp_path):
    pack = pf.make_pack(tmp_path)
    (pack.task_dir / "harness" / "evaluate.py").write_text("# 改了但没更新 SHA256SUMS\n")
    proc = run_cli("cap", "start", str(pack.task_dir), "--runs-root", str(tmp_path / "runs"))
    assert proc.returncode == EXIT_INVALID
    assert "sha256" in proc.stderr.lower()
    assert not (tmp_path / "runs").exists() or not any((tmp_path / "runs").iterdir())


def test_start_twice_same_id_exits_one(tmp_path):
    new_run_via_cli(tmp_path)
    pack, proc = new_run_via_cli(tmp_path)
    assert proc.returncode == EXIT_INVALID  # 能力失败统一退 1，原话在 stderr
    assert "不覆盖" in proc.stderr


def test_start_missing_task_dir_exits_two(tmp_path):
    proc = run_cli("cap", "start", str(tmp_path / "没有"), "--runs-root", str(tmp_path / "runs"))
    assert proc.returncode == EXIT_USAGE


def test_show_run_prints_best_and_ledger_tail(tmp_path):
    new_run_via_cli(tmp_path)
    proc = run_cli("show", "run", "r1", "--runs-root", str(tmp_path / "runs"))
    assert proc.returncode == EXIT_OK, proc.stderr
    fields = dict(line.split("\t", 1) for line in proc.stdout.splitlines() if "\t" in line)
    assert fields["run_id"] == "r1"
    assert fields["source"] == "-", "夹具 manifest 没写 source，打 '-' 不留空"
    assert fields["best_metric"] == "0.5"
    assert fields["stop_reason"] == "-"
    assert fields["ledger_rows"] == "0"


def test_show_run_prints_the_manifest_source(tmp_path):
    manifest = pf.default_manifest()
    manifest["source"] = "docs/cases/boehm-stat5-petab"
    pack = pf.make_pack(tmp_path, manifest=manifest)
    run_cli("cap", "start", str(pack.task_dir), "--run-id", "r1",
            "--runs-root", str(tmp_path / "runs"))
    proc = run_cli("show", "run", "r1", "--runs-root", str(tmp_path / "runs"))
    assert "source\tdocs/cases/boehm-stat5-petab" in proc.stdout.splitlines()


def test_show_run_reconciles_the_ledger_and_exits_one_when_git_lost_a_row(tmp_path):
    """status 顺手对账：被弃的那一轮的 attempts ref 被删掉，账本就跟 git 对不上了。"""
    run_dir, _ = start_run(tmp_path)  # run_id 是 r1，runs 根是 tmp_path/runs
    run_loop(run_dir, ScriptedRunner([train_for_mse(0.5)]), LocalCompute(), max_iters=1)
    refs = gitwork.attempt_refs(run_dir / "work")
    assert refs, "改坏的那一轮该留在 refs/attempts/ 下"
    ok = run_cli("show", "run", "r1", "--runs-root", str(tmp_path / "runs"))
    assert ok.returncode == EXIT_OK, ok.stderr

    gitwork.git(run_dir / "work", "update-ref", "-d", next(iter(refs)))
    proc = run_cli("show", "run", "r1", "--runs-root", str(tmp_path / "runs"))
    assert proc.returncode == EXIT_INVALID
    assert "refs/attempts" in proc.stderr
    assert "ledger_rows\t1" in proc.stdout, "对账失败也要先把状态打完"


def test_show_run_unknown_run_exits_two(tmp_path):
    proc = run_cli("show", "run", "没这个 run", "--runs-root", str(tmp_path / "runs"))
    assert proc.returncode == EXIT_USAGE


def test_experiment_unknown_run_exits_two(tmp_path):
    proc = run_cli("cap", "experiment", "没这个 run", "--runs-root", str(tmp_path / "runs"))
    assert proc.returncode == EXIT_USAGE


def test_experiment_unknown_compute_exits_two(tmp_path):
    new_run_via_cli(tmp_path)
    proc = run_cli("cap", "experiment", "r1", "--compute", "slurm",
                   "--runs-root", str(tmp_path / "runs"))
    assert proc.returncode == EXIT_USAGE
    assert "local" in proc.stderr  # 报错要列出可用的名字，不静默回退


def test_experiment_resume_unknown_backend_exits_two(tmp_path):
    new_run_via_cli(tmp_path)
    proc = run_cli("cap", "experiment", "r1", "--resume", "--backend", "codex",
                   "--runs-root", str(tmp_path / "runs"))
    assert proc.returncode == EXIT_USAGE
    assert "claude_code" in proc.stderr


def test_experiment_extends_the_budget_before_looping(tmp_path, monkeypatch, capsys):
    """续命是实验能力的参数：给了预算就改快照、清停止标记、journal 记一行，再接着跑。"""
    from framework.capabilities import experiment
    from framework.cli import main
    from framework.run.checkpoint import read_checkpoint, write_checkpoint

    run_dir, _ = start_run(tmp_path)
    write_checkpoint(run_dir, {**read_checkpoint(run_dir), "stop_reason": "patience"})
    seen = {}

    def fake_loop(run_dir, runner, compute, max_iters=None):
        seen["stop_reason"] = read_checkpoint(run_dir).get("stop_reason")
        return experiment.StopReason(reason="batch_exhausted", iter=0, best_metric=0.5)

    monkeypatch.setattr(experiment, "run_loop", fake_loop)
    code = main(["cap", "experiment", "r1", "--patience", "9", "--reason", "测试",
                 "--runs-root", str(tmp_path / "runs")])
    assert code == EXIT_OK and seen["stop_reason"] is None
    assert "patience: 99 → 9" in (run_dir / "journal.md").read_text(encoding="utf-8")
    assert capsys.readouterr().out.startswith("stop batch_exhausted")
    code = main(["cap", "experiment", "r1", "--reason", "没配预算",
                 "--runs-root", str(tmp_path / "runs")])
    assert code == EXIT_INVALID and "只在续命时" in capsys.readouterr().err


# ── cap：按名字跑一个能力 ────────────────────────────────────────────────
def test_show_caps_lists_by_stage_with_empty_stages_visible():
    proc = run_cli("show", "caps")
    assert proc.returncode == EXIT_OK, proc.stderr
    rows = [line.split("\t") for line in proc.stdout.splitlines()]
    assert [r[0] for r in rows] == ["文献", "假设", "设计", "设计", "实验", "实验", "分析", "写作",
                                    "验证"]
    assert [r[1] for r in rows] == ["-", "-", "baseline", "design", "experiment", "start",
                                    "analysis", "-", "verify"]
    assert rows[0][2] == "还没有这一步的能力"
    design = next(r for r in rows if r[1] == "design")
    assert design[2] == "接任务" and "used_by=intake" in design


def test_show_caps_json_is_descriptor_dicts_with_used_by():
    import json

    proc = run_cli("show", "caps", "--json")
    assert proc.returncode == EXIT_OK, proc.stderr
    descriptors = json.loads(proc.stdout)
    assert {d["name"] for d in descriptors} == {
        "analysis", "baseline", "design", "experiment", "start", "verify"}
    assert all({"inputs", "outputs", "params", "criteria", "stage", "title", "what", "used_by"}
               <= set(d) for d in descriptors)
    by_name = {d["name"]: d for d in descriptors}
    assert by_name["verify"]["used_by"] == ["auto-research"]
    assert by_name["verify"]["stage"] == "验证"


def test_show_workflows_and_flow_say_which_stages_they_cover():
    proc = run_cli("show", "workflows")
    assert proc.returncode == EXIT_OK, proc.stderr
    lines = proc.stdout.splitlines()
    assert lines[0].startswith("auto-research\t") and "覆盖 实验 → 分析 → 验证" in lines[0]
    assert lines[1].startswith("intake\t") and "覆盖 设计" in lines[1]
    proc = run_cli("show", "flow", "design", "baseline", "start", "experiment", "analysis")
    assert proc.returncode == EXIT_OK, proc.stderr
    assert "覆盖 设计 → 实验 → 分析" in proc.stdout and "没有验证" in proc.stdout  # 提醒不退非零


def test_cap_unknown_capability_is_a_usage_error(tmp_path):
    proc = run_cli("cap", "writing", "r1", "--runs-root", str(tmp_path))
    assert proc.returncode == EXIT_USAGE


def test_cap_verify_unknown_run_exits_two(tmp_path):
    proc = run_cli("cap", "verify", "nope", "--runs-root", str(tmp_path))
    assert proc.returncode == EXIT_USAGE
    assert "checkpoint" in proc.stderr


def test_cap_analysis_unknown_backend_exits_two(tmp_path):
    from tests.fixtures import runs_factory as rf

    run_dir = rf.make_run(tmp_path)
    proc = run_cli("cap", "analysis", "r1", "--backend", "nope", "--runs-root",
                   str(run_dir.parent))
    assert proc.returncode == EXIT_USAGE
    assert "未知的执行层后端" in proc.stderr


def test_cap_verify_exit_code_follows_the_verdict(tmp_path):
    from tests.fixtures import runs_factory as rf

    run_dir = rf.make_run(tmp_path)
    rf.write_analysis(run_dir, rf.good_analysis(run_dir))
    proc = run_cli("cap", "verify", "r1", "--runs-root", str(run_dir.parent))
    assert proc.returncode == EXIT_OK, proc.stderr
    assert proc.stdout.strip() == "verify PASS\tchecks=4\tpath=verify/report.json"
    rf.write_analysis(run_dir, rf.good_analysis(run_dir) + "\n另外 0.4321 也不错。\n")
    proc = run_cli("cap", "verify", "r1", "--tolerance", "0.02", "--runs-root",
                   str(run_dir.parent))
    assert proc.returncode == EXIT_INVALID
    assert proc.stdout == "" and "verify FAIL 1/4：prose_numbers_in_table" in proc.stderr


def test_cap_analysis_runs_the_capability_with_the_named_backend(tmp_path, monkeypatch, capsys):
    """进程内跑：剧本后端没法按名字从子进程里取，把取后端的那一步换掉即可。"""
    from framework.cli import main
    from tests.fixtures import runs_factory as rf

    run_dir = rf.make_run(tmp_path)
    runner = ScriptedRunner([{"analysis/analysis.md": rf.good_analysis(run_dir)}])
    monkeypatch.setattr("framework.cli._common.get_backend", lambda name: runner)
    code = main(["cap", "analysis", "r1", "--runs-root", str(run_dir.parent)])
    assert code == EXIT_OK
    assert capsys.readouterr().out.startswith("analysis ok\tclaims=4")
    proc = run_cli("show", "run", "r1", "--runs-root", str(run_dir.parent))
    assert proc.returncode == EXIT_OK, proc.stderr
    assert "analysis\tanalysis/analysis.md" in proc.stdout and "verify\t-" in proc.stdout
    run_cli("cap", "verify", "r1", "--runs-root", str(run_dir.parent))
    proc = run_cli("show", "run", "r1", "--runs-root", str(run_dir.parent))
    assert "verify\tPASS" in proc.stdout


# ── task publish：需求看板的发布键 ─────────────────────────────────────
def test_sign_task_writes_the_key_and_start_needs_it(tmp_path):
    pack = pf.make_pack(tmp_path, published=False)
    proc = run_cli("cap", "start", str(pack.task_dir), "--run-id", "r1",
                   "--runs-root", str(tmp_path / "runs"))
    assert proc.returncode == EXIT_INVALID and "还没发布" in proc.stderr
    assert not (tmp_path / "runs" / "r1").exists()

    proc = run_cli("sign", "task", str(pack.task_dir), "--by", "小王")
    assert proc.returncode == EXIT_OK, proc.stderr
    assert proc.stdout.startswith("ok toy\tby=小王\tat=")
    assert "next=ai4sci cap design" in proc.stdout
    proc = run_cli("cap", "start", str(pack.task_dir), "--run-id", "r1",
                   "--runs-root", str(tmp_path / "runs"))
    assert proc.returncode == EXIT_OK, proc.stderr


def test_sign_task_refuses_a_pack_whose_brief_is_missing(tmp_path):
    pack = pf.make_pack(tmp_path, published=False)
    (pack.task_dir / "design.md").unlink()
    proc = run_cli("sign", "task", str(pack.task_dir), "--by", "小王")
    assert proc.returncode == EXIT_INVALID and "design.md" in proc.stderr
    assert not (pack.task_dir / "publish.json").exists()


def test_sign_task_missing_dir_exits_two(tmp_path):
    assert run_cli("sign", "task", str(tmp_path / "nope")).returncode == EXIT_USAGE


def test_sign_run_writes_the_acceptance(tmp_path):
    from tests.fixtures.runs_factory import make_run

    run_dir = make_run(tmp_path)
    proc = run_cli("sign", "run", run_dir.name, "--by", "小王", "--runs-root", str(run_dir.parent))
    assert proc.returncode == EXIT_OK, proc.stderr
    assert proc.stdout.startswith(f"ok {run_dir.name}\tby=小王\tbest_iter=")
    assert (run_dir / "accept.json").is_file()
    proc = run_cli("sign", "run", "nope", "--runs-root", str(run_dir.parent))
    assert proc.returncode == EXIT_USAGE


# ── cap design：接任务的按钮（task 级能力，子命令从描述符生成）──────────────
def test_cap_design_missing_dir_exits_two(tmp_path):
    proc = run_cli("cap", "design", str(tmp_path / "nope"))
    assert proc.returncode == EXIT_USAGE


def test_cap_design_missing_feedback_file_exits_one(tmp_path):
    pack = pf.make_pack(tmp_path)
    proc = run_cli("cap", "design", str(pack.task_dir), "--feedback", "@/nonexistent/f.md")
    assert proc.returncode == EXIT_INVALID
    assert "--feedback" in proc.stderr


def test_cap_design_unpublished_exits_one_before_any_session(tmp_path, monkeypatch):
    monkeypatch.setenv("AI4SCI_RUNS_ROOT", str(tmp_path / "runs"))
    pack = pf.make_pack(tmp_path, published=False)
    proc = run_cli("cap", "design", str(pack.task_dir))
    assert proc.returncode == EXIT_INVALID
    assert "还没发布" in proc.stderr and "sign task" in proc.stderr
    assert not (tmp_path / "runs" / "design-toy").exists()


def test_cap_design_runs_the_executor_and_reports_the_stop(tmp_path, monkeypatch, capsys):
    """进程内跑：剧本后端没法按名字从子进程里取，把取后端的那一步换掉即可。"""
    import shutil

    from framework.cli import main
    from tests.test_executor_design import GOOD_DRAFT

    monkeypatch.setenv("AI4SCI_RUNS_ROOT", str(tmp_path / "runs"))
    pack = pf.make_pack(tmp_path)
    for name in ("harness", "run_0", "code"):
        shutil.rmtree(pack.task_dir / name)
    runner = ScriptedRunner([GOOD_DRAFT, {"harness/launcher.sh": pf.BARE_PYTHON_LAUNCHER_SH}])
    monkeypatch.setattr("framework.cli._common.get_backend", lambda name: runner)

    code = main(["cap", "design", str(pack.task_dir)])
    out = capsys.readouterr().out
    assert code == EXIT_OK
    assert out.startswith(
        "design ok\tsession=1\tchanged=4\tsealed=evaluate.py,launcher.sh,make_run0.sh")
    assert "next=对照 design.md" in out and "ai4sci cap baseline" in out
    assert (tmp_path / "runs" / "design-toy" / "executor" / "session-1" / "prompt.md").is_file()

    code = main(["cap", "design", str(pack.task_dir), "--feedback", "改坏它"])
    captured = capsys.readouterr()
    assert code == EXIT_INVALID
    assert captured.err.startswith("design draft\tsession=2\t")
    assert "裸调 python" in captured.err and "--feedback @" in captured.err


# ── cap baseline：跑 make_run0.sh，环境变量与内环同一组，跑完预检 ─────────
MAKE_RUN0_RECORDING = (
    "#!/usr/bin/env bash\nset -euo pipefail\n"
    ': "${AI4SCI_INNER_K:?}"\n: "${AI4SCI_BUDGET_S:?}"\n'
    'TASK_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"\n'
    'printf \'{"inner_k": "%s", "budget": "%s", "python": "%s"}\' '
    '"$AI4SCI_INNER_K" "$AI4SCI_BUDGET_S" "$AI4SCI_PYTHON" > "$TASK_DIR/baseline-env.json"\n'
)


def test_cap_baseline_runs_make_run0_with_the_guaranteed_env_and_reports_headroom(tmp_path):
    manifest = pf.default_manifest()
    manifest["budget"]["inner_k"] = 7
    manifest["metrics"][0]["attainable"] = 0.3
    pack = pf.make_pack(tmp_path, manifest=manifest)
    (pack.task_dir / "harness" / "make_run0.sh").write_text(MAKE_RUN0_RECORDING, encoding="utf-8")
    proc = run_cli("cap", "baseline", str(pack.task_dir))  # 环境不在，基线自己建
    assert proc.returncode == EXIT_OK, proc.stderr
    line = proc.stdout.strip()
    assert line.startswith("ok toy\tinner_k=7\tbaseline=0.5\tsigma=0.02\tgate=0.04\t")
    assert "attainable=0.3\troom=0.2（5.0 个门）" in line and "next=ai4sci show task" in line
    seen = json.loads((pack.task_dir / "baseline-env.json").read_text(encoding="utf-8"))
    assert seen["inner_k"] == "7"
    assert seen["budget"] == f"{manifest['budget']['wall_clock_s']:g}"
    assert seen["python"] == str(pack.task_dir / ".venv" / "bin" / "python")


def test_cap_baseline_stops_when_the_headroom_check_fails(tmp_path):
    manifest = pf.default_manifest()
    manifest["metrics"][0]["attainable"] = 0.49  # 基线 0.5 离尽头 0.01，门 0.04：无解
    pack = pf.make_pack(tmp_path, manifest=manifest)
    (pack.task_dir / "harness" / "make_run0.sh").write_text(MAKE_RUN0_RECORDING, encoding="utf-8")
    proc = run_cli("cap", "baseline", str(pack.task_dir))
    assert proc.returncode == EXIT_INVALID
    assert "无解" in proc.stderr and "baseline=0.5" in proc.stderr


def test_cap_baseline_without_script_builds_env_itself_and_needs_the_key(tmp_path):
    pack = pf.make_pack(tmp_path)
    proc = run_cli("cap", "baseline", str(pack.task_dir))
    assert proc.returncode == EXIT_INVALID and "make_run0.sh" in proc.stderr
    (pack.task_dir / "harness" / "make_run0.sh").write_text(MAKE_RUN0_RECORDING, encoding="utf-8")
    proc = run_cli("cap", "baseline", str(pack.task_dir))
    assert proc.returncode == EXIT_OK, proc.stderr  # 环境不在就按 env/ 建，不用人单独按一颗键
    assert (pack.task_dir / ".venv" / "bin" / "python").is_file()
    (pack.task_dir / "publish.json").unlink()
    proc = run_cli("cap", "baseline", str(pack.task_dir))
    assert proc.returncode == EXIT_INVALID and "还没发布" in proc.stderr


# ── flow check：按描述符对吃吐文件 ─────────────────────────────────────────
def test_show_flow_passes_the_whole_line_and_prints_it():
    proc = run_cli("show", "flow", "design", "baseline", "experiment", "analysis", "verify")
    assert proc.returncode == EXIT_OK, proc.stderr
    assert proc.stdout.strip() == ("ok 5 步：design → baseline → experiment → analysis → verify"
                                   "\t覆盖 设计 → 实验 → 分析 → 验证")


def test_show_flow_reports_every_gap_and_json_carries_them():
    proc = run_cli("show", "flow", "verify")
    assert proc.returncode == EXIT_INVALID
    assert "过桥" in proc.stderr and "analysis/analysis.md" in proc.stderr
    proc = run_cli("show", "flow", "verify", "--json")
    assert proc.returncode == EXIT_INVALID
    doc = json.loads(proc.stdout)
    assert doc["steps"] == ["verify"] and len(doc["problems"]) >= 2


def test_show_flow_unknown_capability_is_a_usage_error():
    proc = run_cli("show", "flow", "design", "nope")
    assert proc.returncode == EXIT_USAGE and "nope" in proc.stderr


# ── chat：终端里和协调 agent 聊 ─────────────────────────────────────────────
def test_chat_new_send_list_with_a_scripted_backend(tmp_path, monkeypatch, capsys):
    from framework.cli import main
    from tests.fixtures.scripted_chat import ScriptedChat, with_tool

    chat = ScriptedChat([with_tool("有三个任务包：a、b、c。", "Bash",
                                   {"command": ".venv/bin/ai4sci task list"}, "a\nb\nc")])
    monkeypatch.setattr("framework.cli.chat.get_chat", lambda name: chat)
    monkeypatch.setattr("framework.chat.guide.GUIDE_PATH", tmp_path / "README.md")
    (tmp_path / "README.md").write_text("# 指南\n按按钮。", encoding="utf-8")
    runs = str(tmp_path / "runs")

    assert main(["chat", "new", "--cwd", str(tmp_path), "--runs-root", runs]) == EXIT_OK
    chat_id = capsys.readouterr().out.split("\t")[0].split(" ")[1]
    assert chat_id.startswith("chat-")

    assert main(["chat", "send", chat_id, "有哪些任务包？", "--runs-root", runs]) == EXIT_OK
    out = capsys.readouterr().out.splitlines()
    assert out[0].startswith("[init] session=") and out[1].startswith("[tool] Bash ")
    assert out[2].startswith("[result] a") and out[3] == "有三个任务包：a、b、c。"
    assert out[4].startswith("done\tcost_usd=0.0100")
    assert chat.calls[0]["system_prompt"].startswith("# 你在服务里") and \
        "按按钮" in chat.calls[0]["system_prompt"]
    assert chat.calls[0]["allowed_paths"] == [tmp_path / "tasks", tmp_path / "runs"]

    assert main(["chat", "list", "--runs-root", runs]) == EXIT_OK
    assert capsys.readouterr().out.startswith(f"{chat_id}\tturns=1\tcost_usd=0.0100")


def test_chat_send_unknown_id_and_missing_file_exit_two(tmp_path):
    runs = str(tmp_path / "runs")
    assert run_cli("chat", "send", "nope", "hi", "--runs-root", runs).returncode == EXIT_USAGE
    proc = run_cli("chat", "new", "--cwd", str(tmp_path), "--runs-root", runs)
    chat_id = proc.stdout.split("\t")[0].split(" ")[1]
    proc = run_cli("chat", "send", chat_id, "@/nonexistent.md", "--runs-root", runs)
    assert proc.returncode == EXIT_USAGE and "消息文件" in proc.stderr
    assert run_cli("chat", "new", "--backend", "nope", "--runs-root", runs).returncode == EXIT_USAGE
