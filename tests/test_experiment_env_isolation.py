"""任务自带环境与领域包注入在 run 这一层的验收（spec A-12、纲领 packs.md §2 §3）。

- 开实验按 env/ 建 experiment/<n>/.venv，设计包里的 .venv 不被拷进 work/
- harness 经框架跑时，解释器落在这次实验自己的 .venv 下（A-12 的机器证据）
- 领域包的 prompts/experiment.md 随实验快照，进执行层提示的「领域约定」段；领域 skill 挂到流程实例上
  才装载（P-26），以清单（名字 + 一句话）进执行层提示的「工具包」段
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from compute.local import LocalCompute
from framework import paths
from framework.capabilities.auto_research import run_loop
from framework.capabilities.auto_research.open import EnvBuildError
from framework.experiment import env, layout
from framework.experiment.context import load_context, read_domain_extra
from tests.fixtures import packs_factory as pf
from tests.fixtures import spaces
from tests.fixtures.scripted_backend import ScriptedRunner
from tests.test_experiment_loop import make_loop_pack, open_run, train_for_mse

SKILL_MD = """---
name: petab
description: 夹具 skill
---
# 夹具 skill 正文

只改 code/，边界不许动。
"""


def test_open_builds_the_experiment_venv_and_leaves_the_design_venv_behind(tmp_path):
    pack = make_loop_pack(tmp_path)
    # 设计产出里先有一个 .venv（make_run0.sh 用的），它不该被拷进 work/
    env.build_venv(pack.pack, pack.pack / env.VENV_DIRNAME)
    run_dir = open_run(pack)
    assert layout.venv_python(run_dir).is_file()
    assert not (layout.work(run_dir) / env.VENV_DIRNAME).exists()
    assert Path(load_context(run_dir).python) == layout.venv_python(run_dir)


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
    """A-12：train.py 把 sys.executable 写进 predictions.json，它必须在 experiment/<n>/.venv 下。"""
    pack = make_loop_pack(tmp_path)
    run_dir = open_run(pack)
    runner = ScriptedRunner([{"code/train.py": RECORDING_TRAIN_PY}])
    run_loop(run_dir, runner, LocalCompute(), max_iters=1)
    text = (layout.iter_run(run_dir, 1) / "predictions.json").read_text(encoding="utf-8")
    preds = json.loads(text)
    assert Path(preds["python"]).resolve() == layout.venv_python(run_dir).resolve()


def test_open_clears_the_half_built_experiment_when_the_env_cannot_be_built(tmp_path):
    pack = make_loop_pack(tmp_path)
    pf.write_env(pack.pack, python_version="3.999")
    with pytest.raises(EnvBuildError):
        open_run(pack)
    run_dir = pack.workspace.root / "experiment" / "1"
    assert [p.name for p in run_dir.iterdir()] == ["meta.yaml"], "铺了一半的要清掉，只留框架的账"


def test_domain_prompt_is_snapshotted_and_skills_go_in_as_a_catalog(tmp_path, monkeypatch):
    pack = make_loop_pack(tmp_path)
    monkeypatch.setenv(paths.DOMAINS_ROOT_ENV, str(pack.domains_root))
    monkeypatch.setenv(paths.SKILLS_ROOT_ENV, str(tmp_path / "no-resident-skills"))
    (tmp_path / "no-resident-skills").mkdir()
    domain = pack.domains_root / "generic"
    (domain / "prompts").mkdir()
    (domain / "prompts" / "experiment.md").write_text("实验时只调学习率。\n", encoding="utf-8")
    skill = domain / "skills" / "experiment" / "biology" / "petab" / "SKILL.md"
    skill.parent.mkdir(parents=True)
    skill.write_text(SKILL_MD, encoding="utf-8")
    spaces.give_flow(pack.workspace, "  - 实验: [petab]\n")  # 领域 skill 挂上才装载（P-26）

    run_dir = open_run(pack)
    assert layout.domain_prompt(run_dir).is_file()
    assert not (run_dir / "prompts" / "skills").exists(), "skill 不快照：按名字进清单"
    extra = read_domain_extra(run_dir)
    assert extra == "实验时只调学习率。"

    runner = ScriptedRunner([train_for_mse(0.001)])
    run_loop(run_dir, runner, LocalCompute(), max_iters=1)
    prompt = runner.prompts[0]
    assert "## 领域约定" in prompt and "实验时只调学习率。" in prompt
    assert "<skill><name>petab</name><description>夹具 skill</description></skill>" in prompt
    assert "边界不许动" not in prompt, "skill 正文不进提示，执行层 ai4sci skill show 按需读"
    assert runner.bash_rules == ("ai4sci skill",)
    assert prompt.rstrip().endswith("一类命令。"), "提示末尾接这家 CLI 自己的「工具怎么用」"


def test_nothing_hung_and_no_domain_prompt_injects_nothing(tmp_path, monkeypatch):
    monkeypatch.setenv(paths.SKILLS_ROOT_ENV, str(tmp_path / "no-resident-skills"))
    (tmp_path / "no-resident-skills").mkdir()
    pack = make_loop_pack(tmp_path)
    run_dir = open_run(pack)
    assert read_domain_extra(run_dir) == ""
    runner = ScriptedRunner([train_for_mse(0.001)])
    run_loop(run_dir, runner, LocalCompute(), max_iters=1)
    assert "## 工具包" not in runner.prompts[0], "没有 skill 不输出空清单"
    assert "## 领域约定" not in runner.prompts[0]
