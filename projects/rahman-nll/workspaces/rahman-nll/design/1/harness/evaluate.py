"""评测层：读 K 份基线产物，用同一份 PEtab 问题重算 NLL，写 results.json。

MISS_THRESHOLD = 21.5：谷底 NLL≈21.18 加研究者定的最小有意义差距 0.3（见 manifest.yaml
顶部注释），超过这条线就算没摸到谷底；n_miss 只记录不判分。
"""

import json
import os
import statistics
import sys
import time
from pathlib import Path

import numpy as np
import petab.v1 as petab
from pypesto.petab import PetabImporter

TASK_DIR = Path(__file__).resolve().parent.parent
DEFAULT_SEED = 42
MISS_THRESHOLD = 21.5


def _fail(code: int, message: str) -> None:
    print(f"evaluate: {message}", file=sys.stderr)
    raise SystemExit(code)


def _load_json(path: Path) -> dict:
    if not path.is_file():
        _fail(2, f"文件缺失：{path}")
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except ValueError as exc:
        _fail(2, f"{path} 不是合法 JSON：{exc}")
        raise AssertionError("不可达") from exc
    if not isinstance(doc, dict):
        _fail(2, f"{path} 顶层应为 JSON 对象，实际是 {type(doc).__name__}")
        raise AssertionError("不可达")
    return doc


def _inner_k() -> int:
    # 缺失或非正整数一律拒收：K 悄悄退回缺省值会让 nll_mean 的统计口径被环境变量
    # 无声改掉，写出一份看着合法、口径却错了的 results.json（假成功）。
    raw = os.environ.get("AI4SCI_INNER_K")
    if raw is None:
        _fail(5, "未设 AI4SCI_INNER_K：应为正整数")
    try:
        k = int(raw)
    except ValueError:
        _fail(5, f"AI4SCI_INNER_K 应为正整数，实际是 {raw!r}")
        raise AssertionError("不可达") from None
    if k <= 0:
        _fail(5, f"AI4SCI_INNER_K 应为正整数，实际是 {k}")
    return k


def _elapsed_s() -> float:
    start = os.environ.get("AI4SCI_START_EPOCH")
    if start is None:
        _fail(5, "拿不到 AI4SCI_START_EPOCH，不填 0 假装量过")
    try:
        return time.time() - float(start)
    except ValueError:
        _fail(5, f"AI4SCI_START_EPOCH 应为数字，实际是 {start!r}")
        raise AssertionError("不可达") from None


def _seed() -> int:
    raw = os.environ.get("AI4SCI_SEED", str(DEFAULT_SEED))
    try:
        return int(raw)
    except ValueError:
        _fail(2, f"AI4SCI_SEED 应为整数，实际是 {raw!r}")
        raise AssertionError("不可达") from None


def _score_one(
    path: Path, free_names: list, dim: int, lb: np.ndarray, ub: np.ndarray, objective
) -> float:
    doc = _load_json(path)
    x_names = doc.get("x_names")
    x_scaled = doc.get("x_scaled")
    if not isinstance(x_names, list) or x_names != free_names:
        _fail(3, f"{path} 的 x_names 与问题自由参数名不符")
    if not isinstance(x_scaled, list) or len(x_scaled) != dim:
        _fail(3, f"{path} 的 x_scaled 长度应为 {dim}")
    x = np.asarray(x_scaled, dtype=float)
    if not np.all(np.isfinite(x)):
        _fail(4, f"{path} 的 x_scaled 含 NaN/Inf")
    if np.any(x < lb) or np.any(x > ub):
        _fail(4, f"{path} 的 x_scaled 越界")
    nll = float(objective(x))
    if not np.isfinite(nll):
        _fail(4, f"{path} 重算 NLL 得到 NaN/Inf")
    return nll


def main() -> None:
    k = _inner_k()
    pp = petab.Problem.from_yaml(str(TASK_DIR / "data" / "Rahman_MBS2016.yaml"))
    problem = PetabImporter(pp, simulator_type="roadrunner").create_problem()
    free_names = [problem.x_names[i] for i in problem.x_free_indices]

    nlls = [
        _score_one(
            TASK_DIR / f"params_{i}.json",
            free_names,
            problem.dim,
            problem.lb,
            problem.ub,
            problem.objective,
        )
        for i in range(k)
    ]

    n_miss = sum(1 for v in nlls if v > MISS_THRESHOLD)
    metrics = {
        "nll_mean": statistics.fmean(nlls),
        "nll_max": max(nlls),
        "nll_min": min(nlls),
        "n_miss": n_miss,
    }
    results = {
        "metrics": metrics,
        "elapsed_s": _elapsed_s(),
        "seed": _seed(),
        "status": "ok",
    }
    (TASK_DIR / "results.json").write_text(json.dumps(results), encoding="utf-8")
    print(
        f"nll_mean={metrics['nll_mean']:.4f} nll_max={metrics['nll_max']:.4f} "
        f"nll_min={metrics['nll_min']:.4f} n_miss={metrics['n_miss']} "
        f"seed={results['seed']} elapsed_s={results['elapsed_s']:.2f}"
    )


if __name__ == "__main__":
    main()
