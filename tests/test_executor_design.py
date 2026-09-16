"""设计步骤：零模型的部分（组提示、判越界、封 harness、ruff、validate）用剧本执行层测全。

执行层写什么由剧本决定，所以能一条条摆出来：合约的草稿、越界、会话死掉、什么都没写、
裸 python、lint 不过、第二版带现状与反馈。评分脚本对不对不在这里测——那是人签字的事。
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from framework.executor import design
from tests.fixtures import packs_factory as pf
from tests.fixtures.scripted_backend import ScriptedRunner

BRIEF = "code/ 写 predictions.json：{\"y_pred\": [...]}；evaluate.py 算 val_mse 写 results.json。"
SKILL_MD = ("---\nname: toy\ndescription: 夹具 skill\n---\n\n"
            "用 json 模块读写，别 import 第三方库。\n")
MAKE_RUN0_SH = (
    "#!/usr/bin/env bash\nset -euo pipefail\n"
    'export AI4SCI_PYTHON="${AI4SCI_PYTHON:-.venv/bin/python}"\n'
    'AI4SCI_SEED=42 harness/launcher.sh\n'
)
GOOD_DRAFT = {
    "harness/launcher.sh": pf.LAUNCHER_SH,
    "harness/evaluate.py": pf.EVALUATE_PY,
    "harness/make_run0.sh": MAKE_RUN0_SH,
    "code/train.py": pf.TRAIN_PY,
}


@pytest.fixture
def pack(tmp_path):
    """接任务那一刻的任务包：有 manifest、env、data、design.md，没有 harness、code、run_0。"""
    made = pf.make_pack(tmp_path)
    for name in ("harness", "run_0", "code"):
        shutil.rmtree(made.task_dir / name)
    (made.task_dir / design.BRIEF_NAME).write_text(BRIEF, encoding="utf-8")
    skill = made.domains_root / "generic" / "skills" / "toy" / "SKILL.md"
    skill.parent.mkdir(parents=True)
    skill.write_text(SKILL_MD, encoding="utf-8")
    return made


def run_design(pack, *moves, feedback: str = "", reports: list[str] | None = None,
               **runner_kwargs):
    runner = ScriptedRunner(list(moves), **runner_kwargs)
    runner.reports = list(reports or [])
    outcome = design.design_task(pack.task_dir, pack.domains_root, runner, pack.root / "runs",
                                 feedback=feedback)
    return runner, outcome


def test_good_draft_is_sealed_lint_clean_and_validates(pack):
    runner, outcome = run_design(pack, GOOD_DRAFT)
    assert outcome.session == 1 and outcome.problems == []
    assert outcome.sealed == ["evaluate.py", "launcher.sh", "make_run0.sh"]
    assert outcome.changed_files == sorted(GOOD_DRAFT)
    hdir = pack.task_dir / "harness"
    for name in ("launcher.sh", "make_run0.sh"):
        assert (hdir / name).stat().st_mode & 0o111, f"{name} 没有执行位"
    listed = [ln.split("  ")[1] for ln in (hdir / "SHA256SUMS").read_text().splitlines()]
    assert listed == outcome.sealed
    # 证据都在：提示原文、事件流搬到了会话目录，任务目录里不留 .ai4sci
    assert outcome.log_dir == pack.root / "runs" / "design-toy" / "executor" / "session-1"
    assert (outcome.log_dir / "prompt.md").read_text(encoding="utf-8") == runner.prompts[0]
    assert list(outcome.log_dir.glob("executor-*.jsonl"))
    assert not (pack.task_dir / ".ai4sci").exists()


def test_prompt_carries_manifest_brief_skills_rules_and_escaped_dollars(pack):
    runner, _ = run_design(pack, GOOD_DRAFT)
    prompt = runner.prompts[0]
    for token in ("id: toy", "val_mse", BRIEF, "### skill: toy", "别 import 第三方库",
                  design.LINT_SELECT, str(design.LINT_LINE_LENGTH), "从零写",
                  '"$AI4SCI_PYTHON"', "${AI4SCI_PYTHON:?"):
        assert token in prompt, token
    assert "description: 夹具 skill" not in prompt  # frontmatter 不进提示
    assert "这次要改什么" not in prompt


def test_missing_brief_fails_before_spending_on_the_executor(pack):
    (pack.task_dir / design.BRIEF_NAME).unlink()
    runner = ScriptedRunner([GOOD_DRAFT])
    with pytest.raises(design.DesignFailed, match="design.md"):
        design.design_task(pack.task_dir, pack.domains_root, runner, pack.root / "runs")
    assert runner.calls == 0


def test_unknown_domain_fails_before_the_session(pack):
    manifest = pf.default_manifest()
    manifest["domain"] = "nope"
    (pack.task_dir / "manifest.yaml").write_text(pf.to_yaml(manifest), encoding="utf-8")
    runner = ScriptedRunner([GOOD_DRAFT])
    with pytest.raises(design.DesignFailed, match="'nope'"):
        design.design_task(pack.task_dir, pack.domains_root, runner, pack.root / "runs")
    assert runner.calls == 0


def test_writing_outside_harness_and_code_fails_and_keeps_the_files(pack):
    def move(cwd: Path) -> None:
        for rel, text in GOOD_DRAFT.items():
            (cwd / rel).parent.mkdir(parents=True, exist_ok=True)
            (cwd / rel).write_text(text, encoding="utf-8")
        (cwd / "manifest.yaml").write_text("id: toy\n", encoding="utf-8")

    with pytest.raises(design.DesignFailed, match="manifest.yaml"):
        run_design(pack, move)
    assert (pack.task_dir / "manifest.yaml").read_text(encoding="utf-8") == "id: toy\n"
    assert not (pack.task_dir / "harness" / "SHA256SUMS").exists()  # 越界就不封


def test_dead_session_fails(pack):
    with pytest.raises(design.DesignFailed, match="退出码 -9"):
        run_design(pack, GOOD_DRAFT, die_at=(1,))


def test_session_that_writes_nothing_fails(pack):
    with pytest.raises(design.DesignFailed, match="什么都没写"):
        run_design(pack, {}, reports=["我觉得不需要改"])


def test_bare_python_in_launcher_is_caught_by_validate(pack):
    draft = {**GOOD_DRAFT, "harness/launcher.sh": pf.BARE_PYTHON_LAUNCHER_SH}
    _, outcome = run_design(pack, draft)
    assert outcome.lint_problems == []
    assert any("裸调 python" in p for p in outcome.validate_problems)
    assert outcome.sealed  # 草稿照样封起来留着，问题清单让协调层决定喂回还是找人


def test_lint_problems_come_back_as_a_list(pack):
    draft = {**GOOD_DRAFT, "harness/evaluate.py": "import os\n" + pf.EVALUATE_PY}
    _, outcome = run_design(pack, draft)
    assert any(p.startswith("harness/evaluate.py:1:") and "F401" in p
               for p in outcome.lint_problems)
    assert outcome.validate_problems == []


def test_second_session_sees_current_files_and_feedback(pack):
    run_design(pack, GOOD_DRAFT)
    fixed = {"harness/evaluate.py": pf.EVALUATE_PY.replace("SystemExit(2)", "SystemExit(3)")}
    runner, outcome = run_design(pack, fixed, feedback="缺文件退 3 不退 2")
    assert outcome.session == 2
    assert outcome.log_dir.name == "session-2"
    prompt = runner.prompts[0]
    assert "照它们改，别重写结构" in prompt and "### harness/launcher.sh" in prompt
    assert pf.LAUNCHER_SH.strip() in prompt and "SHA256SUMS" not in prompt.split("## 现状")[1]
    assert "## 这次要改什么\n\n缺文件退 3 不退 2" in prompt
    assert outcome.changed_files == ["harness/evaluate.py"] and outcome.problems == []
    # 重新封：校验和跟着新文件走
    assert (pack.task_dir / "harness" / "evaluate.py").read_text(encoding="utf-8") == fixed[
        "harness/evaluate.py"]
    assert design.packs.validate_task(pack.task_dir, pack.domains_root, require_run0=False) == []


def test_ruff_missing_is_an_error_not_a_pass(pack, monkeypatch):
    def fake_run(*args, **kwargs):
        return subprocess.CompletedProcess(args, 1, stdout="", stderr="No module named ruff")

    monkeypatch.setattr(design.subprocess, "run", fake_run)
    with pytest.raises(design.DesignFailed, match="ruff"):
        run_design(pack, GOOD_DRAFT)
