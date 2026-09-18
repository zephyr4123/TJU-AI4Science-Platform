"""基线:pyPESTO 默认多起点优化,撒 5 个起点找 Boehm STAT5 模型的 NLL 极小点。

这是唯一由后续 agent 逐轮改进的文件。可调参数集中在顶上,改策略优先改这几行 + 下面
optimize.minimize 的调用方式,不要动产物契约(只写 params.json)。

约定(改的时候别破坏):
  * 只读 data/,只写 params.json;NLL 由 harness/evaluate.py 用同一份 PEtab 问题重算,
    这里算出的 nll_reported 只是给人看,不进 results.json(自己不能给自己打分)。
  * 种子从 AI4SCI_SEED 读,撒起点前 np.random.seed(seed),同一 seed 要能复现同一结果。
  * 预算从 AI4SCI_BUDGET_S 读;基线 5 起点顶多几百毫秒,用不满预算,但把它读进来留给
    以后按预算动态定起点数的策略用。
"""

import json
import os
from pathlib import Path

import numpy as np
import petab.v1 as petab
import pypesto.optimize as optimize
import pypesto.startpoint as startpoint
from pypesto.petab import PetabImporter

# ---------------- 可调参数:调策略就改这几行 ----------------
N_STARTS = 5  # 起点数,学长给的基线值,故意留改进空间,不要替他调好
STARTPOINT_METHOD = startpoint.UniformStartpoints()  # 起点撒法
OPTIMIZER = optimize.ScipyOptimizer()  # 缺省 method 即 L-BFGS-B
# ------------------------------------------------------------

DEFAULT_SEED = 42
DEFAULT_BUDGET_S = 30.0
BUDGET_USE_RATIO = 0.8  # 只花预算的 80%,留时间给 harness 评分

TASK_DIR = Path(__file__).resolve().parent.parent
PETAB_YAML = TASK_DIR / "data" / "Boehm_JProteomeRes2014.yaml"


def main() -> None:
    seed = int(os.environ.get("AI4SCI_SEED", str(DEFAULT_SEED)))
    budget_s = float(os.environ.get("AI4SCI_BUDGET_S", str(DEFAULT_BUDGET_S)))
    usable_budget_s = budget_s * BUDGET_USE_RATIO  # 基线用不到,留给以后按预算定起点数的策略
    _ = usable_budget_s

    pp = petab.Problem.from_yaml(str(PETAB_YAML))
    problem = PetabImporter(pp, simulator_type="roadrunner").create_problem()
    problem.startpoint_method = STARTPOINT_METHOD

    np.random.seed(seed)
    result = optimize.minimize(
        problem,
        optimizer=OPTIMIZER,
        n_starts=N_STARTS,
        progress_bar=False,
    )

    best = result.optimize_result.list[0]
    x_full = np.asarray(best.x)
    x_free = x_full[problem.x_free_indices]
    free_names = [problem.x_names[i] for i in problem.x_free_indices]

    doc = {
        "x_names": free_names,
        "x_scaled": [float(v) for v in x_free],
        "seed": seed,
        "n_starts": N_STARTS,
        "nll_reported": float(best.fval),
    }
    (TASK_DIR / "params.json").write_text(json.dumps(doc), encoding="utf-8")


if __name__ == "__main__":
    main()
