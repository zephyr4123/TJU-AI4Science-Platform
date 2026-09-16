"""评测层:只吃产物文件,算分,写 results.json。

框架注入,执行层改不了。输入是 code/optimize.py 每次优化写出的 params.json,harness/launcher.sh
循环跑 AI4SCI_INNER_K 次后依次改名成 params_0.json ... params_{K-1}.json;每一份都用同一份 PEtab
问题(data/Boehm_JProteomeRes2014.yaml)重新算 NLL,取均值/最小值/最大值——code/ 自己算的
nll_reported 不进 results.json,防止自己给自己打分。主指标 nll_mean 量的是策略的期望表现,
不是单次运气(改指标的理由见 manifest.yaml 顶部注释,外层 #40)。

elapsed_s 从 launcher.sh 写进环境变量 AI4SCI_START_EPOCH 的起跑时刻算起;AI4SCI_INNER_K 也只由
launcher.sh 传入。单独跑这个脚本(没有 launcher.sh 先起跑)时这些变量不在,直接报错退出,
不假装量过。

退出码:0 正常;2 params_i.json 缺失或不是合法 JSON;3 x_names 与自由参数名对不上或
x_scaled 长度不等于 problem.dim;4 出现非有限数、越界,或算出的 NLL 不是有限数;
5 墙钟或 AI4SCI_INNER_K 拿不到。非零一律不写 results.json,不抛 traceback——
没有 results.json 就是没有成绩。
"""

import json
import math
import os
import sys
import time
from pathlib import Path

import numpy as np
import petab.v1 as petab
from pypesto.petab import PetabImporter

TASK_DIR = Path(__file__).resolve().parent.parent
PETAB_YAML = TASK_DIR / "data" / "Boehm_JProteomeRes2014.yaml"
DEFAULT_SEED = 42


def _fail(code: int, message: str) -> None:
    print(f"evaluate: {message}", file=sys.stderr)
    raise SystemExit(code)


def _elapsed_s() -> float:
    raw = os.environ.get("AI4SCI_START_EPOCH")
    if not raw:
        _fail(5, "拿不到墙钟:AI4SCI_START_EPOCH 未设(须由 harness/launcher.sh 起跑,不能单独调用)")
    try:
        started = float(raw)
    except ValueError:
        _fail(5, f"AI4SCI_START_EPOCH 期望数字,实际 {raw!r}")
    return max(0.0, time.time() - started)


def _inner_k() -> int:
    raw = os.environ.get("AI4SCI_INNER_K")
    if not raw:
        _fail(5, "拿不到 AI4SCI_INNER_K:未设(须由 harness/launcher.sh 起跑,不能单独调用)")
    try:
        k = int(raw)
    except ValueError:
        k = 0
    if k <= 0:
        _fail(5, f"AI4SCI_INNER_K 期望正整数,实际 {raw!r}")
    return k


def _nll_for(path: Path, problem, free_names: list) -> float:
    if not path.is_file():
        _fail(2, f"文件缺失:{path}")
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except ValueError as exc:
        _fail(2, f"{path.name} 不是合法 JSON:{exc}")

    x_names = doc.get("x_names") if isinstance(doc, dict) else None
    x_scaled = doc.get("x_scaled") if isinstance(doc, dict) else None
    if not isinstance(x_names, list) or not isinstance(x_scaled, list):
        _fail(2, f"{path.name} 缺少数组字段 x_names / x_scaled")

    if len(x_scaled) != problem.dim:
        _fail(3, f"{path.name}: x_scaled 长度对不上:期望 {problem.dim},实际 {len(x_scaled)}")
    if x_names != free_names:
        _fail(3, f"{path.name}: x_names 与自由参数名对不上:期望 {free_names},实际 {x_names}")

    for name, value, lb, ub in zip(x_names, x_scaled, problem.lb, problem.ub, strict=True):
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            _fail(4, f"{path.name}: x_scaled[{name}] 不是数字:{value!r}")
        if not math.isfinite(value):
            _fail(4, f"{path.name}: x_scaled[{name}] 是 NaN / Inf:{value!r}")
        if value < lb or value > ub:
            _fail(4, f"{path.name}: x_scaled[{name}]={value} 越界 [{lb}, {ub}]")

    nll = float(problem.objective(np.asarray(x_scaled, dtype=float)))
    if not math.isfinite(nll):
        _fail(4, f"{path.name}: 算出的 nll 不是有限数:{nll!r}")
    return nll


def main() -> None:
    seed_raw = os.environ.get("AI4SCI_SEED", str(DEFAULT_SEED))
    try:
        seed = int(seed_raw)
    except ValueError:
        _fail(2, f"AI4SCI_SEED 期望整数,实际 {seed_raw!r}")

    k = _inner_k()

    pp = petab.Problem.from_yaml(str(PETAB_YAML))
    problem = PetabImporter(pp, simulator_type="roadrunner").create_problem()
    free_names = [problem.x_names[i] for i in problem.x_free_indices]

    nlls = [_nll_for(TASK_DIR / f"params_{i}.json", problem, free_names) for i in range(k)]

    nll_mean = sum(nlls) / len(nlls)
    nll_min = min(nlls)
    nll_max = max(nlls)

    results = {
        "metrics": {"nll_mean": nll_mean, "nll_min": nll_min, "nll_max": nll_max},
        "elapsed_s": _elapsed_s(),
        "seed": seed,
        "status": "ok",
    }
    (TASK_DIR / "results.json").write_text(json.dumps(results), encoding="utf-8")
    print(
        f"nll_mean={nll_mean:.6f} nll_min={nll_min:.6f} nll_max={nll_max:.6f} "
        f"seed={seed} elapsed_s={results['elapsed_s']:.2f}"
    )


if __name__ == "__main__":
    main()
