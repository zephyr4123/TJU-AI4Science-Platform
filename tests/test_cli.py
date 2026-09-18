"""`ai4sci` CLI 的测试：用退出码说话。

用 subprocess 起真进程而不是直接调 main()，因为协调层拿到的就是退出码与两个流，
进程边界上的行为（0 / 1 / 2、问题走 stderr、ok 走 stdout）才是契约。
命令不带工作区路径（纲领 P-15）：子进程的 cwd 放在工作区里，CLI 自己往上找标记文件。
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from compute.local import LocalCompute
from framework.capabilities.auto_research import run_loop
from framework.run import gitwork
from tests.fixtures import packs_factory as pf
from tests.fixtures.scripted_backend import ScriptedRunner
from tests.test_experiment_loop import start_run, train_for_mse

REPO_ROOT = Path(__file__).resolve().parent.parent

EXIT_OK = 0
EXIT_INVALID = 1
EXIT_USAGE = 2


def run_cli(*args: str, cwd: Path | None = None,
            env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "framework.cli", *args],
        capture_output=True, text=True, timeout=120, check=False, cwd=cwd or REPO_ROOT,
        env={**os.environ, "PYTHONPATH": str(REPO_ROOT), **(env or {})},
    )


def in_pack(pack: pf.Pack) -> dict:
    """在夹具的工作区里跑：cwd 是工作区根，领域包指到夹具的（P-5：不靠仓里的 domains/）。"""
    return {"cwd": pack.workspace.root, "env": {"AI4SCI_DOMAINS_ROOT": str(pack.domains_root)}}


def in_run(run_dir: Path) -> dict:
    ws_root = run_dir.parent.parent
    return {"cwd": ws_root, "env": {"AI4SCI_DOMAINS_ROOT": str(ws_root.parent.parent / "domains")}}


def env_of(pack: pf.Pack, monkeypatch) -> None:
    """进程内跑 main() 时的同一件事：环境指定工作区与领域包。"""
    monkeypatch.setenv("AI4SCI_WORKSPACE", str(pack.workspace.root))
    monkeypatch.setenv("AI4SCI_DOMAINS_ROOT", str(pack.domains_root))


# ── show task / workspaces、workspace new ─────────────────────────────────
def test_show_task_ok_exits_zero(tmp_path):
    pack = pf.make_pack(tmp_path)
    proc = run_cli("show", "task", **in_pack(pack))
    assert proc.returncode == EXIT_OK, proc.stderr
    assert proc.stdout.strip() == "ok toy"


def test_show_task_finds_the_workspace_from_a_subdirectory(tmp_path):
    pack = pf.make_pack(tmp_path)
    proc = run_cli("show", "task", cwd=pack.task_dir / "code",
                   env={"AI4SCI_DOMAINS_ROOT": str(pack.domains_root)})
    assert proc.returncode == EXIT_OK, proc.stderr


def test_show_task_problems_exit_one_and_print_one_per_line(tmp_path):
    manifest = pf.default_manifest()
    manifest["metrics"][0]["direction"] = "沿着感觉走"
    del manifest["metrics"][0]["primary"]
    pack = pf.make_pack(tmp_path, manifest=manifest)
    proc = run_cli("show", "task", **in_pack(pack))
    assert proc.returncode == EXIT_INVALID
    assert proc.stdout == ""
    lines = [ln for ln in proc.stderr.splitlines() if ln.strip()]
    assert len(lines) == 2, proc.stderr
    assert any("direction" in ln for ln in lines)
    assert any("primary" in ln for ln in lines)


def test_outside_a_workspace_is_a_usage_error_that_says_what_to_do(tmp_path):
    for args in (("show", "task"), ("cap", "init", "--python", "3.12", "--lock", "x"),
                 ("sign", "task", "--by", "x"), ("show", "jobs"), ("flow", "take", "intake")):
        proc = run_cli(*args, cwd=tmp_path)
        assert proc.returncode == EXIT_USAGE, args
        assert "不在任何工作区里" in proc.stderr and "workspace new" in proc.stderr


def test_show_task_without_a_task_pack_exits_one(tmp_path):
    from framework.run import workspace

    ws = workspace.create(tmp_path / "workspaces", "fresh")
    proc = run_cli("show", "task", cwd=ws.root)
    assert proc.returncode == EXIT_INVALID and "还没有任务包" in proc.stderr
    proc = run_cli("sign", "task", "--by", "x", cwd=ws.root)
    assert proc.returncode == EXIT_INVALID and "还没有任务包" in proc.stderr


def test_workspace_new_and_show_workspaces(tmp_path):
    env = {"AI4SCI_HOME": str(tmp_path)}
    proc = run_cli("workspace", "new", "rahman-nll", "--title", "Rahman 稳定性", env=env)
    assert proc.returncode == EXIT_OK, proc.stderr
    assert proc.stdout.startswith("ok rahman-nll\t") and "cap init" in proc.stdout
    assert (tmp_path / "workspaces" / "rahman-nll" / "workspace.yaml").is_file()
    assert run_cli("workspace", "new", "rahman-nll", env=env).returncode == EXIT_INVALID
    bad = run_cli("workspace", "new", "Bad Name", env=env)
    assert bad.returncode == EXIT_INVALID and "小写英文" in bad.stderr
    proc = run_cli("show", "workspaces", env=env)
    assert proc.returncode == EXIT_OK, proc.stderr
    assert proc.stdout.startswith("rahman-nll\tRahman 稳定性\t")


def test_real_task_pack_validates_via_cli():
    ws_root = REPO_ROOT / "workspaces" / "mlp-regression"
    if not (ws_root / "task").is_dir():
        pytest.skip("仓里没有 workspaces/mlp-regression，框架测试不依赖它")
    proc = run_cli("show", "task", cwd=ws_root)
    assert proc.returncode == EXIT_OK, proc.stderr
    assert proc.stdout.strip() == "ok mlp-regression"


# ── auto-research / show run：实验内环的驱动面 ─────────────────────────
def new_run_in_place(tmp_path, run_id: str = "r1"):
    """夹具工作区里直接建一个 run（不走执行层）：给只看 run 的命令当靶子。"""
    from framework.run.lifecycle import new_run

    pack = pf.make_pack(tmp_path)
    run_dir = new_run(pack.task_dir, pack.workspace.runs, run_id, domains_root=pack.domains_root)
    return pack, run_dir


def fake_loop_that_stops_at_once(monkeypatch, best: float = 0.5):
    """进程内跑 auto-research 时把内环换成剧本：这里测的是命令层，不是内环。"""
    from framework.capabilities import auto_research

    seen: list[Path] = []

    def fake_loop(run_dir, runner, compute, max_iters=None):
        seen.append(Path(run_dir))
        return auto_research.StopReason(reason="batch_exhausted", iter=0, best_metric=best)

    monkeypatch.setattr(auto_research, "run_loop", fake_loop)
    return seen


def test_auto_research_opens_the_run_inside_the_workspace(tmp_path, monkeypatch, capsys):
    from framework.cli import main

    pack = pf.make_pack(tmp_path)
    env_of(pack, monkeypatch)
    seen = fake_loop_that_stops_at_once(monkeypatch)
    code = main(["cap", "auto-research", "--run-id", "r1"])
    out = capsys.readouterr().out
    assert code == EXIT_OK and seen == [pack.workspace.runs / "r1"]
    assert out.startswith("stop batch_exhausted\titer=0\tbest=0.5\trun=r1\t")
    assert out.rstrip().endswith("next=ai4sci cap analysis r1")
    run_dir = pack.workspace.runs / "r1"
    assert (run_dir / "checkpoint.json").is_file()
    assert (run_dir / "work" / ".git").is_dir()
    assert (run_dir / "manifest.yaml").is_file()
    assert (run_dir / "journal.md").is_file()
    # 同名再按一次：接着跑，不是拒绝
    assert main(["cap", "auto-research", "--run-id", "r1"]) == EXIT_OK and len(seen) == 2


def test_flow_take_then_auto_research_with_workflow_snapshots_it_and_reads_the_note(
        tmp_path, monkeypatch, capsys):
    """纲领 P-15：库里的流先取成实例才能照着开 run；快照进 run、跑成后记到实验那个阶段；
    名字不对在开 run 之前就拒。"""
    from framework.cli import main

    pack = pf.make_pack(tmp_path)
    env_of(pack, monkeypatch)
    fake_loop_that_stops_at_once(monkeypatch)
    code = main(["cap", "auto-research", "--run-id", "r0", "--workflow", "research"])
    assert code == EXIT_INVALID and "flow take research" in capsys.readouterr().err
    assert not (pack.workspace.runs / "r0").exists()

    assert run_cli("flow", "take", "nope", **in_pack(pack)).returncode == EXIT_USAGE
    taken = run_cli("flow", "take", "research", **in_pack(pack))
    assert taken.returncode == EXIT_OK, taken.stderr
    assert taken.stdout.startswith("ok research\tflows/research.yaml\t8 项")
    assert (pack.workspace.flows / "research.yaml").is_file()
    again = run_cli("flow", "take", "research", **in_pack(pack))
    assert again.returncode == EXIT_INVALID and "已经有" in again.stderr
    renamed = run_cli("flow", "take", "research", "--as", "research-5", **in_pack(pack))
    assert renamed.returncode == EXIT_OK and (pack.workspace.flows / "research-5.yaml").is_file()
    listed = run_cli("show", "flows", **in_pack(pack))
    assert listed.returncode == EXIT_OK, listed.stderr
    names = [line.split("\t")[0] for line in listed.stdout.splitlines() if not line.startswith(" ")]
    assert names == ["research-5", "research"]  # 按文件名排（'-' 排在 '.' 前）
    assert "假设 → ◆publish → 设计 → ◆ → 实验(auto-research) → 分析 → 验证 → ◆accept" in (
        listed.stdout)
    # 助理随手写个只有一行的文件：清单照列、那一条报问题、退 1；不是整张清单炸掉
    (pack.workspace.flows / "zz.yaml").write_text("name: zz\n", encoding="utf-8")
    listed = run_cli("show", "flows", **in_pack(pack))
    assert listed.returncode == EXIT_INVALID and "zz.yaml: 缺 title" in listed.stderr
    assert listed.stdout.startswith("research-5\t")
    (pack.workspace.flows / "zz.yaml").unlink()

    code = main(["cap", "auto-research", "--run-id", "r1", "--workflow", "research"])
    assert code == EXIT_OK, capsys.readouterr().err
    run_dir = pack.workspace.runs / "r1"
    assert (run_dir / "workflow" / "research.yaml").is_file()
    assert (run_dir / "flow.json").is_file()
    shown = run_cli("show", "run", "r1", **in_pack(pack))
    assert shown.returncode == EXIT_OK, shown.stderr
    assert "workflow\tresearch\tstep=5/8\twaiting=assistant\tnext=分析阶段" in shown.stdout
    # 已经开过的 run 不能再换流
    code = main(["cap", "auto-research", "--run-id", "r1", "--workflow", "research-5"])
    assert code == EXIT_INVALID and "已经开过了" in capsys.readouterr().err


def test_auto_research_on_broken_pack_exits_one_before_any_session(tmp_path):
    pack = pf.make_pack(tmp_path)
    (pack.task_dir / "harness" / "evaluate.py").write_text("# 改了但没更新 SHA256SUMS\n")
    proc = run_cli("cap", "auto-research", **in_pack(pack))  # 真后端也没事：门口就拒，不起会话
    assert proc.returncode == EXIT_INVALID
    assert "sha256" in proc.stderr.lower()
    assert not pack.workspace.runs.exists() or not any(pack.workspace.runs.iterdir())


def test_cap_init_creates_the_task_dir_of_the_workspace(tmp_path):
    from framework.run import workspace

    lock = tmp_path / "freeze.txt"
    lock.write_text("numpy==2.0.0\n", encoding="utf-8")
    ws = workspace.create(tmp_path / "workspaces", "t1")
    proc = run_cli("cap", "init", "--python", "3.12", "--lock", str(lock), cwd=ws.root)
    assert proc.returncode == EXIT_OK, proc.stderr
    assert proc.stdout.startswith("ok t1\tdomain=generic\tdata=1 个文件")
    assert (ws.task / "manifest.yaml").is_file()
    again = run_cli("cap", "init", "--python", "3.12", "--lock", str(lock), cwd=ws.root)
    assert again.returncode == EXIT_INVALID and "已经有任务包" in again.stderr


def test_cap_detach_returns_a_job_id_and_the_job_finishes_on_its_own(tmp_path, monkeypatch):
    """外层 #63：`--detach` 立刻打印作业号退出；子进程自己跑完回写；show job / show jobs 能查。"""
    import time

    from framework.run import jobs, workspace

    lock = tmp_path / "freeze.txt"
    lock.write_text("numpy==2.0.0\n", encoding="utf-8")
    ws = workspace.create(tmp_path / "workspaces", "t")
    proc = run_cli("cap", "init", "--python", "3.12", "--lock", str(lock), "--detach", cwd=ws.root)
    assert proc.returncode == EXIT_OK, proc.stderr
    head, *fields = proc.stdout.strip().split("\t")
    job_id = head.split(" ", 1)[1]
    assert head.startswith("job job-") and "cap=init" in fields and fields[-1].endswith(job_id)
    for _ in range(300):
        if jobs.load(ws.jobs, job_id).status != "running":
            break
        time.sleep(0.2)
    shown = run_cli("show", "job", job_id, cwd=ws.root)
    assert shown.returncode == EXIT_OK, shown.stderr
    assert shown.stdout.startswith(f"{job_id}\tdone\tinit\t") and "ok t\t" in shown.stdout
    assert "argv\tai4sci cap init" in shown.stdout and "--detach" not in shown.stdout
    listing = run_cli("show", "jobs", cwd=ws.root)
    assert listing.returncode == EXIT_OK and listing.stdout.startswith(job_id)
    assert run_cli("show", "job", "nope", cwd=ws.root).returncode == EXIT_USAGE
    # 对话里按的：子进程跑完去叫醒；这里对话不存在，叫醒的失败要记回作业，不能无声
    other = workspace.create(tmp_path / "workspaces", "t2")
    proc = run_cli("cap", "init", "--python", "3.12", "--lock", str(lock), "--detach",
                   cwd=other.root, env={"AI4SCI_CHAT_ID": "chat-nope"})
    job_id = proc.stdout.split("\t")[0].split(" ", 1)[1]
    for _ in range(300):
        job = jobs.load(other.jobs, job_id)
        if job.wake is not None:
            break
        time.sleep(0.2)
    assert job.chat_id == "chat-nope" and job.wake.startswith("failed: 对话不存在")


def test_finished_job_drops_its_job_id_before_waking_the_chat(tmp_path, monkeypatch):
    """叫醒起的 agent 继承作业进程的环境：作业号留着，它按的每个 --detach 都会被拒。"""
    import argparse

    from framework.cli import cap as cap_cli
    from framework.run import jobs, workspace

    seen: dict[str, object] = {}

    def fake_wake(ws, job):
        seen["job_id_env"] = os.environ.get("AI4SCI_JOB_ID")  # 叫醒那一刻环境里还有没有作业号
        return "done"

    monkeypatch.setattr(cap_cli.notify, "wake", fake_wake)
    ws = workspace.create(tmp_path / "workspaces", "t")
    job = jobs.Job(job_id="job-t", cap="init", level="task", target="t", argv=[], pid=1,
                   started_at="t", chat_id="chat-1")
    jobs._save(ws.jobs, job)
    monkeypatch.setenv("AI4SCI_JOB_ID", "job-t")
    monkeypatch.setenv("AI4SCI_WORKSPACE", str(ws.root))
    lock = tmp_path / "freeze.txt"
    lock.write_text("numpy==2.0.0\n", encoding="utf-8")
    module = cap_cli.discover()["init"]
    args = argparse.Namespace(module=module, detach=False, domain="generic", materials="",
                              python="3.12", lock=str(lock), argv=[])
    assert cap_cli.cmd_cap(args) == EXIT_OK
    assert seen == {"job_id_env": None} and jobs.load(ws.jobs, "job-t").wake == "done"


def test_show_run_prints_best_and_ledger_tail(tmp_path):
    pack, _ = new_run_in_place(tmp_path)
    proc = run_cli("show", "run", "r1", **in_pack(pack))
    assert proc.returncode == EXIT_OK, proc.stderr
    fields = dict(line.split("\t", 1) for line in proc.stdout.splitlines() if "\t" in line)
    assert fields["run_id"] == "r1"
    assert fields["source"] == "-", "夹具 manifest 没写 source，打 '-' 不留空"
    assert fields["best_metric"] == "0.5"
    assert fields["stop_reason"] == "-"
    assert fields["ledger_rows"] == "0"


def test_show_run_prints_the_manifest_source(tmp_path):
    from framework.run.lifecycle import new_run

    manifest = pf.default_manifest()
    manifest["source"] = "docs/cases/boehm-stat5-petab"
    pack = pf.make_pack(tmp_path, manifest=manifest)
    new_run(pack.task_dir, pack.workspace.runs, "r1", domains_root=pack.domains_root)
    proc = run_cli("show", "run", "r1", **in_pack(pack))
    assert "source\tdocs/cases/boehm-stat5-petab" in proc.stdout.splitlines()


def test_show_run_reconciles_the_ledger_and_exits_one_when_git_lost_a_row(tmp_path):
    """status 顺手对账：被弃的那一轮的 attempts ref 被删掉，账本就跟 git 对不上了。"""
    run_dir, _ = start_run(tmp_path)  # run_id 是 r1，落在夹具工作区的 runs/ 下
    run_loop(run_dir, ScriptedRunner([train_for_mse(0.5)]), LocalCompute(), max_iters=1)
    refs = gitwork.attempt_refs(run_dir / "work")
    assert refs, "改坏的那一轮该留在 refs/attempts/ 下"
    ok = run_cli("show", "run", "r1", **in_run(run_dir))
    assert ok.returncode == EXIT_OK, ok.stderr

    gitwork.git(run_dir / "work", "update-ref", "-d", next(iter(refs)))
    proc = run_cli("show", "run", "r1", **in_run(run_dir))
    assert proc.returncode == EXIT_INVALID
    assert "refs/attempts" in proc.stderr
    assert "ledger_rows\t1" in proc.stdout, "对账失败也要先把状态打完"


def test_show_run_unknown_run_exits_two(tmp_path):
    pack = pf.make_pack(tmp_path)
    proc = run_cli("show", "run", "没这个 run", **in_pack(pack))
    assert proc.returncode == EXIT_USAGE


def test_auto_research_unknown_compute_exits_two(tmp_path):
    pack, _ = new_run_in_place(tmp_path)
    proc = run_cli("cap", "auto-research", "--run-id", "r1", "--compute", "slurm", **in_pack(pack))
    assert proc.returncode == EXIT_USAGE
    assert "local" in proc.stderr  # 报错要列出可用的名字，不静默回退


def test_auto_research_resume_unknown_backend_exits_two(tmp_path):
    pack, _ = new_run_in_place(tmp_path)
    proc = run_cli("cap", "auto-research", "--run-id", "r1", "--resume", "--backend", "codex",
                   **in_pack(pack))
    assert proc.returncode == EXIT_USAGE
    assert "claude_code" in proc.stderr


def test_auto_research_extends_the_budget_before_looping(tmp_path, monkeypatch, capsys):
    """续命是 auto-research 的参数：给了预算就改快照、清停止标记、journal 记一行，再接着跑。"""
    from framework.capabilities import auto_research as experiment
    from framework.cli import main
    from framework.run.checkpoint import read_checkpoint, write_checkpoint

    run_dir, pack = start_run(tmp_path)
    env_of(pack, monkeypatch)
    write_checkpoint(run_dir, {**read_checkpoint(run_dir), "stop_reason": "patience"})
    seen = {}

    def fake_loop(run_dir, runner, compute, max_iters=None):
        seen["stop_reason"] = read_checkpoint(run_dir).get("stop_reason")
        return experiment.StopReason(reason="batch_exhausted", iter=0, best_metric=0.5)

    monkeypatch.setattr(experiment, "run_loop", fake_loop)
    code = main(["cap", "auto-research", "--run-id", "r1", "--patience", "9", "--reason", "测试"])
    assert code == EXIT_OK and seen["stop_reason"] is None
    assert "patience: 99 → 9" in (run_dir / "journal.md").read_text(encoding="utf-8")
    assert capsys.readouterr().out.startswith("stop batch_exhausted")
    code = main(["cap", "auto-research", "--run-id", "r1", "--reason", "没配预算"])
    assert code == EXIT_INVALID and "只在续命时" in capsys.readouterr().err


# ── cap：按名字跑一个能力 ────────────────────────────────────────────────
def test_show_caps_lists_stages_with_empty_stages_visible_and_five_columns():
    proc = run_cli("show", "caps")
    assert proc.returncode == EXIT_OK, proc.stderr
    rows = [line.split("\t") for line in proc.stdout.splitlines() if not line.startswith("  ")]
    assert [r[0] for r in rows] == ["文献", "假设", "设计", "实验", "分析", "写作", "验证"]
    assert [r[1] for r in rows] == ["-", "init", "design", "auto-research", "analysis", "-",
                                    "verify"]
    assert rows[0][2] == "这个阶段还没有能力"
    auto = next(r for r in rows if r[1] == "auto-research")
    assert auto[2] == "auto-research" and auto[3] == "助理" and "used_by=research" in auto
    columns = [line.strip().split("：", 1)[0] for line in proc.stdout.splitlines()
               if line.startswith("  ")]
    assert columns == ["干什么", "不干什么", "要带什么进来", "留下什么", "什么时候停"] * 5


def test_show_caps_json_is_descriptor_dicts_with_used_by():
    proc = run_cli("show", "caps", "--json")
    assert proc.returncode == EXIT_OK, proc.stderr
    descriptors = json.loads(proc.stdout)
    assert {d["name"] for d in descriptors} == {"analysis", "auto-research", "design", "init",
                                                "verify"}
    assert all({"does", "does_not", "brings", "leaves", "stops", "params", "stage", "title",
                "used_by"} <= set(d) for d in descriptors)
    assert not any("inputs" in d or "outputs" in d for d in descriptors)  # 路径表不再是接口
    by_name = {d["name"]: d for d in descriptors}
    assert by_name["auto-research"]["used_by"] == ["research"]
    assert by_name["verify"]["used_by"] == [] and by_name["verify"]["stage"] == "验证"
    assert [p["name"] for p in by_name["auto-research"]["params"]][:2] == ["run_id", "workflow"]


def test_show_workflows_lists_stages_and_stops():
    proc = run_cli("show", "workflows")
    assert proc.returncode == EXIT_OK, proc.stderr
    assert proc.stdout.splitlines() == [
        "research\t从课题到验证\t假设 → ◆publish → 设计 → ◆ → 实验(auto-research) → 分析 → 验证"
        " → ◆accept"]
    proc = run_cli("show", "workflows", "--json")
    [doc] = json.loads(proc.stdout)
    assert doc["covers"] == ["假设", "设计", "实验", "分析", "验证"] and doc["problems"] == []
    assert doc["stages"][1] == {"kind": "stop", "key": "publish", "note": "发布"}


def test_cap_unknown_capability_is_a_usage_error(tmp_path):
    proc = run_cli("cap", "writing", "r1", cwd=tmp_path)
    assert proc.returncode == EXIT_USAGE


def test_cap_verify_unknown_run_exits_two(tmp_path):
    pack = pf.make_pack(tmp_path)
    proc = run_cli("cap", "verify", "nope", **in_pack(pack))
    assert proc.returncode == EXIT_USAGE
    assert "checkpoint" in proc.stderr


def test_cap_analysis_unknown_backend_exits_two(tmp_path):
    from tests.fixtures import runs_factory as rf

    run_dir = rf.make_run(tmp_path)
    proc = run_cli("cap", "analysis", "r1", "--backend", "nope", **in_run(run_dir))
    assert proc.returncode == EXIT_USAGE
    assert "未知的执行层后端" in proc.stderr


def test_cap_verify_exit_code_follows_the_verdict(tmp_path):
    from tests.fixtures import runs_factory as rf

    run_dir = rf.make_run(tmp_path)
    rf.write_analysis(run_dir, rf.good_analysis(run_dir))
    proc = run_cli("cap", "verify", "r1", **in_run(run_dir))
    assert proc.returncode == EXIT_OK, proc.stderr
    assert proc.stdout.strip() == "verify PASS\tchecks=4\tpath=verify/report.json"
    rf.write_analysis(run_dir, rf.good_analysis(run_dir) + "\n另外 0.4321 也不错。\n")
    proc = run_cli("cap", "verify", "r1", "--tolerance", "0.02", **in_run(run_dir))
    assert proc.returncode == EXIT_INVALID
    assert proc.stdout == "" and "verify FAIL 1/4：prose_numbers_in_table" in proc.stderr


def test_cap_analysis_runs_the_capability_with_the_named_backend(tmp_path, monkeypatch, capsys):
    """进程内跑：剧本后端没法按名字从子进程里取，把取后端的那一步换掉即可。"""
    from framework.cli import main
    from tests.fixtures import runs_factory as rf

    run_dir = rf.make_run(tmp_path)
    monkeypatch.setenv("AI4SCI_WORKSPACE", str(run_dir.parent.parent))
    runner = ScriptedRunner([{"analysis/analysis.md": rf.good_analysis(run_dir)}])
    monkeypatch.setattr("framework.cli._common.get_backend", lambda name: runner)
    code = main(["cap", "analysis", "r1"])
    assert code == EXIT_OK
    assert capsys.readouterr().out.startswith("analysis ok\tclaims=4")
    proc = run_cli("show", "run", "r1", **in_run(run_dir))
    assert proc.returncode == EXIT_OK, proc.stderr
    assert "analysis\tanalysis/analysis.md" in proc.stdout and "verify\t-" in proc.stdout
    run_cli("cap", "verify", "r1", **in_run(run_dir))
    proc = run_cli("show", "run", "r1", **in_run(run_dir))
    assert "verify\tPASS" in proc.stdout


# ── sign task：需求看板的发布键 ─────────────────────────────────────────
def test_sign_task_writes_the_key_and_auto_research_needs_it(tmp_path, monkeypatch, capsys):
    from framework.cli import main

    pack = pf.make_pack(tmp_path, published=False)
    proc = run_cli("cap", "auto-research", "--run-id", "r1", **in_pack(pack))  # 门口就拒，不起会话
    assert proc.returncode == EXIT_INVALID and "还没发布" in proc.stderr
    assert not (pack.workspace.runs / "r1").exists()

    proc = run_cli("sign", "task", "--by", "小王", **in_pack(pack))
    assert proc.returncode == EXIT_OK, proc.stderr
    assert proc.stdout.startswith("ok toy\tby=小王\tat=")
    assert proc.stdout.rstrip().endswith("next=ai4sci cap design")
    env_of(pack, monkeypatch)
    fake_loop_that_stops_at_once(monkeypatch)
    assert main(["cap", "auto-research", "--run-id", "r1"]) == EXIT_OK, capsys.readouterr().err


def test_sign_task_refuses_a_pack_whose_brief_is_missing(tmp_path):
    pack = pf.make_pack(tmp_path, published=False)
    (pack.task_dir / "design.md").unlink()
    proc = run_cli("sign", "task", "--by", "小王", **in_pack(pack))
    assert proc.returncode == EXIT_INVALID and "design.md" in proc.stderr
    assert not (pack.task_dir / "publish.json").exists()


def test_sign_run_writes_the_acceptance(tmp_path):
    from tests.fixtures.runs_factory import make_run

    run_dir = make_run(tmp_path)
    proc = run_cli("sign", "run", run_dir.name, "--by", "小王", **in_run(run_dir))
    assert proc.returncode == EXIT_OK, proc.stderr
    assert proc.stdout.startswith(f"ok {run_dir.name}\tby=小王\tbest_iter=")
    assert (run_dir / "accept.json").is_file()
    proc = run_cli("sign", "run", "nope", **in_run(run_dir))
    assert proc.returncode == EXIT_USAGE


# ── cap design：写评分脚本、跑基线（task 级能力，子命令从描述符生成）──────────────
def test_cap_design_missing_feedback_file_exits_one(tmp_path):
    pack = pf.make_pack(tmp_path)
    proc = run_cli("cap", "design", "--feedback", "@/nonexistent/f.md", **in_pack(pack))
    assert proc.returncode == EXIT_INVALID
    assert "--feedback" in proc.stderr


def test_cap_design_unpublished_exits_one_before_any_session(tmp_path):
    pack = pf.make_pack(tmp_path, published=False)
    proc = run_cli("cap", "design", **in_pack(pack))
    assert proc.returncode == EXIT_INVALID
    assert "还没发布" in proc.stderr and "sign task" in proc.stderr
    assert not (pack.workspace.runs / "design").exists()


def test_cap_design_runs_the_executor_and_reports_the_stop(tmp_path, monkeypatch, capsys):
    """进程内跑：剧本后端没法按名字从子进程里取，把取后端的那一步换掉即可。"""
    import shutil

    from framework.cli import main
    from tests.test_executor_design import GOOD_DRAFT

    manifest = pf.default_manifest()
    manifest["budget"]["min_delta"] = 0.001  # 夹具训练是确定性的，σ=0，门靠 min_delta 撑起来
    pack = pf.make_pack(tmp_path, manifest=manifest)
    env_of(pack, monkeypatch)
    for name in ("harness", "run_0", "code"):
        shutil.rmtree(pack.task_dir / name)
    # 草稿里的 make_run0.sh 得真出 run_0/：跑三遍 launcher、把三份 results 收进 repeats/、算 σ
    draft = {**GOOD_DRAFT, "harness/make_run0.sh": MAKE_RUN0_THREE_REPEATS}
    runner = ScriptedRunner([draft, {"harness/launcher.sh": pf.BARE_PYTHON_LAUNCHER_SH}])
    monkeypatch.setattr("framework.cli._common.get_backend", lambda name: runner)

    code = main(["cap", "design"])
    out = capsys.readouterr().out
    assert code == EXIT_OK, out
    assert out.startswith(
        "design ok\tsession=1\tchanged=4\tsealed=evaluate.py,launcher.sh,make_run0.sh")
    # 后半段：评分脚本封好就接着跑基线、算预检，一条命令到底
    assert "\tinner_k=" in out and "\tbaseline=" in out and "\tgate=" in out
    assert "next=对照 design.md" in out and out.rstrip().endswith("ai4sci cap auto-research")
    assert (pack.workspace.runs / "design" / "executor" / "session-1" / "prompt.md").is_file()
    assert (pack.task_dir / "run_0" / "results.json").is_file()

    code = main(["cap", "design", "--feedback", "改坏它"])
    captured = capsys.readouterr()
    assert code == EXIT_INVALID
    assert captured.err.startswith("design draft\tsession=2\t")
    assert "裸调 python" in captured.err and "--feedback @" in captured.err


# ── 写评分脚本、跑基线的后半段：跑 make_run0.sh，环境变量与内环同一组，跑完预检 ─────────
MAKE_RUN0_THREE_REPEATS = (
    "#!/usr/bin/env bash\nset -euo pipefail\n"
    'TASK_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"\n'
    'mkdir -p "$TASK_DIR/run_0/repeats"\n'
    "for seed in 1 2 3; do\n"
    '  AI4SCI_SEED=$seed "$TASK_DIR/harness/launcher.sh"\n'
    '  cp "$TASK_DIR/results.json" "$TASK_DIR/run_0/repeats/results-$seed.json"\n'
    "done\n"
    'cp "$TASK_DIR/results.json" "$TASK_DIR/run_0/results.json"\n'
    """"$AI4SCI_PYTHON" - "$TASK_DIR" <<'PY'
import json, sys
from pathlib import Path
run0 = Path(sys.argv[1]) / "run_0"
files = sorted(run0.glob("repeats/*.json"))
values = [json.loads(p.read_text())["metrics"]["val_mse"] for p in files]
mean = sum(values) / len(values)
sigma = (sum((v - mean) ** 2 for v in values) / (len(values) - 1)) ** 0.5
doc = {"val_mse": {"sigma": sigma, "seeds": [1, 2, 3], "values": values}}
(run0 / "sigma.json").write_text(json.dumps(doc))
PY
"""
)
MAKE_RUN0_RECORDING = (
    "#!/usr/bin/env bash\nset -euo pipefail\n"
    ': "${AI4SCI_INNER_K:?}"\n: "${AI4SCI_BUDGET_S:?}"\n'
    'TASK_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"\n'
    'printf \'{"inner_k": "%s", "budget": "%s", "python": "%s"}\' '
    '"$AI4SCI_INNER_K" "$AI4SCI_BUDGET_S" "$AI4SCI_PYTHON" > "$TASK_DIR/baseline-env.json"\n'
)


def test_baseline_runs_make_run0_with_the_guaranteed_env_and_reports_headroom(tmp_path):
    from framework.capabilities.design.baseline import run_baseline

    manifest = pf.default_manifest()
    manifest["budget"]["inner_k"] = 7
    manifest["metrics"][0]["attainable"] = 0.3
    pack = pf.make_pack(tmp_path, manifest=manifest)
    (pack.task_dir / "harness" / "make_run0.sh").write_text(MAKE_RUN0_RECORDING, encoding="utf-8")
    line = run_baseline(pack.workspace)  # 环境不在，基线自己建
    assert line.startswith("inner_k=7\tbaseline=0.5\tsigma=0.02\tgate=0.04\t")
    assert "attainable=0.3\troom=0.2（5.0 个门）" in line
    seen = json.loads((pack.task_dir / "baseline-env.json").read_text(encoding="utf-8"))
    assert seen["inner_k"] == "7"
    assert seen["budget"] == f"{manifest['budget']['wall_clock_s']:g}"
    assert seen["python"] == str(pack.task_dir / ".venv" / "bin" / "python")
    assert (pack.task_dir / ".venv" / "bin" / "python").is_file()


def test_baseline_stops_when_the_headroom_check_fails_or_the_key_is_missing(tmp_path):
    from framework.capabilities.design.baseline import run_baseline
    from framework.contracts.capability import CapabilityFailed
    from framework.contracts.publish import NotPublished

    manifest = pf.default_manifest()
    manifest["metrics"][0]["attainable"] = 0.49  # 基线 0.5 离尽头 0.01，门 0.04：无解
    pack = pf.make_pack(tmp_path, manifest=manifest)
    (pack.task_dir / "harness" / "make_run0.sh").write_text(MAKE_RUN0_RECORDING, encoding="utf-8")
    with pytest.raises(CapabilityFailed, match="无解") as caught:
        run_baseline(pack.workspace)
    assert "baseline=0.5" in str(caught.value)
    (pack.task_dir / "harness" / "make_run0.sh").unlink()
    with pytest.raises(CapabilityFailed, match="make_run0.sh"):
        run_baseline(pack.workspace)
    (pack.task_dir / "publish.json").unlink()
    with pytest.raises(NotPublished, match="还没发布"):
        run_baseline(pack.workspace)


# ── chat：终端里和两位助理聊 ────────────────────────────────────────────────
def test_chat_new_send_list_in_the_workspace_with_a_scripted_backend(tmp_path, monkeypatch,
                                                                       capsys):
    from framework import paths
    from framework.chat import guide
    from framework.cli import main
    from framework.run import workspace
    from tests.fixtures.scripted_chat import ScriptedChat, streamed, with_tool

    chat = ScriptedChat([with_tool("有一份需求。", "Bash", {"command": "ai4sci show task"},
                                   "ok w")])
    monkeypatch.setattr("framework.cli.chat.get_chat", lambda name: chat)
    monkeypatch.setitem(guide.GUIDE_PATHS, guide.WORKSPACE, tmp_path / "README.md")
    (tmp_path / "README.md").write_text("# 指南\n用流不造流。", encoding="utf-8")
    ws = workspace.create(tmp_path / "workspaces", "w")
    monkeypatch.setenv("AI4SCI_WORKSPACE", str(ws.root))

    assert main(["chat", "new"]) == EXIT_OK
    chat_id = capsys.readouterr().out.split("\t")[0].split(" ")[1]
    assert chat_id.startswith("chat-") and (ws.chats / chat_id / "meta.json").is_file()

    assert main(["chat", "send", chat_id, "需求在哪？"]) == EXIT_OK
    out = capsys.readouterr().out.splitlines()
    assert out[0].startswith("[init] session=") and out[1].startswith("[tool] Bash ")
    assert out[2].startswith("[result] ok w") and out[3] == "有一份需求。"
    assert out[4].startswith("done\tcost_usd=0.0100")
    assert chat.calls[0]["system_prompt"].startswith("# 你在服务里") and \
        "用流不造流" in chat.calls[0]["system_prompt"]
    assert chat.calls[0]["cwd"] == ws.root
    assert chat.calls[0]["allowed_paths"] == [ws.task, ws.flows, ws.runs]
    assert chat.calls[0]["readable_paths"] == [paths.workflows_root()]

    assert main(["chat", "list"]) == EXIT_OK
    assert capsys.readouterr().out.startswith(f"{chat_id}\tturns=1\tcost_usd=0.0100")

    # 逐字吐的一轮：片段接在一行里打，完整 text 到了只补换行，不重复打一遍（外层 #65）
    chat.turns.append(streamed("基线跑完了，均值 21.49。", pieces=4))
    assert main(["chat", "send", chat_id, "怎么样了？"]) == EXIT_OK
    out = capsys.readouterr().out.splitlines()
    assert out[1] == "基线跑完了，均值 21.49。" and out[2].startswith("done\t")


def test_chat_new_and_send_take_model_and_effort_from_the_backends_list(tmp_path, monkeypatch,
                                                                         capsys):
    """外层 #86：`--model` / `--effort` 只认后端自报的清单；选了记进对话，list 里看得见。"""
    from backends import Tuning
    from framework.chat import conversation, guide
    from framework.cli import main
    from framework.run import workspace
    from tests.fixtures.scripted_chat import ScriptedChat, reply

    chat = ScriptedChat([reply("好"), reply("好")])
    monkeypatch.setattr("framework.cli.chat.get_chat", lambda name: chat)
    monkeypatch.setitem(guide.GUIDE_PATHS, guide.WORKSPACE, tmp_path / "README.md")
    (tmp_path / "README.md").write_text("# 指南\n", encoding="utf-8")
    ws = workspace.create(tmp_path / "workspaces", "w")
    monkeypatch.setenv("AI4SCI_WORKSPACE", str(ws.root))

    assert main(["chat", "new", "--model", "gpt"]) == EXIT_USAGE
    assert "模型 'gpt' 不在清单上；可选：a, b" in capsys.readouterr().err
    assert main(["chat", "new", "--model", "b", "--effort", "low"]) == EXIT_OK
    chat_id = capsys.readouterr().out.split("\t")[0].split(" ")[1]
    assert conversation.load_conversation(ws.chats, chat_id).tuning == Tuning("b", "low")

    assert main(["chat", "send", chat_id, "一", "--effort", "ultra"]) == EXIT_USAGE
    assert "思考深度 'ultra' 不在清单上" in capsys.readouterr().err and chat.calls == []
    assert main(["chat", "send", chat_id, "一", "--effort", "high"]) == EXIT_OK
    capsys.readouterr()
    assert chat.calls[0]["tuning"] == Tuning("b", "high")  # 模型沿用开对话时选的
    assert main(["chat", "send", chat_id, "二"]) == EXIT_OK
    capsys.readouterr()
    assert chat.calls[1]["tuning"] == Tuning("b", "high")
    assert main(["chat", "list"]) == EXIT_OK
    assert capsys.readouterr().out.rstrip().endswith("backend=claude_code\tmodel=b\teffort=high")


def test_chat_studio_talks_to_the_flow_builder_and_only_writes_the_library(tmp_path, monkeypatch,
                                                                            capsys):
    """纲领 P-16：`--studio` 是编辑台的造流助理——另一份指南、对话在 studio/ 下、只能写库。"""
    from framework import paths
    from framework.chat import guide
    from framework.cli import main
    from tests.fixtures.scripted_chat import ScriptedChat, reply

    chat = ScriptedChat([reply("拼好了")])
    monkeypatch.setattr("framework.cli.chat.get_chat", lambda name: chat)
    monkeypatch.setitem(guide.GUIDE_PATHS, guide.STUDIO, tmp_path / "studio.md")
    (tmp_path / "studio.md").write_text("# 造流\n只写库。", encoding="utf-8")
    library = tmp_path / "lib" / "workflows"
    library.mkdir(parents=True)
    monkeypatch.setenv("AI4SCI_HOME", str(tmp_path))
    monkeypatch.setenv(paths.WORKFLOWS_ROOT_ENV, str(library))

    assert main(["chat", "new", "--studio"]) == EXIT_OK
    chat_id = capsys.readouterr().out.split("\t")[0].split(" ")[1]
    assert (tmp_path / "studio" / "chats" / chat_id / "meta.json").is_file()
    assert main(["chat", "send", chat_id, "拼一条", "--studio"]) == EXIT_OK
    capsys.readouterr()
    prompt = chat.calls[0]["system_prompt"]
    assert "只写库" in prompt and "造流助理" in prompt
    assert chat.calls[0]["cwd"] == library.parent and chat.calls[0]["allowed_paths"] == [library]
    assert chat.calls[0]["readable_paths"] == []
    assert main(["chat", "list", "--studio"]) == EXIT_OK
    assert capsys.readouterr().out.startswith(f"{chat_id}\tturns=1")
    assert main(["chat", "list"]) == EXIT_USAGE  # 没在工作区里：研究助理那边没得列


def test_chat_send_unknown_id_and_missing_file_exit_two(tmp_path):
    from framework.run import workspace

    ws = workspace.create(tmp_path / "workspaces", "w")
    assert run_cli("chat", "send", "nope", "hi", cwd=ws.root).returncode == EXIT_USAGE
    proc = run_cli("chat", "new", cwd=ws.root)
    chat_id = proc.stdout.split("\t")[0].split(" ")[1]
    proc = run_cli("chat", "send", chat_id, "@/nonexistent.md", cwd=ws.root)
    assert proc.returncode == EXIT_USAGE and "消息文件" in proc.stderr
    assert run_cli("chat", "new", "--backend", "nope", cwd=ws.root).returncode == EXIT_USAGE


# ── serve 注入给页面后端的几个函数：真清单、真检查 ────────────────────────
def test_serve_helpers_check_a_draft_and_list_the_catalog():
    """页面拼流台边拼边问：名字、标题、说明还没填也只报阶段的问题；清单每颗带五栏与 used_by。"""
    from framework.cli import serve

    ok = serve._check_workflow({"stages": ["假设", {"断点": "发布"}, {"设计": ["design"]}, "分析"]})
    assert ok["problems"] == [] and ok["covers"] == ["假设", "设计", "分析"]
    assert ok["remarks"] == ["有实验或分析、没有验证：数字没人回溯，结果不能算可信"]
    bad = serve._check_workflow({"name": "x", "stages": [{"设计": ["verify"]}, "断点", "断点"]})
    assert bad["problems"] == ["x.yaml: 第 2 项与第 3 项都是断点：两个断点挨着等于一个"]
    bad = serve._check_workflow({"stages": [{"设计": ["verify"]}]})
    assert "属于「验证」间" in bad["problems"][0]
    catalog = {c["name"]: c for c in serve._catalog()}
    assert catalog["auto-research"]["used_by"] == ["research"] and catalog["verify"]["does"]
    assert [w["name"] for w in serve._workflows()] == ["research"]
