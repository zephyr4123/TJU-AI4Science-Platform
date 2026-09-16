"""在 tmp_path 里造一个最小合法任务包，供 packs / cli 测试逐条破坏。

为什么不复用仓里的 tasks/mlp-regression：CI 门禁要求删掉全部任务包后框架测试照过
（纲领 P-5），夹具一旦指向真实包，这条门禁就成了摆设。
"""

from __future__ import annotations

import hashlib
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from framework.contracts import publish

# 夹具 harness：形状与真任务一致（清产物 → 训练 → 评分），但只有几行。
LAUNCHER_SH = """#!/usr/bin/env bash
set -euo pipefail
TASK_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$TASK_DIR"
rm -f predictions.json results.json
"$AI4SCI_PYTHON" code/train.py
"$AI4SCI_PYTHON" harness/evaluate.py
"""

# 裸调 python3 的 launcher：契约判它不合法（任务必须跑在自己的 venv 里）
BARE_PYTHON_LAUNCHER_SH = LAUNCHER_SH.replace('"$AI4SCI_PYTHON"', "python3")

EVALUATE_PY = '''"""夹具 harness：只吃 predictions.json，缺了就退非零且不写 results.json。"""
import json
import sys
from pathlib import Path

TASK_DIR = Path(__file__).resolve().parent.parent
preds = TASK_DIR / "predictions.json"
if not preds.is_file():
    print("evaluate: 文件缺失：predictions.json", file=sys.stderr)
    raise SystemExit(2)
values = json.loads(preds.read_text(encoding="utf-8"))["y_pred"]
mse = sum(v * v for v in values) / len(values)
(TASK_DIR / "results.json").write_text(
    json.dumps({"metrics": {"val_mse": mse}, "elapsed_s": 0.1, "seed": 42, "status": "ok"}),
    encoding="utf-8",
)
print(f"val_mse={mse}")
'''

TRAIN_PY = '''"""夹具基线：写出 predictions.json，不算分；顺带记下跑在哪个解释器里（A-12）。"""
import json
import sys
from pathlib import Path

TASK_DIR = Path(__file__).resolve().parent.parent
(TASK_DIR / "predictions.json").write_text(
    json.dumps({"y_pred": [0.1, 0.2], "python": sys.executable}), encoding="utf-8"
)
'''

# 夹具任务的环境：解释器版本取当前进程的，uv 就地能找到、不用下载；零依赖
PYTHON_VERSION = f"{sys.version_info[0]}.{sys.version_info[1]}"

# 只 print 一行"成绩"、什么都不产出的假成功脚本，用来验证 harness 拦得住它。
FAKE_SUCCESS_TRAIN_PY = 'print("val_mse 0.0001")\n'

# 夹具的 design.md：需求看板聊出来的"怎么算好"，发布签的就是它和 manifest
BRIEF = "code/ 写 predictions.json：{\"y_pred\": [...]}；evaluate.py 算 val_mse 写 results.json。\n"
PUBLISHED_BY = "fixture"
DEFAULT_SEEDS = (42, 43, 44)
DEFAULT_VALUES = (0.50, 0.52, 0.48)


@dataclass
class Pack:
    root: Path
    tasks_root: Path
    task_dir: Path
    domains_root: Path


def default_manifest(task_id: str = "toy") -> dict[str, Any]:
    return {
        "format_version": 1,
        "id": task_id,
        "domain": "generic",
        "title": "夹具任务",
        "question": "在固定预算下把 val_mse 压到最低",
        "metrics": [{"name": "val_mse", "direction": "minimize", "primary": True}],
        "budget": {
            "wall_clock_s": 10,
            "max_iterations": 5,
            "repeat_k": 3,
            "accept_sigma": 2.0,
        },
        "requirements": [
            {
                "id": "R1",
                "type": "numeric",
                "must_pass": True,
                "description": "主指标优于基线且过统计门",
            }
        ],
    }


def to_yaml(manifest: dict[str, Any]) -> str:
    """手写 YAML，避免夹具依赖 yaml.dump 的格式选择；坏 YAML 的用例直接传字符串。"""
    import yaml

    return yaml.safe_dump(manifest, allow_unicode=True, sort_keys=False)


def make_pack(
    tmp_path: Path,
    *,
    task_id: str = "toy",
    dir_name: str | None = None,
    manifest: dict[str, Any] | None = None,
    manifest_text: str | None = None,
    domains: tuple[str, ...] = ("generic",),
    seeds: tuple[int, ...] = DEFAULT_SEEDS,
    values: tuple[float, ...] = DEFAULT_VALUES,
    elapsed_s: float = 1.0,
    published: bool = True,
) -> Pack:
    """造一个默认合法的任务包；每个参数对应一处可被单独破坏的地方。

    默认已发布（design.md + publish.json）：夹具代表"接任务那一刻已经过了需求看板"，
    `run new` 与 task 级能力开门前查的钥匙都在。`published=False` 是没发布那条路的入口。
    """
    root = tmp_path
    tasks_root = root / "tasks"
    task_dir = tasks_root / (dir_name or task_id)
    domains_root = root / "domains"
    (task_dir / "code").mkdir(parents=True, exist_ok=True)
    (task_dir / "harness").mkdir(exist_ok=True)
    (task_dir / "run_0" / "repeats").mkdir(parents=True, exist_ok=True)

    for domain in domains:
        (domains_root / domain).mkdir(parents=True, exist_ok=True)
        (domains_root / domain / "profile.yaml").write_text(
            f"id: {domain}\ndisplay_name: {domain}\n", encoding="utf-8"
        )

    if manifest_text is None:
        manifest_text = to_yaml(manifest or default_manifest(task_id))
    text = manifest_text
    (task_dir / "manifest.yaml").write_text(text, encoding="utf-8")
    (task_dir / "design.md").write_text(BRIEF, encoding="utf-8")

    (task_dir / "code" / "train.py").write_text(TRAIN_PY, encoding="utf-8")
    write_env(task_dir)
    write_harness(task_dir)
    write_run0(task_dir, seeds=seeds, values=values, elapsed_s=elapsed_s)
    if published:
        # 直接写钥匙不过检查：夹具要能造"发布过的坏包"，坏在哪由各测试自己破坏
        publish.write_record(task_dir, by=PUBLISHED_BY)
    return Pack(root=root, tasks_root=tasks_root, task_dir=task_dir, domains_root=domains_root)


def write_env(task_dir: Path, python_version: str = PYTHON_VERSION,
              requirements: str = "") -> None:
    edir = task_dir / "env"
    edir.mkdir(exist_ok=True)
    (edir / "python-version").write_text(python_version + "\n", encoding="utf-8")
    (edir / "requirements.lock").write_text(requirements, encoding="utf-8")


def write_harness(task_dir: Path) -> None:
    hdir = task_dir / "harness"
    (hdir / "launcher.sh").write_text(LAUNCHER_SH, encoding="utf-8")
    (hdir / "evaluate.py").write_text(EVALUATE_PY, encoding="utf-8")
    refresh_sums(task_dir)


def refresh_sums(task_dir: Path) -> None:
    """按磁盘现状重写 SHA256SUMS，格式与 `shasum -a 256` 一致。"""
    hdir = task_dir / "harness"
    lines = []
    for name in ("evaluate.py", "launcher.sh"):
        digest = hashlib.sha256((hdir / name).read_bytes()).hexdigest()
        lines.append(f"{digest}  {name}")
    (hdir / "SHA256SUMS").write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_run0(
    task_dir: Path,
    *,
    seeds: tuple[int, ...] = DEFAULT_SEEDS,
    values: tuple[float, ...] = DEFAULT_VALUES,
    elapsed_s: float = 1.0,
) -> None:
    run0 = task_dir / "run_0"
    (run0 / "repeats").mkdir(parents=True, exist_ok=True)
    _dump(run0 / "results.json", _results(values[0], elapsed_s, seeds[0]))
    for seed, value in zip(seeds, values, strict=True):
        _dump(run0 / "repeats" / f"results-{seed}.json", _results(value, elapsed_s, seed))
    mean = sum(values) / len(values)
    var = sum((v - mean) ** 2 for v in values) / (len(values) - 1) if len(values) > 1 else 0.0
    _dump(
        run0 / "sigma.json",
        {"val_mse": {"sigma": var**0.5, "seeds": list(seeds), "values": list(values)}},
    )


def _results(value: float, elapsed_s: float, seed: int) -> dict[str, Any]:
    return {"metrics": {"val_mse": value}, "elapsed_s": elapsed_s, "seed": seed, "status": "ok"}


def _dump(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")
