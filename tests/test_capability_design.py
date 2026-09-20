"""设计能力：零模型的部分（准备 data/ 与 env/、组提示、判越界、补 domain、封 harness、ruff、
validate）用剧本执行层测全。

执行层写什么由剧本决定，所以能一条条摆出来：合约的草稿、越界、会话死掉、什么都没写、
裸 python、lint 不过、第二版带现状与反馈。评分脚本对不对不在这里测——那是人在断点上签字的事。
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
import yaml

from compute.local import LocalCompute
from framework import paths
from framework.capabilities import design as design_cap
from framework.capabilities.design import drafting as design
from framework.contracts.capability import CapabilityFailed, Inputs, Ports
from framework.experiment import pack as packs
from framework.workspace import outputs
from tests.fixtures import packs_factory as pf
from tests.fixtures.scripted_backend import ScriptedRunner

SKILL_MD = ("---\nname: toy\ndescription: 夹具 skill\n---\n\n"
            "用 json 模块读写，别 import 第三方库。\n")
# 夹具的 make_run0.sh：基线一次 + 三个 seed + σ，纯标准库；与真任务的骨架同形
MAKE_RUN0_SH = """#!/usr/bin/env bash
set -euo pipefail
TASK_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$TASK_DIR"
export AI4SCI_PYTHON="${AI4SCI_PYTHON:-$TASK_DIR/.venv/bin/python}"
rm -rf baseline
mkdir -p baseline/repeats
AI4SCI_SEED=42 harness/launcher.sh
cp results.json baseline/results.json
for seed in 42 43 44; do
  AI4SCI_SEED="$seed" harness/launcher.sh
  "$AI4SCI_PYTHON" - "$seed" <<'PY'
import json, sys
from pathlib import Path
doc = json.loads(Path("results.json").read_text())
doc["seed"] = int(sys.argv[1])
doc["metrics"]["val_mse"] += 0.001 * (doc["seed"] - 42)
Path(f"baseline/repeats/results-{doc['seed']}.json").write_text(json.dumps(doc))
PY
done
"$AI4SCI_PYTHON" - <<'PY'
import json, statistics
from pathlib import Path
docs = [json.loads(p.read_text()) for p in sorted(Path("baseline/repeats").glob("results-*.json"))]
values = [d["metrics"]["val_mse"] for d in docs]
Path("baseline/sigma.json").write_text(json.dumps({"val_mse": {"sigma": statistics.stdev(values),
    "seeds": [d["seed"] for d in docs], "values": values}}))
PY
rm -f predictions.json results.json
"""
GOOD_DRAFT = {
    "scoring.yaml": pf.to_yaml({k: v for k, v in pf.default_scoring().items() if k != "domain"}),
    "harness/launcher.sh": pf.LAUNCHER_SH,
    "harness/evaluate.py": pf.EVALUATE_PY,
    "harness/make_run0.sh": MAKE_RUN0_SH,
    "code/train.py": pf.TRAIN_PY,
}


@pytest.fixture
def ws(tmp_path):
    """需求确认过、原件里有 env/ 与一份数据、领域包带一个 skill 的工作区。"""
    workspace = pf.make_workspace(tmp_path, "toy")
    (workspace.materials / "val.json").write_text('{"y": [1.0]}', encoding="utf-8")
    domains = tmp_path / "domains"
    skill = domains / "generic" / "skills" / "toy" / "SKILL.md"
    skill.parent.mkdir(parents=True)
    (domains / "generic" / "profile.yaml").write_text("id: generic\n", encoding="utf-8")
    skill.write_text(SKILL_MD, encoding="utf-8")
    return workspace, domains


def new_pack(workspace) -> Path:
    directory, _ = outputs.open_output(workspace, "design", title="t", by="design", inputs=[],
                                       params={}, flow=None, step=None, requirement=1,
                                       chat_id=None)
    design_cap._prepare(directory, workspace.root)
    return directory


def run_design(ws, pack: Path, *moves, feedback: str = "", hypothesis: str = "",
               reports: list[str] | None = None, **runner_kwargs):
    workspace, domains = ws
    runner = ScriptedRunner(list(moves), **runner_kwargs)
    runner.reports = list(reports or [])
    outcome = design.draft(pack, workspace.requirement.read_text(encoding="utf-8"), hypothesis,
                           "generic", domains, runner, feedback=feedback)
    return runner, outcome


def test_prepare_copies_materials_into_data_and_env_and_refuses_without_env(ws):
    workspace, _ = ws
    pack = new_pack(workspace)
    assert (pack / "data" / "val.json").is_file() and not (pack / "data" / "env").exists()
    assert (pack / "env" / "python-version").is_file()
    design_cap._prepare(pack, workspace.root)  # 第二次不动
    (workspace.materials / "env" / "python-version").unlink()
    bare, _ = outputs.open_output(workspace, "design", title="t", by="design", inputs=[],
                                  params={}, flow=None, step=None, requirement=1, chat_id=None)
    with pytest.raises(CapabilityFailed, match="materials/env/"):
        design_cap._prepare(bare, workspace.root)


def test_good_draft_is_sealed_lint_clean_validates_and_gets_the_domain(ws):
    workspace, domains = ws
    pack = new_pack(workspace)
    runner, outcome = run_design(ws, pack, GOOD_DRAFT)
    assert outcome.session == 1 and outcome.problems == []
    assert outcome.sealed == ["evaluate.py", "launcher.sh", "make_run0.sh"]
    assert outcome.changed_files == sorted(GOOD_DRAFT)
    hdir = pack / "harness"
    for name in ("launcher.sh", "make_run0.sh"):
        assert (hdir / name).stat().st_mode & 0o111, f"{name} 没有执行位"
    listed = [ln.split("  ")[1] for ln in (hdir / "SHA256SUMS").read_text().splitlines()]
    assert listed == outcome.sealed
    # domain 是框架定的，写进 scoring.yaml；执行层没写它
    scoring = yaml.safe_load((pack / "scoring.yaml").read_text(encoding="utf-8"))
    assert scoring["domain"] == "generic"
    # 证据都在：提示原文、事件流搬到了会话目录，产出目录里不留 .ai4sci
    assert outcome.log_dir == pack / "executor" / "session-1"
    assert (outcome.log_dir / "prompt.md").read_text(encoding="utf-8") == runner.prompts[0]
    assert list(outcome.log_dir.glob("executor-*.jsonl"))
    assert not (pack / ".ai4sci").exists()


def test_prompt_carries_requirement_hypothesis_skills_rules_and_escaped_dollars(ws, monkeypatch,
                                                                                 tmp_path):
    """领域 skill 只以清单进提示（名字 + 一句话），正文由执行层 `ai4sci skill show` 按需读（P-22）；
    执行层的 Bash 白名单只有 `ai4sci skill *`。"""
    monkeypatch.setenv(paths.SKILLS_ROOT_ENV, str(tmp_path / "no-generic-skills"))
    (tmp_path / "no-generic-skills").mkdir()
    pack = new_pack(ws[0])
    runner, _ = run_design(ws, pack, GOOD_DRAFT, hypothesis="### hypothesis.md\n\n加一层会更好")
    prompt = runner.prompts[0]
    for token in ("在固定预算下把 val_mse 压到最低", "## 假设", "加一层会更好", "## 工具包",
                  "<skill><name>toy</name><description>夹具 skill</description></skill>",
                  "ai4sci skill show", "## 联网", "自带的联网搜索",
                  design.LINT_SELECT, str(design.LINT_LINE_LENGTH),
                  "从零写", '"$AI4SCI_PYTHON"', "${AI4SCI_PYTHON:?", "scoring.yaml"):
        assert token in prompt, token
    assert "别 import 第三方库" not in prompt, "skill 正文不进提示，执行层按需 show"
    assert "这次要改什么" not in prompt
    assert runner.bash_rules == ("Bash(ai4sci skill *)",)


def test_unknown_domain_fails_before_the_session(ws):
    workspace, domains = ws
    pack = new_pack(workspace)
    runner = ScriptedRunner([GOOD_DRAFT])
    with pytest.raises(design.DesignFailed, match="'nope'"):
        design.draft(pack, "需求", "", "nope", domains, runner)
    assert runner.calls == 0


def test_writing_outside_the_allowed_files_fails_and_keeps_the_files(ws):
    pack = new_pack(ws[0])

    def move(cwd: Path) -> None:
        for rel, text in GOOD_DRAFT.items():
            (cwd / rel).parent.mkdir(parents=True, exist_ok=True)
            (cwd / rel).write_text(text, encoding="utf-8")
        (cwd / "data" / "val.json").write_text("{}", encoding="utf-8")

    with pytest.raises(design.DesignFailed, match="data/val.json"):
        run_design(ws, pack, move)
    assert (pack / "data" / "val.json").read_text(encoding="utf-8") == "{}"
    assert not (pack / "harness" / "SHA256SUMS").exists()  # 越界就不封


def test_dead_session_fails(ws):
    with pytest.raises(design.DesignFailed, match="退出码 -9"):
        run_design(ws, new_pack(ws[0]), GOOD_DRAFT, die_at=(1,))


def test_session_that_writes_nothing_fails(ws):
    with pytest.raises(design.DesignFailed, match="什么都没写"):
        run_design(ws, new_pack(ws[0]), {}, reports=["我觉得不需要改"])


def test_bare_python_in_launcher_is_caught_by_validate(ws):
    draft = {**GOOD_DRAFT, "harness/launcher.sh": pf.BARE_PYTHON_LAUNCHER_SH}
    _, outcome = run_design(ws, new_pack(ws[0]), draft)
    assert outcome.lint_problems == []
    assert any("裸调 python" in p for p in outcome.validate_problems)
    assert outcome.sealed  # 草稿照样封起来留着，问题清单让协调层决定喂回还是找人


def test_missing_scoring_is_a_validate_problem(ws):
    draft = {k: v for k, v in GOOD_DRAFT.items() if k != "scoring.yaml"}
    _, outcome = run_design(ws, new_pack(ws[0]), draft)
    assert any("scoring.yaml" in p and "缺失" in p for p in outcome.validate_problems)


def test_lint_problems_come_back_as_a_list(ws):
    draft = {**GOOD_DRAFT, "harness/evaluate.py": "import os\n" + pf.EVALUATE_PY}
    _, outcome = run_design(ws, new_pack(ws[0]), draft)
    assert any(p.startswith("harness/evaluate.py:1:") and "F401" in p
               for p in outcome.lint_problems)
    assert outcome.validate_problems == []


def test_import_order_is_fixed_before_sealing_not_reported(ws):
    """外层 #116：I001 这种 ruff 能安全修的纯格式问题，框架自己修完再封，不让执行层重来一轮；
    别的规则（没用的 import）照旧报。SHA256SUMS 记的是修完的文件。"""
    workspace, domains = ws
    pack = new_pack(workspace)
    unsorted = pf.EVALUATE_PY.replace("import json\nimport sys\n", "import sys\nimport json\n")
    _, outcome = run_design(ws, pack, {**GOOD_DRAFT, "harness/evaluate.py": unsorted})
    assert outcome.problems == [], outcome.problems
    text = (pack / "harness" / "evaluate.py").read_text(encoding="utf-8")
    assert "import json\nimport sys\n" in text
    assert packs.validate_pack(pack, domains, require_baseline=False) == []  # 校验和是修完的
    draft = {**GOOD_DRAFT, "harness/evaluate.py": "import sys\nimport os\n" + pf.EVALUATE_PY}
    _, outcome = run_design(ws, new_pack(workspace), draft)
    assert [p for p in outcome.lint_problems if "I001" in p] == []
    assert any("F401" in p for p in outcome.lint_problems)


def test_second_session_sees_current_files_and_feedback(ws):
    workspace, domains = ws
    pack = new_pack(workspace)
    run_design(ws, pack, GOOD_DRAFT)
    fixed = {"harness/evaluate.py": pf.EVALUATE_PY.replace("SystemExit(2)", "SystemExit(3)")}
    runner, outcome = run_design(ws, pack, fixed, feedback="缺文件退 3 不退 2")
    assert outcome.session == 2
    assert outcome.log_dir.name == "session-2"
    prompt = runner.prompts[0]
    assert "照它们改，别重写结构" in prompt and "### harness/launcher.sh" in prompt
    assert "### scoring.yaml" in prompt
    assert pf.LAUNCHER_SH.strip() in prompt and "SHA256SUMS" not in prompt.split("## 现状")[1]
    assert "## 这次要改什么\n\n缺文件退 3 不退 2" in prompt
    assert outcome.changed_files == ["harness/evaluate.py"] and outcome.problems == []
    # 重新封：校验和跟着新文件走
    assert (pack / "harness" / "evaluate.py").read_text(encoding="utf-8") == fixed[
        "harness/evaluate.py"]
    assert packs.validate_pack(pack, domains, require_baseline=False) == []


def test_ruff_missing_is_an_error_not_a_pass(ws, monkeypatch):
    def fake_run(*args, **kwargs):
        return subprocess.CompletedProcess(args, 1, stdout="", stderr="No module named ruff")

    monkeypatch.setattr(design.subprocess, "run", fake_run)
    with pytest.raises(design.DesignFailed, match="ruff"):
        run_design(ws, new_pack(ws[0]), GOOD_DRAFT)


def test_capability_entry_runs_draft_then_baseline_and_reads_hypothesis(ws, monkeypatch):
    """整颗能力：准备 → 草稿 → 基线 → 结论行；假设产出的正文进提示。草稿有问题就停在前半段，
    说清怎么喂回。"""
    workspace, domains = ws
    monkeypatch.setattr(design_cap.paths, "domains_root", lambda: domains)
    hyp, meta = outputs.open_output(workspace, "hypothesis", title="假设", by="assistant",
                                    inputs=[], params={}, flow=None, step=None, requirement=1,
                                    chat_id=None)
    (hyp / "hypothesis.md").write_text("先加一层。", encoding="utf-8")
    outputs.close_output(hyp, meta, ok=True, line="手写")
    pack, _ = outputs.open_output(workspace, "design", title="t", by="design",
                                  inputs=["hypothesis/1"], params={}, flow=None, step=None,
                                  requirement=1, chat_id=None)
    inputs = Inputs(workspace.root, (hyp,), ("hypothesis/1",))
    runner = ScriptedRunner([{**GOOD_DRAFT, "harness/launcher.sh": pf.BARE_PYTHON_LAUNCHER_SH}])
    with pytest.raises(CapabilityFailed, match="--continue design/1 --feedback"):
        design_cap.run(pack, inputs, Ports(runner=runner, compute=LocalCompute()))
    assert "先加一层。" in runner.prompts[0]
    # 喂回第二版：修好 launcher，跑基线出 baseline/
    runner = ScriptedRunner([{"harness/launcher.sh": pf.LAUNCHER_SH}])
    ports = Ports(runner=runner, compute=LocalCompute())
    line = design_cap.run(pack, inputs, ports, feedback="别裸调 python")
    assert line.startswith("design ok\t") and "auto-research --from design/1" in line
    assert (pack / "baseline" / "sigma.json").is_file()


def test_continue_refuses_when_materials_env_changed(ws, monkeypatch):
    """外层 #117：研究者（或助理）改了 materials/env/ 之后 `--continue` 不能悄悄接着用旧环境：
    明说「环境变了，重开一次」，不让执行层空跑一轮。"""
    workspace, domains = ws
    monkeypatch.setattr(design_cap.paths, "domains_root", lambda: domains)
    pack = new_pack(workspace)
    run_design(ws, pack, GOOD_DRAFT)
    pf.write_env(workspace.materials, requirements="numpy==2.3.1\n")  # 事后补了依赖
    runner = ScriptedRunner([{"harness/evaluate.py": pf.EVALUATE_PY}])
    inputs = Inputs(workspace.root, (), ())
    with pytest.raises(CapabilityFailed, match="requirements.lock.*重开一次设计"):
        design_cap.run(pack, inputs, Ports(runner=runner, compute=LocalCompute()),
                       feedback="改一版")
    assert runner.calls == 0


def test_continue_without_feedback_reruns_only_the_baseline(ws, monkeypatch):
    """外层 #118：环境没装成 / 机器换了 / 被叫停之后，接着干、不给修改意见 = 草稿不动、只重跑基线；
    不起执行层（第一轮真任务里执行层为此空跑了一轮、被判「没产出」）。"""
    workspace, domains = ws
    monkeypatch.setattr(design_cap.paths, "domains_root", lambda: domains)
    pack = new_pack(workspace)
    inputs = Inputs(workspace.root, (), ())
    first = ScriptedRunner([{**GOOD_DRAFT, "harness/launcher.sh": pf.LAUNCHER_SH}])
    line = design_cap.run(pack, inputs, Ports(runner=first, compute=LocalCompute()))
    assert line.startswith("design ok\t") and (pack / "baseline" / "sigma.json").is_file()
    import shutil
    shutil.rmtree(pack / "baseline")  # 像基线没跑成那样
    idle = ScriptedRunner([])
    line = design_cap.run(pack, inputs, Ports(runner=idle, compute=LocalCompute()))
    assert idle.calls == 0 and line.startswith("design ok\tsession=-\tchanged=0")
    assert (pack / "baseline" / "sigma.json").is_file() and "auto-research --from design/1" in line
