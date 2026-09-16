"""framework/contracts/packs.py 的测试：一个合法夹具 + 逐条破坏。

夹具全部长在 tmp_path 上，删掉仓里的 tasks/ 与 domains/ 这些用例照过（P-5）。
每条用例断言问题清单里带得出定位关键词——问题清单读不出"哪个文件的哪个字段"就等于没报。
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from framework.contracts import env, packs
from tests.fixtures import packs_factory as pf

REPO_ROOT = Path(__file__).resolve().parent.parent


def problems_of(pack: pf.Pack) -> str:
    return "\n".join(packs.validate_task(pack.task_dir, pack.domains_root))


# --------------------------------------------------------------------------
# 基线：合法包必须一条问题都没有，否则下面所有"破坏"用例都没有意义
# --------------------------------------------------------------------------
def test_minimal_pack_is_valid(tmp_path):
    pack = pf.make_pack(tmp_path)
    assert packs.validate_task(pack.task_dir, pack.domains_root) == []


def test_domain_defaults_to_generic_when_absent(tmp_path):
    manifest = pf.default_manifest()
    del manifest["domain"]
    pack = pf.make_pack(tmp_path, manifest=manifest)
    assert packs.validate_task(pack.task_dir, pack.domains_root) == []


# --------------------------------------------------------------------------
# 发现
# --------------------------------------------------------------------------
def test_discover_tasks_accepts_repo_root_and_tasks_root(tmp_path):
    pack = pf.make_pack(tmp_path)
    assert packs.discover_tasks(pack.root) == {"toy": pack.task_dir}
    assert packs.discover_tasks(pack.tasks_root) == {"toy": pack.task_dir}


def test_discover_tasks_raises_on_duplicate_id(tmp_path):
    pack = pf.make_pack(tmp_path)
    pf.make_pack(tmp_path, task_id="toy", dir_name="toy-copy")
    with pytest.raises(ValueError, match="id 重复"):
        packs.discover_tasks(pack.root)


def test_discover_tasks_raises_on_dir_name_mismatch(tmp_path):
    pack = pf.make_pack(tmp_path, task_id="other", dir_name="toy")
    with pytest.raises(ValueError, match="目录名"):
        packs.discover_tasks(pack.root)


def test_discover_tasks_raises_on_broken_yaml(tmp_path):
    pack = pf.make_pack(tmp_path, manifest_text="id: [unclosed\n")
    with pytest.raises(ValueError, match="YAML"):
        packs.discover_tasks(pack.root)


# --------------------------------------------------------------------------
# manifest
# --------------------------------------------------------------------------
def test_id_must_equal_dir_name(tmp_path):
    pack = pf.make_pack(tmp_path, task_id="not-toy", dir_name="toy")
    report = problems_of(pack)
    assert "manifest.yaml" in report
    assert "字段 id" in report
    assert "'toy'" in report and "'not-toy'" in report


def test_missing_primary_metric(tmp_path):
    manifest = pf.default_manifest()
    del manifest["metrics"][0]["primary"]
    report = problems_of(pf.make_pack(tmp_path, manifest=manifest))
    assert "字段 metrics" in report and "primary" in report and "实际 0 个" in report


def test_two_primary_metrics(tmp_path):
    manifest = pf.default_manifest()
    manifest["metrics"].append({"name": "runtime_s", "direction": "minimize", "primary": True})
    report = problems_of(pf.make_pack(tmp_path, manifest=manifest))
    assert "字段 metrics" in report and "primary" in report and "实际 2 个" in report


def test_bad_direction(tmp_path):
    manifest = pf.default_manifest()
    manifest["metrics"][0]["direction"] = "lower_is_better"
    report = problems_of(pf.make_pack(tmp_path, manifest=manifest))
    assert "metrics/0/direction" in report


def test_unknown_manifest_field_is_rejected(tmp_path):
    """P-8 反过来用：没有读取点的字段（本轮的 conditions）不进 schema，写了就判不合法。"""
    manifest = pf.default_manifest()
    manifest["conditions"] = [{"name": "uniform"}]
    report = problems_of(pf.make_pack(tmp_path, manifest=manifest))
    assert "conditions" in report


def test_format_version_is_required(tmp_path):
    manifest = pf.default_manifest()
    del manifest["format_version"]
    report = problems_of(pf.make_pack(tmp_path, manifest=manifest))
    assert "format_version" in report and "required" in report


def test_unsupported_format_version_is_rejected_with_the_supported_list(tmp_path):
    manifest = pf.default_manifest()
    manifest["format_version"] = 2
    report = problems_of(pf.make_pack(tmp_path, manifest=manifest))
    assert "字段 format_version" in report and "(1,)" in report and "实际 2" in report


def test_source_is_optional_free_text(tmp_path):
    manifest = pf.default_manifest()
    manifest["source"] = "docs/cases/boehm-stat5-petab"
    assert packs.validate_task(*_dirs(pf.make_pack(tmp_path, manifest=manifest))) == []


def _dirs(pack: pf.Pack) -> tuple[Path, Path]:
    return pack.task_dir, pack.domains_root


# --------------------------------------------------------------------------
# env/ 与 launcher：任务必须跑在自己的环境里
# --------------------------------------------------------------------------
def test_missing_env_dir_is_a_problem(tmp_path):
    pack = pf.make_pack(tmp_path)
    shutil.rmtree(pack.task_dir / "env")
    report = problems_of(pack)
    assert "env/" in report and "目录缺失" in report


def test_launcher_calling_bare_python_is_rejected_with_line_numbers(tmp_path):
    pack = pf.make_pack(tmp_path)
    (pack.task_dir / "harness" / "launcher.sh").write_text(pf.BARE_PYTHON_LAUNCHER_SH, "utf-8")
    pf.refresh_sums(pack.task_dir)
    report = problems_of(pack)
    assert "harness/launcher.sh:6" in report and "harness/launcher.sh:7" in report
    assert "裸调 python" in report and "$AI4SCI_PYTHON" in report


@pytest.mark.parametrize("line", [
    '"$AI4SCI_PYTHON" code/train.py',
    "$AI4SCI_PYTHON -m foo",
    "# python3 code/train.py   注释不算",
    "echo python3-is-just-a-word",
    "./bin/python3 x.py",
])
def test_bare_python_check_ignores_these(line, tmp_path):
    pack = pf.make_pack(tmp_path)
    script = pack.task_dir / "harness" / "make_run0.sh"
    script.write_text(f"#!/usr/bin/env bash\n{line}\n", encoding="utf-8")
    assert not [p for p in packs.validate_task(*_dirs(pack)) if "裸调" in p]


@pytest.mark.parametrize("line", ["python3 x.py", "python x.py", "python3.14 -c pass",
                                  "cd harness && python3 x.py", "$(python3 -c 'print(1)')"])
def test_bare_python_check_catches_these(line, tmp_path):
    pack = pf.make_pack(tmp_path)
    script = pack.task_dir / "harness" / "make_run0.sh"
    script.write_text(f"#!/usr/bin/env bash\n{line}\n", encoding="utf-8")
    assert [p for p in packs.validate_task(*_dirs(pack)) if "make_run0.sh:2" in p and "裸调" in p]


def test_broken_yaml_becomes_a_problem_not_a_traceback(tmp_path):
    pack = pf.make_pack(tmp_path, manifest_text="id: toy\nmetrics: [\n")
    report = problems_of(pack)
    assert "manifest.yaml" in report and "YAML 语法错误" in report


def test_missing_manifest(tmp_path):
    pack = pf.make_pack(tmp_path)
    (pack.task_dir / "manifest.yaml").unlink()
    assert "manifest.yaml" in problems_of(pack)


# --------------------------------------------------------------------------
# 领域包
# --------------------------------------------------------------------------
def test_domain_must_exist(tmp_path):
    manifest = pf.default_manifest()
    manifest["domain"] = "mechanics"
    report = problems_of(pf.make_pack(tmp_path, manifest=manifest))
    assert "字段 domain" in report and "mechanics" in report and "profile.yaml" in report


# --------------------------------------------------------------------------
# harness
# --------------------------------------------------------------------------
def test_sha256sums_mismatch(tmp_path):
    pack = pf.make_pack(tmp_path)
    # 改 evaluate.py 而不重算 SHA256SUMS：这正是"评测被动过"的样子
    evaluate = pack.task_dir / "harness" / "evaluate.py"
    evaluate.write_text(evaluate.read_text(encoding="utf-8") + "\n# 偷改一行\n", encoding="utf-8")
    report = problems_of(pack)
    assert "harness/evaluate.py" in report and "sha256 不一致" in report


def test_missing_harness_file(tmp_path):
    pack = pf.make_pack(tmp_path)
    (pack.task_dir / "harness" / "launcher.sh").unlink()
    report = problems_of(pack)
    assert "harness/launcher.sh" in report and "文件缺失" in report


def test_unlisted_harness_file(tmp_path):
    pack = pf.make_pack(tmp_path)
    sums = pack.task_dir / "harness" / "SHA256SUMS"
    kept = [ln for ln in sums.read_text(encoding="utf-8").splitlines() if "launcher.sh" not in ln]
    sums.write_text("\n".join(kept) + "\n", encoding="utf-8")
    assert "未登记 launcher.sh" in problems_of(pack)


# --------------------------------------------------------------------------
# code/
# --------------------------------------------------------------------------
def test_empty_code_dir(tmp_path):
    pack = pf.make_pack(tmp_path)
    (pack.task_dir / "code" / "train.py").unlink()
    assert "code/" in problems_of(pack) and "为空" in problems_of(pack)


# --------------------------------------------------------------------------
# run_0
# --------------------------------------------------------------------------
def test_missing_repeats(tmp_path):
    pack = pf.make_pack(tmp_path)
    for path in (pack.task_dir / "run_0" / "repeats").glob("*.json"):
        path.unlink()
    report = problems_of(pack)
    assert "run_0/repeats/" in report and "repeat_k=3" in report and "实际 0 个" in report


def test_repeats_count_must_equal_repeat_k(tmp_path):
    pack = pf.make_pack(tmp_path, seeds=(42, 43), values=(0.5, 0.52))
    assert "repeat_k=3" in problems_of(pack)


def test_sigma_seeds_do_not_match_repeats(tmp_path):
    pack = pf.make_pack(tmp_path)
    sigma_path = pack.task_dir / "run_0" / "sigma.json"
    doc = json.loads(sigma_path.read_text(encoding="utf-8"))
    doc["val_mse"]["seeds"] = [1, 2, 3]
    sigma_path.write_text(json.dumps(doc), encoding="utf-8")
    report = problems_of(pack)
    assert "sigma.json" in report and "seeds" in report and "[42, 43, 44]" in report


def test_negative_sigma(tmp_path):
    pack = pf.make_pack(tmp_path)
    sigma_path = pack.task_dir / "run_0" / "sigma.json"
    doc = json.loads(sigma_path.read_text(encoding="utf-8"))
    doc["val_mse"]["sigma"] = -1.0
    sigma_path.write_text(json.dumps(doc), encoding="utf-8")
    assert "val_mse/sigma" in problems_of(pack)


def test_seed_in_file_must_match_file_name(tmp_path):
    pack = pf.make_pack(tmp_path)
    path = pack.task_dir / "run_0" / "repeats" / "results-43.json"
    doc = json.loads(path.read_text(encoding="utf-8"))
    doc["seed"] = 99
    path.write_text(json.dumps(doc), encoding="utf-8")
    report = problems_of(pack)
    assert "results-43.json" in report and "字段 seed" in report


def test_elapsed_over_budget(tmp_path):
    # wall_clock_s=10，1.5 倍是 15；16 秒必须被拦下
    pack = pf.make_pack(tmp_path, elapsed_s=16.0)
    report = problems_of(pack)
    assert "elapsed_s" in report and "超预算" in report and "15" in report


def test_results_missing_declared_metric(tmp_path):
    pack = pf.make_pack(tmp_path)
    path = pack.task_dir / "run_0" / "results.json"
    doc = json.loads(path.read_text(encoding="utf-8"))
    doc["metrics"] = {"other": 1.0}
    path.write_text(json.dumps(doc), encoding="utf-8")
    report = problems_of(pack)
    assert "run_0/results.json" in report and "val_mse" in report


def test_nan_metric_is_rejected(tmp_path):
    pack = pf.make_pack(tmp_path)
    path = pack.task_dir / "run_0" / "results.json"
    # 手写 NaN：Python 的 json 默认会把它读成 float('nan')，校验层必须拒
    path.write_text(
        '{"metrics": {"val_mse": NaN}, "elapsed_s": 1.0, "seed": 42, "status": "ok"}',
        encoding="utf-8",
    )
    report = problems_of(pack)
    assert "run_0/results.json" in report and "NaN" in report


def test_missing_run0(tmp_path):
    pack = pf.make_pack(tmp_path)
    shutil.rmtree(pack.task_dir / "run_0")
    assert "run_0/" in problems_of(pack)


def test_missing_task_dir(tmp_path):
    assert packs.validate_task(tmp_path / "nope", tmp_path / "domains") == [
        f"{tmp_path / 'nope'}: 任务目录不存在"
    ]


# --------------------------------------------------------------------------
# 假成功：只 print 一行分数的"训练"必须拿不到 results.json
# --------------------------------------------------------------------------
def test_fake_success_is_caught_by_harness(tmp_path):
    pack = pf.make_pack(tmp_path)
    (pack.task_dir / "code" / "train.py").write_text(pf.FAKE_SUCCESS_TRAIN_PY, encoding="utf-8")
    proc = subprocess.run(
        ["bash", str(pack.task_dir / "harness" / "launcher.sh")],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
        env={**os.environ, env.PYTHON_ENV: sys.executable},  # 直接起 launcher 时解释器由调用方给
    )
    assert proc.returncode != 0, proc.stdout
    assert not (pack.task_dir / "results.json").exists()
    assert "val_mse 0.0001" in proc.stdout  # 它确实"报了分"，只是没人认


# --------------------------------------------------------------------------
# 仓里的真实任务包：在就校验，不在就跳过（P-5：删掉 tasks/ 测试照过）
# --------------------------------------------------------------------------
def test_real_task_pack_if_present():
    task_dir = REPO_ROOT / "tasks" / "mlp-regression"
    if not task_dir.is_dir():
        pytest.skip("仓里没有 tasks/mlp-regression，框架测试不依赖它")
    assert packs.validate_task(task_dir, REPO_ROOT / "domains") == []


def test_real_task_pack_runs_end_to_end_if_present(tmp_path):
    """真跑一遍真实任务包。

    先整包拷到 tmp_path 再跑：产物（predictions.json / results.json / timing.json）不许
    落在仓里，否则跑一次测试就脏一次工作区。
    """
    source = REPO_ROOT / "tasks" / "mlp-regression"
    if not source.is_dir():
        pytest.skip("仓里没有 tasks/mlp-regression，框架测试不依赖它")
    task_dir = tmp_path / "mlp-regression"
    shutil.copytree(source, task_dir, ignore=shutil.ignore_patterns(env.VENV_DIRNAME))
    # 任务自带环境：按它的 env/ 建一个 venv，launcher 只经 $AI4SCI_PYTHON 起解释器
    python = env.build_venv(task_dir, task_dir / env.VENV_DIRNAME)
    clean = {k: v for k, v in os.environ.items() if not k.startswith("AI4SCI_")}
    proc = subprocess.run(
        ["bash", str(task_dir / "harness" / "launcher.sh")],
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
        env={**clean, "AI4SCI_SEED": "42", env.PYTHON_ENV: str(python)},
    )
    assert proc.returncode == 0, proc.stderr
    doc = json.loads((task_dir / "results.json").read_text(encoding="utf-8"))
    assert doc["seed"] == 42
    assert doc["metrics"]["val_mse"] > 0
    assert doc["elapsed_s"] <= 30 * 1.5  # manifest 的 wall_clock_s × 1.5


# ── seal_harness 与设计阶段的 validate ─────────────────────────────────────
def test_seal_harness_sets_exec_bits_and_lists_every_file(tmp_path):
    pack = pf.make_pack(tmp_path)
    hdir = pack.task_dir / "harness"
    (hdir / "make_run0.sh").write_text("#!/usr/bin/env bash\n", encoding="utf-8")
    (hdir / "launcher.sh").chmod(0o644)
    names = packs.seal_harness(pack.task_dir)
    assert names == ["evaluate.py", "launcher.sh", "make_run0.sh"]
    assert os.access(hdir / "launcher.sh", os.X_OK) and os.access(hdir / "make_run0.sh", os.X_OK)
    assert not os.access(hdir / "evaluate.py", os.X_OK)  # 只给脚本加执行位
    listed = [ln.split("  ")[1] for ln in (hdir / "SHA256SUMS").read_text().splitlines()]
    assert listed == names
    assert packs.validate_task(pack.task_dir, pack.domains_root) == []


def test_seal_harness_without_harness_dir_returns_nothing(tmp_path):
    (tmp_path / "toy").mkdir()
    assert packs.seal_harness(tmp_path / "toy") == []
    assert not (tmp_path / "toy" / "harness").exists()


def test_validate_can_skip_run0_for_the_design_stage(tmp_path):
    pack = pf.make_pack(tmp_path)
    shutil.rmtree(pack.task_dir / "run_0")
    assert packs.validate_task(pack.task_dir, pack.domains_root, require_run0=False) == []
    full = packs.validate_task(pack.task_dir, pack.domains_root)
    assert full and all("run_0/" in p for p in full)
