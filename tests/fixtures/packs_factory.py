"""在 tmp_path 里造一个最小的工作区（需求已确认）和一次合法的设计产出 `design/1/`，
供 pack / cli 测试逐条破坏。

为什么不复用仓里的 workspaces/：CI 门禁要求删掉全部工作区后框架测试照过（纲领 P-5），
夹具一旦指向真实工作区，这条门禁就成了摆设。
"""

from __future__ import annotations

import hashlib
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from framework.contracts import requirement
from framework.workspace import outputs
from framework.workspace.root import Workspace
from tests.fixtures import spaces

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

# 夹具的需求：研究者与助理对齐过、确认过的那份
REQUIREMENT = (
    "# 夹具课题\n\n## 问题\n\n在固定预算下把 val_mse 压到最低。\n\n"
    "## 怎么算好\n\ncode/ 写 predictions.json：{\"y_pred\": [...]}；"
    "evaluate.py 算 val_mse 写 results.json。\n"
)
CONFIRMED_BY = "fixture"
DEFAULT_SEEDS = (42, 43, 44)
DEFAULT_VALUES = (0.50, 0.52, 0.48)


@dataclass
class Pack:
    root: Path
    workspace: Workspace
    pack: Path
    domains_root: Path

    @property
    def output_id(self) -> str:
        return f"design/{self.pack.name}"


def default_scoring() -> dict[str, Any]:
    return {
        "format_version": 1,
        "domain": "generic",
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


def to_yaml(doc: dict[str, Any]) -> str:
    import yaml

    return yaml.safe_dump(doc, allow_unicode=True, sort_keys=False)


def make_workspace(tmp_path: Path, ws_id: str = "toy", *, confirmed: bool = True) -> Workspace:
    """一个工作区：需求写好（缺省已确认）、materials/env/ 备好。"""
    workspace = spaces.make_workspace(tmp_path, ws_id)
    workspace.requirement.write_text(REQUIREMENT, encoding="utf-8")
    write_env(workspace.materials)
    if confirmed:
        requirement.confirm(workspace.root, by=CONFIRMED_BY)
    return workspace


def make_pack(
    tmp_path: Path,
    *,
    ws_id: str = "toy",
    scoring: dict[str, Any] | None = None,
    scoring_text: str | None = None,
    domains: tuple[str, ...] = ("generic",),
    seeds: tuple[int, ...] = DEFAULT_SEEDS,
    values: tuple[float, ...] = DEFAULT_VALUES,
    elapsed_s: float = 1.0,
    confirmed: bool = True,
) -> Pack:
    """造一个工作区加一次默认合法的设计产出；每个参数对应一处可被单独破坏的地方。

    产出住在 `<root>/workspaces/<ws_id>/design/1/`（纲领 P-19），meta 记成 design 产的、ok。
    `confirmed=False` 是需求没确认那条路的入口。
    """
    workspace = make_workspace(tmp_path, ws_id, confirmed=confirmed)
    domains_root = tmp_path / "domains"
    for domain in domains:
        (domains_root / domain).mkdir(parents=True, exist_ok=True)
        (domains_root / domain / "profile.yaml").write_text(
            f"id: {domain}\ndisplay_name: {domain}\n", encoding="utf-8"
        )
    pack, meta = outputs.open_output(
        workspace, "design", title="评分脚本与基线", by="design", inputs=[], params={},
        flow=None, step=None, requirement=1 if confirmed else None, chat_id=None)
    fill_pack(pack, scoring=scoring, scoring_text=scoring_text, seeds=seeds, values=values,
              elapsed_s=elapsed_s)
    outputs.close_output(pack, meta, ok=True, line="design ok")
    return Pack(root=tmp_path, workspace=workspace, pack=pack, domains_root=domains_root)


def fill_pack(pack: Path, *, scoring: dict[str, Any] | None = None,
              scoring_text: str | None = None, seeds: tuple[int, ...] = DEFAULT_SEEDS,
              values: tuple[float, ...] = DEFAULT_VALUES, elapsed_s: float = 1.0) -> None:
    """往一个目录里铺设计那包的全部文件：scoring、code、env、harness、baseline。"""
    (pack / "code").mkdir(parents=True, exist_ok=True)
    (pack / "harness").mkdir(exist_ok=True)
    (pack / "data").mkdir(exist_ok=True)
    if scoring_text is None:
        scoring_text = to_yaml(scoring or default_scoring())
    (pack / "scoring.yaml").write_text(scoring_text, encoding="utf-8")
    (pack / "code" / "train.py").write_text(TRAIN_PY, encoding="utf-8")
    write_env(pack)
    write_harness(pack)
    write_baseline(pack, seeds=seeds, values=values, elapsed_s=elapsed_s)


def write_env(directory: Path, python_version: str = PYTHON_VERSION,
              requirements: str = "") -> None:
    edir = directory / "env"
    edir.mkdir(parents=True, exist_ok=True)
    (edir / "python-version").write_text(python_version + "\n", encoding="utf-8")
    (edir / "requirements.lock").write_text(requirements, encoding="utf-8")


def write_harness(pack: Path) -> None:
    hdir = pack / "harness"
    hdir.mkdir(exist_ok=True)
    (hdir / "launcher.sh").write_text(LAUNCHER_SH, encoding="utf-8")
    (hdir / "evaluate.py").write_text(EVALUATE_PY, encoding="utf-8")
    refresh_sums(pack)


def refresh_sums(pack: Path) -> None:
    """按磁盘现状重写 SHA256SUMS，格式与 `shasum -a 256` 一致。"""
    hdir = pack / "harness"
    lines = []
    for name in ("evaluate.py", "launcher.sh"):
        digest = hashlib.sha256((hdir / name).read_bytes()).hexdigest()
        lines.append(f"{digest}  {name}")
    (hdir / "SHA256SUMS").write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_baseline(
    pack: Path,
    *,
    seeds: tuple[int, ...] = DEFAULT_SEEDS,
    values: tuple[float, ...] = DEFAULT_VALUES,
    elapsed_s: float = 1.0,
) -> None:
    base = pack / "baseline"
    (base / "repeats").mkdir(parents=True, exist_ok=True)
    _dump(base / "results.json", _results(values[0], elapsed_s, seeds[0]))
    for seed, value in zip(seeds, values, strict=True):
        _dump(base / "repeats" / f"results-{seed}.json", _results(value, elapsed_s, seed))
    mean = sum(values) / len(values)
    var = sum((v - mean) ** 2 for v in values) / (len(values) - 1) if len(values) > 1 else 0.0
    _dump(
        base / "sigma.json",
        {"val_mse": {"sigma": var**0.5, "seeds": list(seeds), "values": list(values)}},
    )


def _results(value: float, elapsed_s: float, seed: int) -> dict[str, Any]:
    return {"metrics": {"val_mse": value}, "elapsed_s": elapsed_s, "seed": seed, "status": "ok"}


def _dump(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")
