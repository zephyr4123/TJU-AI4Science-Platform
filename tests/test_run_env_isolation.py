"""任务自带环境与领域包注入在 run 这一层的验收（spec A-12、纲领 packs.md §2 §3）。

- run new 按 work/env/ 建 runs/<id>/.venv，任务目录里的 .venv 不被拷进 work/
- harness 经框架跑时，解释器落在 run 自己的 .venv 下（A-12 的机器证据）
- 领域包的 prompts/experiment.md 与 skills/*/SKILL.md 随 run 快照，进执行层提示的「领域约定」段
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from compute.local import LocalCompute
from framework.capabilities.auto_research import run_loop
from framework.contracts import env
from framework.run import layout
from framework.run.context import load_context, read_domain_extra
from framework.run.lifecycle import EnvBuildError, new_run
from tests.fixtures import packs_factory as pf
from tests.fixtures.scripted_backend import ScriptedRunner
from tests.test_experiment_loop import make_loop_pack, train_for_mse

SKILL_MD = """---
name: petab
description: 夹具 skill
---
# 夹具 skill 正文

只改 code/，边界不许动。
"""


def test_run_new_builds_the_run_venv_and_leaves_the_task_venv_behind(tmp_path):
    pack = make_loop_pack(tmp_path)
    # 任务目录里先有一个 .venv（make_run0.sh 用的），它不该被拷进 work/
    env.build_venv(pack.task_dir, pack.task_dir / env.VENV_DIRNAME)
    run_dir = new_run(pack.task_dir, tmp_path / "runs", "r1", domains_root=pack.domains_root)
    assert layout.venv_python(run_dir).is_file()
    assert not (layout.work(run_dir) / env.VENV_DIRNAME).exists()
    assert load_context(run_dir).python == layout.venv_python(run_dir)


# 执行层这一轮写的 train.py：除了预测值，把自己跑在哪个解释器里也写进产物（A-12 的证据）
RECORDING_TRAIN_PY = '''import json
import sys
from pathlib import Path

TASK_DIR = Path(__file__).resolve().parent.parent
(TASK_DIR / "predictions.json").write_text(
    json.dumps({"y_pred": [0.1], "python": sys.executable}), encoding="utf-8"
)
'''


def test_harness_runs_in_the_run_venv_not_the_platform_one(tmp_path):
    """A-12：train.py 把 sys.executable 写进 predictions.json，它必须在 runs/<id>/.venv 下。"""
    pack = make_loop_pack(tmp_path)
    run_dir = new_run(pack.task_dir, tmp_path / "runs", "r1", domains_root=pack.domains_root)
    runner = ScriptedRunner([{"code/train.py": RECORDING_TRAIN_PY}])
    run_loop(run_dir, runner, LocalCompute(), max_iters=1)
    preds = json.loads((layout.iter_run(run_dir, 1) / "predictions.json").read_text("utf-8"))
    assert Path(preds["python"]).resolve() == layout.venv_python(run_dir).resolve()


def test_run_new_removes_the_half_built_run_when_the_env_cannot_be_built(tmp_path):
    pack = make_loop_pack(tmp_path)
    pf.write_env(pack.task_dir, python_version="3.999")
    with pytest.raises(EnvBuildError):
        new_run(pack.task_dir, tmp_path / "runs", "r1", domains_root=pack.domains_root)
    assert not (tmp_path / "runs" / "r1").exists()


def test_domain_prompt_and_skills_are_snapshotted_and_injected(tmp_path):
    pack = make_loop_pack(tmp_path)
    domain = pack.domains_root / "generic"
    (domain / "prompts").mkdir()
    (domain / "prompts" / "experiment.md").write_text("实验时只调学习率。\n", encoding="utf-8")
    (domain / "skills" / "petab").mkdir(parents=True)
    (domain / "skills" / "petab" / "SKILL.md").write_text(SKILL_MD, encoding="utf-8")

    run_dir = new_run(pack.task_dir, tmp_path / "runs", "r1", domains_root=pack.domains_root)
    assert layout.domain_prompt(run_dir).is_file()
    assert (layout.domain_skills(run_dir) / "petab.md").is_file()

    extra = read_domain_extra(run_dir)
    assert "实验时只调学习率。" in extra
    assert "### skill: petab" in extra and "边界不许动" in extra
    assert "description: 夹具 skill" not in extra, "frontmatter 是给 CLI 索引的，不进 prompt"

    runner = ScriptedRunner([train_for_mse(0.001)])
    run_loop(run_dir, runner, LocalCompute(), max_iters=1)
    assert "## 领域约定" in runner.prompts[0] and "边界不许动" in runner.prompts[0]


def test_domain_without_prompt_or_skills_injects_nothing(tmp_path):
    pack = make_loop_pack(tmp_path)
    run_dir = new_run(pack.task_dir, tmp_path / "runs", "r1", domains_root=pack.domains_root)
    assert read_domain_extra(run_dir) == ""
    runner = ScriptedRunner([train_for_mse(0.001)])
    run_loop(run_dir, runner, LocalCompute(), max_iters=1)
    assert "## 领域约定" not in runner.prompts[0]
