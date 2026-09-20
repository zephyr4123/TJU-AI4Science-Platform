"""`ai4sci` 命令行：驱动面的退出码与那一行话（纲领 P-10、P-14、P-19）。

子进程跑真命令（退出码、stdout / stderr 分工），进程内跑 `main()` 换剧本后端
（能力本身在各自的测试里）。
门：需求没确认任何能力不开工；输入冻住了改过就拒；照流程跑断点没签就拒。
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from compute.local import LocalCompute
from framework.contracts import output, requirement
from framework.workspace import outputs
from tests.fixtures import packs_factory as pf
from tests.fixtures import runs_factory as rf
from tests.fixtures.scripted_backend import ScriptedRunner
from tests.test_experiment_loop import start_run

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


def env_of(pack: pf.Pack, monkeypatch) -> None:
    """进程内跑 main() 时的同一件事：环境指定工作区与领域包。"""
    monkeypatch.setenv("AI4SCI_WORKSPACE", str(pack.workspace.root))
    monkeypatch.setenv("AI4SCI_DOMAINS_ROOT", str(pack.domains_root))


# ── workspace new / show workspaces / show workspace / templates ──────────────
def test_workspace_new_and_show_workspaces(tmp_path):
    env = {"AI4SCI_HOME": str(tmp_path)}
    made = run_cli("workspace", "new", "rahman-nll", "--title", "Rahman 稳定性", env=env)
    assert made.returncode == EXIT_OK, made.stderr
    assert made.stdout.startswith("ok rahman-nll\t")
    text = (tmp_path / "workspaces" / "rahman-nll" / "requirement.md").read_text(encoding="utf-8")
    assert text.startswith("# Rahman 稳定性\n") and "## 问题" in text  # generic 模板
    assert run_cli("workspace", "new", "rahman-nll", env=env).returncode == EXIT_INVALID
    assert run_cli("workspace", "new", "Bad", env=env).returncode == EXIT_INVALID
    assert run_cli("workspace", "new", "x", "--template", "nope", env=env).returncode == EXIT_USAGE
    ai = run_cli("workspace", "new", "vision", "--template", "ai", env=env)
    assert ai.returncode == EXIT_OK
    assert "## 指标与基线" in (tmp_path / "workspaces" / "vision" / "requirement.md").read_text()
    listed = run_cli("show", "workspaces", env=env)
    assert listed.returncode == EXIT_OK, listed.stderr
    assert listed.stdout.splitlines()[0].startswith("rahman-nll\tRahman 稳定性\t需求 未确认\t")
    templates = run_cli("show", "templates")
    assert templates.returncode == EXIT_OK
    assert [line.split("\t")[0] for line in templates.stdout.splitlines()] == [
        "ai", "cs", "generic", "materials"]
    one = run_cli("show", "template", "generic")
    assert one.returncode == EXIT_OK and one.stdout.startswith("# 课题标题")
    assert run_cli("show", "template", "nope").returncode == EXIT_USAGE


def test_outside_a_workspace_is_a_usage_error_that_says_what_to_do(tmp_path):
    proc = run_cli("show", "workspace", cwd=tmp_path)
    assert proc.returncode == EXIT_USAGE
    assert "不在任何工作区里" in proc.stderr and "workspace new" in proc.stderr


def test_show_workspace_walks_requirement_outputs_flows_and_jobs(tmp_path):
    run_dir, pack = rf.make_run(tmp_path)
    rf.write_analysis(pack, rf.good_analysis(run_dir))
    (pack.workspace.flows / "research.yaml").write_text(
        (REPO_ROOT / "workflows" / "research.yaml").read_text(encoding="utf-8"), encoding="utf-8")
    proc = run_cli("show", "workspace", cwd=run_dir)  # 从产出目录里往上找得到工作区
    assert proc.returncode == EXIT_OK, proc.stderr
    lines = proc.stdout.splitlines()
    assert lines[0] == "workspace\ttoy\t夹具课题"
    assert lines[1].startswith("requirement\tv1 by fixture ")
    assert "design\t1 次" in lines and "experiment\t1 次" in lines and "analysis\t1 次" in lines
    assert any(line.startswith("  experiment/1\tok\tauto-research\tfrom=design/1")
               for line in lines)
    assert "flow\tresearch\tstep=0/6\twaiting=assistant" in lines
    as_json = run_cli("show", "workspace", "--json", cwd=run_dir)
    doc = json.loads(as_json.stdout)
    assert doc["requirement"]["confirmed"] and [f["name"] for f in doc["flows"]] == ["research"]
    outs = run_cli("show", "outputs", cwd=run_dir)
    assert [line.split("\t")[0] for line in outs.stdout.splitlines()] == [
        "design/1", "experiment/1", "analysis/1"]
    only = run_cli("show", "outputs", "analysis", cwd=run_dir)
    assert only.stdout.startswith("analysis/1\tok\tanalysis\tfrom=experiment/1")
    assert run_cli("show", "outputs", "runs", cwd=run_dir).returncode == EXIT_USAGE
    one = run_cli("show", "output", "experiment/1", cwd=run_dir)
    assert one.returncode == EXIT_OK, one.stderr
    assert "id\texperiment/1" in one.stdout and "file\tledger.tsv" in one.stdout
    assert "signed\t-" in one.stdout
    assert run_cli("show", "output", "experiment/9", cwd=run_dir).returncode == EXIT_USAGE
    assert run_cli("show", "output", "r1", cwd=run_dir).returncode == EXIT_USAGE


# ── requirement confirm / sign：人的两处确认 ────────────────────────────────
def test_requirement_confirm_writes_the_lock_and_refuses_placeholders(tmp_path):
    ws = pf.make_workspace(tmp_path, "w", confirmed=False)
    ws.requirement.write_text(pf.REQUIREMENT + "\n## 预算\n\n待填\n", encoding="utf-8")
    proc = run_cli("requirement", "confirm", "--by", "张三", cwd=ws.root)
    assert proc.returncode == EXIT_INVALID and "待填" in proc.stderr
    ws.requirement.write_text(pf.REQUIREMENT, encoding="utf-8")
    proc = run_cli("requirement", "confirm", "--by", "张三", cwd=ws.root)
    assert proc.returncode == EXIT_OK, proc.stderr
    assert proc.stdout.startswith("ok w\tv1\tby=张三\t") and "flow take" in proc.stdout
    assert requirement.status(ws.root)["version"] == 1


def test_sign_writes_the_signature_and_refuses_bad_targets(tmp_path):
    pack = pf.make_pack(tmp_path)
    proc = run_cli("sign", "design/1", "--by", "李四", "--note", "看过了", **in_pack(pack))
    assert proc.returncode == EXIT_OK, proc.stderr
    assert proc.stdout.startswith("ok design/1\tby=李四\t")
    assert output.read_signed(pack.pack)["note"] == "看过了"
    again = run_cli("sign", "design/1", "--by", "李四", **in_pack(pack))
    assert again.returncode == EXIT_INVALID and "已经签过了" in again.stderr
    assert run_cli("sign", "design/9", "--by", "x", **in_pack(pack)).returncode == EXIT_USAGE
    assert run_cli("sign", "r1", "--by", "x", **in_pack(pack)).returncode == EXIT_USAGE
    shown = run_cli("show", "output", "design/1", **in_pack(pack))
    assert "signed\tyes\t李四" in shown.stdout


# ── cap：门、输入、断点、产出 ───────────────────────────────────────────────
def fake_loop_that_stops_at_once(monkeypatch, best: float = 0.5):
    """进程内跑 auto-research 时把内环换成剧本：这里测的是命令层，不是内环。"""
    from framework.capabilities import auto_research

    seen: list[Path] = []

    def fake_loop(run_dir, runner, compute, max_iters=None):
        seen.append(Path(run_dir))
        return auto_research.StopReason(reason="batch_exhausted", iter=0, best_metric=best)

    monkeypatch.setattr(auto_research, "run_loop", fake_loop)
    return seen


def test_cap_refuses_before_the_requirement_is_confirmed(tmp_path):
    pack = pf.make_pack(tmp_path, confirmed=False)
    proc = run_cli("cap", "auto-research", "--from", "design/1", **in_pack(pack))
    assert proc.returncode == EXIT_INVALID and "需求还没确认" in proc.stderr
    assert not (pack.workspace.root / "experiment").exists()
    requirement.confirm(pack.workspace.root, by="t")
    pack.workspace.requirement.write_text(pf.REQUIREMENT + "\n改了\n", encoding="utf-8")
    proc = run_cli("cap", "auto-research", "--from", "design/1", **in_pack(pack))
    assert proc.returncode == EXIT_INVALID and "又改过" in proc.stderr


def test_cap_auto_research_opens_an_output_and_continues_it(tmp_path, monkeypatch, capsys):
    from framework.cli import main

    pack = pf.make_pack(tmp_path)
    env_of(pack, monkeypatch)
    seen = fake_loop_that_stops_at_once(monkeypatch)
    code = main(["cap", "auto-research", "--from", "design/1"])
    out = capsys.readouterr().out
    assert code == EXIT_OK, out
    run_dir = pack.workspace.root / "experiment" / "1"
    assert seen == [run_dir]
    assert out.startswith("stop batch_exhausted\titer=0\tbest=0.5\toutput=experiment/1\t")
    assert out.rstrip().endswith("output=experiment/1")
    meta = output.read_meta(run_dir)
    assert meta.status == "ok" and meta.by == "auto-research" and meta.input_ids == ["design/1"]
    assert meta.requirement == 1 and meta.flow is None and meta.result.startswith("stop ")
    assert (run_dir / "checkpoint.json").is_file() and (run_dir / "work" / ".git").is_dir()
    # 接着跑：同一个产出，不另开；换输入不行；不是它产的不行
    assert main(["cap", "auto-research", "--continue", "experiment/1"]) == EXIT_OK
    assert len(seen) == 2 and not (pack.workspace.root / "experiment" / "2").exists()
    capsys.readouterr()
    code = main(["cap", "auto-research", "--continue", "experiment/1", "--from", "design/1"])
    assert code == EXIT_OK and len(seen) == 3  # 同样的输入可以再说一遍
    capsys.readouterr()
    code = main(["cap", "auto-research", "--continue", "design/1"])
    assert code == EXIT_INVALID and "接不了" in capsys.readouterr().err
    # 设计产出被引用后冻住：改了它，再开一次实验就拒
    (pack.pack / "scoring.yaml").write_text(
        (pack.pack / "scoring.yaml").read_text(encoding="utf-8") + "# 改\n", encoding="utf-8")
    code = main(["cap", "auto-research", "--from", "design/1"])
    assert code == EXIT_INVALID and "改过了" in capsys.readouterr().err


def test_cap_records_failures_on_disk_and_refuses_them_as_inputs(tmp_path):
    pack = pf.make_pack(tmp_path)
    (pack.pack / "harness" / "evaluate.py").write_text("# 改了但没更新 SHA256SUMS\n")
    proc = run_cli("cap", "auto-research", "--from", "design/1", **in_pack(pack))
    assert proc.returncode == EXIT_INVALID and "sha256" in proc.stderr.lower()
    assert "output=experiment/1（没成，留在盘上）" in proc.stderr
    meta = output.read_meta(pack.workspace.root / "experiment" / "1")
    assert meta.status == "failed" and "sha256" in meta.error.lower()
    proc = run_cli("cap", "analysis", "--from", "experiment/1", **in_pack(pack))
    assert proc.returncode == EXIT_INVALID and "没成（failed" in proc.stderr
    missing = run_cli("cap", "analysis", "--from", "experiment/9", **in_pack(pack))
    assert missing.returncode == EXIT_INVALID
    assert run_cli("cap", "analysis", "--from", "r1", **in_pack(pack)).returncode == EXIT_INVALID


def test_flow_take_then_stops_are_enforced_when_following_the_flow(tmp_path, monkeypatch, capsys):
    """纲领 P-15 / P-19：库里的流程先取成实例；照流程跑时，前一项后面有断点就得签了才能读。"""
    from framework.cli import main

    pack = pf.make_pack(tmp_path)
    env_of(pack, monkeypatch)
    fake_loop_that_stops_at_once(monkeypatch)
    assert run_cli("flow", "take", "nope", **in_pack(pack)).returncode == EXIT_USAGE
    taken = run_cli("flow", "take", "research", **in_pack(pack))
    assert taken.returncode == EXIT_OK, taken.stderr
    assert taken.stdout.startswith("ok research\tflows/research.yaml\t6 项")
    again = run_cli("flow", "take", "research", **in_pack(pack))
    assert again.returncode == EXIT_INVALID and "已经有" in again.stderr
    renamed = run_cli("flow", "take", "research", "--as", "research-5", **in_pack(pack))
    assert renamed.returncode == EXIT_OK and (pack.workspace.flows / "research-5.yaml").is_file()
    listed = run_cli("show", "flows", **in_pack(pack))
    assert listed.returncode == EXIT_OK, listed.stderr
    assert ("设计 → ◆评分指标核对 → 实验(auto-research) → 分析 → 验证 → ◆验收"
            in listed.stdout)
    (pack.workspace.flows / "zz.yaml").write_text("name: zz\n", encoding="utf-8")
    listed = run_cli("show", "flows", **in_pack(pack))
    assert listed.returncode == EXIT_INVALID and "zz.yaml: 缺 title" in listed.stderr
    (pack.workspace.flows / "zz.yaml").unlink()

    # 两条流程：不说照哪条就拒；design/1 没记在流程里（夹具直接造的），断点管不到它
    code = main(["cap", "auto-research", "--from", "design/1"])
    assert code == EXIT_INVALID and "--flow" in capsys.readouterr().err
    code = main(["cap", "auto-research", "--from", "design/1", "--flow", "nope"])
    assert code == EXIT_INVALID and "flow take nope" in capsys.readouterr().err
    _, meta = outputs.find_output(pack.workspace, "design/1")
    meta.flow, meta.step = "research", 0
    output.write_meta(pack.pack, meta)
    code = main(["cap", "auto-research", "--from", "design/1", "--flow", "research"])
    err = capsys.readouterr().err
    assert code == EXIT_INVALID and "断点「评分指标核对」" in err
    assert "ai4sci sign design/1" in err
    output.sign(pack.pack, by="人")
    code = main(["cap", "auto-research", "--from", "design/1", "--flow", "research"])
    assert code == EXIT_OK, capsys.readouterr().err
    meta = output.read_meta(pack.workspace.root / "experiment" / "1")
    assert meta.flow == "research" and meta.step == 2
    shown = run_cli("show", "workspace", **in_pack(pack))
    assert "flow\tresearch\tstep=3/6\twaiting=assistant" in shown.stdout
    assert "flow\tresearch-5\tstep=0/6\twaiting=assistant" in shown.stdout


def test_cap_detach_returns_a_job_id_and_the_job_finishes_on_its_own(tmp_path):
    """外层 #63：`--detach` 立刻打印作业号退出；子进程自己跑完回写产出与结论；
    show job / show jobs 能查。"""
    import time

    from framework.workspace import jobs

    run_dir, pack = rf.make_run(tmp_path)
    rf.write_analysis(pack, rf.good_analysis(run_dir))
    ws = pack.workspace
    proc = run_cli("cap", "verify", "--from", "analysis/1", "--from", "experiment/1", "--detach",
                   **in_pack(pack))
    assert proc.returncode == EXIT_OK, proc.stderr
    head, *fields = proc.stdout.strip().split("\t")
    job_id = head.split(" ", 1)[1]
    assert head.startswith("job job-") and "cap=verify" in fields and fields[-1].endswith(job_id)
    for _ in range(300):
        if jobs.load(ws.jobs, job_id).status != "running":
            break
        time.sleep(0.2)
    shown = run_cli("show", "job", job_id, **in_pack(pack))
    assert shown.returncode == EXIT_OK, shown.stderr
    assert shown.stdout.startswith(f"{job_id}\tdone\tverify\tverification/1\t")
    assert "verify PASS\t" in shown.stdout
    assert "argv\tai4sci cap verify" in shown.stdout and "--detach" not in shown.stdout
    listing = run_cli("show", "jobs", **in_pack(pack))
    assert listing.returncode == EXIT_OK and listing.stdout.startswith(job_id)
    assert run_cli("show", "job", "nope", **in_pack(pack)).returncode == EXIT_USAGE
    # 对话里调用的：子进程跑完去叫醒；这里对话不存在，叫醒的失败要记回作业，不能无声
    proc = run_cli("cap", "verify", "--from", "analysis/1", "--from", "experiment/1", "--detach",
                   cwd=ws.root, env={"AI4SCI_CHAT_ID": "chat-nope",
                                     "AI4SCI_DOMAINS_ROOT": str(pack.domains_root)})
    job_id = proc.stdout.split("\t")[0].split(" ", 1)[1]
    for _ in range(300):
        job = jobs.load(ws.jobs, job_id)
        if job.wake is not None:
            break
        time.sleep(0.2)
    assert job.chat_id == "chat-nope" and job.wake.startswith("failed: 对话不存在")


def test_finished_job_drops_its_job_id_before_waking_the_chat(tmp_path, monkeypatch):
    """叫醒起的 agent 继承作业进程的环境：作业号留着，它调用的每个 --detach 都会被拒。"""
    import argparse

    from framework.cli import cap as cap_cli
    from framework.workspace import jobs

    run_dir, pack = rf.make_run(tmp_path)
    rf.write_analysis(pack, rf.good_analysis(run_dir))
    seen: dict[str, object] = {}

    def fake_wake(ws, job):
        seen["job_id_env"] = os.environ.get("AI4SCI_JOB_ID")  # 叫醒那一刻环境里还有没有作业号
        return "done"

    monkeypatch.setattr(cap_cli.notify, "wake", fake_wake)
    ws = pack.workspace
    job = jobs.Job(job_id="job-t", cap="verify", stage="verification", argv=[], pid=1,
                   started_at="t", chat_id="chat-1")
    jobs._save(ws.jobs, job)
    monkeypatch.setenv("AI4SCI_JOB_ID", "job-t")
    env_of(pack, monkeypatch)
    module = cap_cli.discover()["verify"]
    args = argparse.Namespace(module=module, detach=False, inputs=["analysis/1", "experiment/1"],
                              flow="", tolerance=0.01, argv=[])
    assert cap_cli.cmd_cap(args) == EXIT_OK
    assert seen == {"job_id_env": None}
    job = jobs.load(ws.jobs, "job-t")
    assert job.wake == "done" and job.output == "verification/1"


def test_auto_research_extends_the_budget_before_looping(tmp_path, monkeypatch, capsys):
    """加预算是 auto-research 的参数：给了预算就改快照、清停止标记、journal 记一行，再接着跑。"""
    from framework.capabilities import auto_research as experiment
    from framework.cli import main
    from framework.experiment.checkpoint import read_checkpoint, write_checkpoint

    run_dir, pack = start_run(tmp_path)
    _, meta = outputs.find_output(pack.workspace, "experiment/1")
    outputs.close_output(run_dir, meta, ok=True, line="stop")
    env_of(pack, monkeypatch)
    write_checkpoint(run_dir, {**read_checkpoint(run_dir), "stop_reason": "patience"})
    seen = {}

    def fake_loop(run_dir, runner, compute, max_iters=None):
        seen["stop_reason"] = read_checkpoint(run_dir).get("stop_reason")
        return experiment.StopReason(reason="batch_exhausted", iter=0, best_metric=0.5)

    monkeypatch.setattr(experiment, "run_loop", fake_loop)
    code = main(["cap", "auto-research", "--continue", "experiment/1", "--patience", "9",
                 "--reason", "测试"])
    assert code == EXIT_OK and seen["stop_reason"] is None
    assert "patience: 99 → 9" in (run_dir / "journal.md").read_text(encoding="utf-8")
    assert capsys.readouterr().out.startswith("stop batch_exhausted")
    code = main(["cap", "auto-research", "--continue", "experiment/1", "--reason", "没配预算"])
    assert code == EXIT_INVALID and "只在加预算时" in capsys.readouterr().err


def test_show_caps_lists_stages_with_empty_stages_visible_and_five_columns():
    proc = run_cli("show", "caps")
    assert proc.returncode == EXIT_OK, proc.stderr
    lines = proc.stdout.splitlines()
    assert lines[0].startswith("文献\t-\t这个阶段还没有能力")
    assert "output new literature" in lines[0]
    assert lines[1].startswith("假设\t-\t")
    design = next(line for line in lines if line.startswith("设计\tdesign\t"))
    # 一行上屏，执行者种类不上屏
    assert "评分脚本与基线\t按需求写评分契约" in design and "助理" not in design
    assert "used_by=-" in design and "--domain --feedback" in design
    experiment = next(line for line in lines if line.startswith("实验\tauto-research\t"))
    assert "used_by=research" in experiment
    assert any(line.startswith("  职责：") for line in lines)
    assert any(line.startswith("  终止条件：") for line in lines)


def test_show_caps_json_is_descriptor_dicts_with_used_by():
    proc = run_cli("show", "caps", "--json")
    assert proc.returncode == EXIT_OK, proc.stderr
    doc = {c["name"]: c for c in json.loads(proc.stdout)}
    assert set(doc) == {"design", "auto-research", "analysis", "verify"}
    assert doc["auto-research"]["used_by"] == ["research"] and doc["verify"]["used_by"] == []
    assert doc["design"]["stage"] == "设计" and doc["design"]["stage_slug"] == "design"
    assert doc["auto-research"]["continuable"] is True
    assert "brings" in doc["verify"] and "stops" in doc["verify"]


def test_show_workflows_lists_stages_and_stops():
    proc = run_cli("show", "workflows")
    assert proc.returncode == EXIT_OK, proc.stderr
    assert proc.stdout.startswith("research\t从设计到验证\t设计 → ◆评分指标核对")
    assert proc.stdout.rstrip().endswith("→ 验证 → ◆验收")


def test_cap_unknown_capability_is_a_usage_error(tmp_path):
    proc = run_cli("cap", "teleport", cwd=tmp_path)
    assert proc.returncode == EXIT_USAGE


def test_cap_analysis_unknown_backend_exits_two(tmp_path):
    run_dir, pack = rf.make_run(tmp_path)
    proc = run_cli("cap", "analysis", "--from", "experiment/1", "--backend", "nope",
                   **in_pack(pack))
    assert proc.returncode == EXIT_USAGE and "nope" in proc.stderr


def test_cap_verify_exit_code_follows_the_verdict(tmp_path):
    run_dir, pack = rf.make_run(tmp_path)
    rf.write_analysis(pack, rf.good_analysis(run_dir))
    proc = run_cli("cap", "verify", "--from", "analysis/1", "--from", "experiment/1",
                   **in_pack(pack))
    assert proc.returncode == EXIT_OK, proc.stderr
    assert proc.stdout.startswith("verify PASS\tchecks=4")
    assert "output=verification/1" in proc.stdout
    rf.write_analysis(pack, rf.good_analysis(run_dir).replace("共 3 轮", "共 3 轮，另外 0.1234"))
    proc = run_cli("cap", "verify", "--from", "analysis/2", "--from", "experiment/1",
                   **in_pack(pack))
    assert proc.returncode == EXIT_INVALID
    assert "verify FAIL" in proc.stderr and "output=verification/2（没成，留在盘上）" in proc.stderr
    proc = run_cli("cap", "verify", "--from", "analysis/2", **in_pack(pack))
    assert proc.returncode == EXIT_INVALID and "--from experiment/<n>" in proc.stderr


def test_cap_analysis_runs_the_capability_with_the_named_backend(tmp_path, monkeypatch, capsys):
    """进程内跑：剧本后端没法按名字从子进程里取，把取后端的那一步换掉即可。"""
    from framework.cli import main

    run_dir, pack = rf.make_run(tmp_path)
    env_of(pack, monkeypatch)
    runner = ScriptedRunner([{"analysis.md": rf.good_analysis(run_dir)}])
    monkeypatch.setattr("framework.cli._common.get_backend", lambda name: runner)
    code = main(["cap", "analysis", "--from", "experiment/1"])
    assert code == EXIT_OK
    assert capsys.readouterr().out.startswith("analysis ok\tclaims=4")
    shown = run_cli("show", "output", "analysis/1", **in_pack(pack))
    assert shown.returncode == EXIT_OK and "file\tanalysis.md" in shown.stdout
    assert "from\texperiment/1" in shown.stdout


# ── output new：助理不经能力开产出 ─────────────────────────────────────────
def test_output_new_opens_a_directory_for_hand_written_outputs(tmp_path):
    pack = pf.make_pack(tmp_path)
    proc = run_cli("output", "new", "literature", "--title", "文献笔记", **in_pack(pack))
    assert proc.returncode == EXIT_OK, proc.stderr
    assert proc.stdout.startswith("ok literature/1\t") and "ai4sci sign literature/1" in proc.stdout
    meta = output.read_meta(pack.workspace.root / "literature" / "1")
    assert meta.by == "assistant" and meta.title == "文献笔记" and meta.status == "ok"
    proc = run_cli("output", "new", "hypothesis", "--from", "literature/1", "--by", "human",
                   **in_pack(pack))
    assert proc.returncode == EXIT_OK
    meta = output.read_meta(pack.workspace.root / "hypothesis" / "1")
    assert meta.by == "human" and meta.input_ids == ["literature/1"] and meta.title == "假设"
    assert run_cli("output", "new", "runs", **in_pack(pack)).returncode == EXIT_USAGE
    bad = run_cli("output", "new", "writing", "--from", "nope", **in_pack(pack))
    assert bad.returncode == EXIT_INVALID
    unconfirmed = pf.make_workspace(tmp_path / "other", "u", confirmed=False)
    proc = run_cli("output", "new", "literature", cwd=unconfirmed.root)
    assert proc.returncode == EXIT_INVALID and "需求还没确认" in proc.stderr


# ── design：写评分脚本、跑基线（进程内，剧本执行层）──────────────────────────
def test_cap_design_runs_the_executor_and_reports_the_stop(tmp_path, monkeypatch, capsys):
    from framework.cli import main
    from tests.test_capability_design import GOOD_DRAFT, SKILL_MD

    ws = pf.make_workspace(tmp_path, "toy")
    (ws.materials / "val.json").write_text('{"y": [1.0]}', encoding="utf-8")
    domains = tmp_path / "domains"
    (domains / "generic" / "skills" / "toy").mkdir(parents=True)
    (domains / "generic" / "profile.yaml").write_text("id: generic\n", encoding="utf-8")
    (domains / "generic" / "skills" / "toy" / "SKILL.md").write_text(SKILL_MD, encoding="utf-8")
    monkeypatch.setenv("AI4SCI_WORKSPACE", str(ws.root))
    monkeypatch.setenv("AI4SCI_DOMAINS_ROOT", str(domains))
    scoring = {k: v for k, v in pf.default_scoring().items() if k != "domain"}
    scoring["budget"]["min_delta"] = 0.001  # 夹具训练是确定性的，门靠 min_delta 撑起来
    draft = {**GOOD_DRAFT, "scoring.yaml": pf.to_yaml(scoring)}
    runner = ScriptedRunner([draft, {"harness/launcher.sh": pf.BARE_PYTHON_LAUNCHER_SH}])
    monkeypatch.setattr("framework.cli._common.get_backend", lambda name: runner)

    code = main(["cap", "design"])
    out = capsys.readouterr().out
    assert code == EXIT_OK, out
    assert out.startswith(
        "design ok\tsession=1\tchanged=5\tsealed=evaluate.py,launcher.sh,make_run0.sh")
    # 后半段：评分脚本封好就接着跑基线、算预检，一条命令到底
    assert "\tinner_k=" in out and "\tbaseline=" in out and "\tgate=" in out
    assert "auto-research --from design/1" in out and out.rstrip().endswith("output=design/1")
    pack = ws.root / "design" / "1"
    assert (pack / "executor" / "session-1" / "prompt.md").is_file()
    assert (pack / "baseline" / "results.json").is_file() and (pack / "data" / "val.json").is_file()
    assert output.read_meta(pack).params == {"domain": "generic"}

    code = main(["cap", "design", "--continue", "design/1", "--feedback", "改坏它"])
    captured = capsys.readouterr()
    assert code == EXIT_INVALID
    assert captured.err.startswith("design draft\tsession=2\t")
    assert "裸调 python" in captured.err and "--continue design/1 --feedback @" in captured.err
    assert output.read_meta(pack).status == "failed"
    assert run_cli("cap", "design", "--feedback", "@/nonexistent.md", cwd=ws.root,
                   env={"AI4SCI_DOMAINS_ROOT": str(domains)}).returncode == EXIT_INVALID


# ── 基线：跑 make_run0.sh，环境变量与内环同一组，跑完预检 ───────────────────
MAKE_RUN0_RECORDING = (
    "#!/usr/bin/env bash\nset -euo pipefail\n"
    ': "${AI4SCI_INNER_K:?}"\n: "${AI4SCI_BUDGET_S:?}"\n'
    'TASK_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"\n'
    'printf \'{"inner_k": "%s", "budget": "%s", "python": "%s"}\' '
    '"$AI4SCI_INNER_K" "$AI4SCI_BUDGET_S" "$AI4SCI_PYTHON" > "$TASK_DIR/baseline-env.json"\n'
)


def test_baseline_runs_make_run0_with_the_guaranteed_env_and_reports_headroom(tmp_path):
    from framework.capabilities.design.baseline import run_baseline

    scoring = pf.default_scoring()
    scoring["budget"]["inner_k"] = 7
    scoring["metrics"][0]["attainable"] = 0.3
    pack = pf.make_pack(tmp_path, scoring=scoring)
    (pack.pack / "harness" / "make_run0.sh").write_text(MAKE_RUN0_RECORDING, encoding="utf-8")
    line = run_baseline(pack.pack, LocalCompute())  # 环境不在，基线自己建
    assert line.startswith("inner_k=7\tbaseline=0.5\tsigma=0.02\tgate=0.04\t")
    assert "attainable=0.3\troom=0.2（5.0 个门）" in line
    seen = json.loads((pack.pack / "baseline-env.json").read_text(encoding="utf-8"))
    assert seen["inner_k"] == "7"
    assert seen["budget"] == f"{scoring['budget']['wall_clock_s']:g}"
    assert seen["python"] == str(pack.pack / ".venv" / "bin" / "python")
    assert (pack.pack / ".venv" / "bin" / "python").is_file()


def test_baseline_stops_when_the_headroom_check_fails_or_the_script_is_missing(tmp_path):
    from framework.capabilities.design.baseline import run_baseline
    from framework.contracts.capability import CapabilityFailed

    scoring = pf.default_scoring()
    scoring["metrics"][0]["attainable"] = 0.49  # 基线 0.5 离尽头 0.01，门 0.04：无解
    pack = pf.make_pack(tmp_path, scoring=scoring)
    (pack.pack / "harness" / "make_run0.sh").write_text(MAKE_RUN0_RECORDING, encoding="utf-8")
    with pytest.raises(CapabilityFailed, match="无解") as caught:
        run_baseline(pack.pack, LocalCompute())
    assert "baseline=0.5" in str(caught.value)
    (pack.pack / "harness" / "make_run0.sh").unlink()
    with pytest.raises(CapabilityFailed, match="make_run0.sh"):
        run_baseline(pack.pack, LocalCompute())


# ── chat：终端里和两位助理聊 ────────────────────────────────────────────────
def test_chat_new_send_list_in_the_workspace_with_a_scripted_backend(tmp_path, monkeypatch,
                                                                       capsys):
    from framework import paths
    from framework.chat import guide
    from framework.cli import main
    from framework.workspace import root as workspace
    from tests.fixtures.scripted_chat import ScriptedChat, streamed, with_tool

    chat = ScriptedChat([with_tool("有一份需求。", "Bash", {"command": "ai4sci show workspace"},
                                   "ok w")])
    monkeypatch.setattr("framework.cli.chat.get_chat", lambda name: chat)
    monkeypatch.setitem(guide.GUIDE_PATHS, guide.WORKSPACE, tmp_path / "README.md")
    (tmp_path / "README.md").write_text("# 指南\n用流程不造流程。", encoding="utf-8")
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
        "用流程不造流程" in chat.calls[0]["system_prompt"]
    assert chat.calls[0]["cwd"] == ws.root
    assert chat.calls[0]["allowed_paths"] == [ws.root]
    assert chat.calls[0]["readable_paths"] == [paths.workflows_root(), paths.templates_root()]

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
    from framework.workspace import root as workspace
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
    """纲领 P-16：`--studio` 是编辑台的流程助理——另一份指南、对话在 studio/ 下、只能写库。"""
    from framework import paths
    from framework.chat import guide
    from framework.cli import main
    from tests.fixtures.scripted_chat import ScriptedChat, reply

    chat = ScriptedChat([reply("拼好了")])
    monkeypatch.setattr("framework.cli.chat.get_chat", lambda name: chat)
    monkeypatch.setitem(guide.GUIDE_PATHS, guide.STUDIO, tmp_path / "studio.md")
    (tmp_path / "studio.md").write_text("# 造流程\n只写库。", encoding="utf-8")
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
    assert "只写库" in prompt and "流程助理" in prompt
    assert chat.calls[0]["cwd"] == library.parent and chat.calls[0]["allowed_paths"] == [library]
    assert chat.calls[0]["readable_paths"] == []
    assert main(["chat", "list", "--studio"]) == EXIT_OK
    assert capsys.readouterr().out.startswith(f"{chat_id}\tturns=1")
    assert main(["chat", "list"]) == EXIT_USAGE  # 没在工作区里：研究助理那边没得列


def test_chat_send_unknown_id_and_missing_file_exit_two(tmp_path):
    from framework.workspace import root as workspace

    ws = workspace.create(tmp_path / "workspaces", "w")
    assert run_cli("chat", "send", "nope", "hi", cwd=ws.root).returncode == EXIT_USAGE
    proc = run_cli("chat", "new", cwd=ws.root)
    chat_id = proc.stdout.split("\t")[0].split(" ")[1]
    proc = run_cli("chat", "send", chat_id, "@/nonexistent.md", cwd=ws.root)
    assert proc.returncode == EXIT_USAGE and "消息文件" in proc.stderr
    assert run_cli("chat", "new", "--backend", "nope", cwd=ws.root).returncode == EXIT_USAGE


# ── serve 注入给页面后端的几个函数：真清单、真检查 ────────────────────────
def test_serve_helpers_check_a_draft_and_list_the_catalog():
    """编辑台边拼边问：名字、标题、说明还没填也只报阶段的问题；清单每个带五栏与 used_by。"""
    from framework.cli import serve

    ok = serve._check_workflow(
        {"stages": ["假设", {"断点": "看一眼"}, {"设计": ["design"]}, "分析"]})
    assert ok["problems"] == [] and ok["covers"] == ["假设", "设计", "分析"]
    assert ok["remarks"] == ["有实验或分析、没有验证：数字没人回溯，结果不能算可信"]
    bad = serve._check_workflow({"name": "x", "stages": [{"设计": ["verify"]}, "断点", "断点"]})
    assert bad["problems"] == ["第 2 项与第 3 项都是断点：两个断点挨着等于一个"]
    bad = serve._check_workflow({"stages": [{"设计": ["verify"]}]})
    assert "属于「验证」阶段" in bad["problems"][0]
    catalog = {c["name"]: c for c in serve._catalog()}
    assert catalog["auto-research"]["used_by"] == ["research"] and catalog["verify"]["does"]
    assert [w["name"] for w in serve._workflows()] == ["research"]
    assert set(serve._descriptor_map()) == {"design", "auto-research", "analysis", "verify"}


def test_env_resolve_writes_a_complete_lock_into_materials(tmp_path, monkeypatch, capsys):
    """外层 #117：研究者没有环境，助理按包名算清单（会联网），写进 materials/env/。"""
    from framework.cli import main
    from framework.workspace import root as workspace

    ws = workspace.create(tmp_path / "workspaces", "w1", template="# w1\n\n## 问题\n\n有。\n")
    monkeypatch.setenv("AI4SCI_WORKSPACE", str(ws.root))
    assert main(["env", "resolve", "requests"]) == 2  # 没 python-version 又没 --python
    assert "--python" in capsys.readouterr().err
    assert main(["env", "resolve", "--python", "3", "requests"]) == 2
    capsys.readouterr()
    assert main(["env", "resolve", "--python", "3.12", "requests"]) == 0
    out = capsys.readouterr().out
    assert out.startswith("ok materials/env/requirements.lock\tpython=3.12\tpins=")
    lock = (ws.materials / "env" / "requirements.lock").read_text(encoding="utf-8")
    assert "requests==" in lock and "urllib3==" in lock
    assert (ws.materials / "env" / "python-version").read_text(encoding="utf-8") == "3.12\n"
    assert main(["env", "resolve", "idna"]) == 0  # 第二次不用再给 --python
