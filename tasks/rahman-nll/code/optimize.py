"""基线：照抄研究者现在的跑法——固定 5 个起点、均匀撒点、scipy 默认优化器。

N_STARTS 固定不随预算调整：多撒起点是留给以后轮次的优化空间（design.md），基线不替
研究者调好。但预算信号本身必须读——它是 launcher 传下来的唯一预算契约，不读就成了
没有读取点的死配置。读取方式是按墙钟自截断：起点一个一个撒（一批 = 1 个起点），
每撒完一个看时间，剩下的预算不够再撒一个就停，把已跑完里最优的写出去。基线 5 个
起点只花约 0.7 秒，2 秒预算里本来就花不完，这条截断分支在基线上不会触发——留着
是为了让预算契约成立，也给以后轮次的 code/ 打样。
"""

import json
import os
import time
from pathlib import Path

import numpy as np
import petab.v1 as petab
import pypesto.optimize as optimize
import pypesto.startpoint as startpoint
from pypesto.petab import PetabImporter

TASK_DIR = Path(__file__).resolve().parent.parent
N_STARTS = 5  # 研究者现在的跑法，不因预算变化调整
DEFAULT_BUDGET_S = 2.0
BUDGET_FRACTION = 0.8  # 只花预算的 80%，剩下的留给评分


def main() -> None:
    seed = int(os.environ.get("AI4SCI_SEED", 42))
    budget_s = float(os.environ.get("AI4SCI_BUDGET_S", DEFAULT_BUDGET_S)) * BUDGET_FRACTION
    deadline = time.monotonic() + budget_s

    pp = petab.Problem.from_yaml(str(TASK_DIR / "data" / "Rahman_MBS2016.yaml"))
    problem = PetabImporter(pp, simulator_type="roadrunner").create_problem()
    problem.startpoint_method = startpoint.UniformStartpoints()

    np.random.seed(seed)
    best = None
    completed = 0
    for _ in range(N_STARTS):
        result = optimize.minimize(
            problem, optimizer=optimize.ScipyOptimizer(), n_starts=1, progress_bar=False
        )
        candidate = result.optimize_result.list[0]
        if best is None or candidate.fval < best.fval:
            best = candidate
        completed += 1
        if time.monotonic() >= deadline:
            break  # 这一批（1 个起点）跑完，墙钟已到：不再撒下一个

    x_full = np.asarray(best.x)
    x_free = x_full[problem.x_free_indices]
    x_names = [problem.x_names[i] for i in problem.x_free_indices]

    out = {
        "x_names": x_names,
        "x_scaled": x_free.tolist(),
        "seed": seed,
        "n_starts": completed,
        "nll_reported": float(best.fval),
    }
    (TASK_DIR / "params.json").write_text(json.dumps(out), encoding="utf-8")


if __name__ == "__main__":
    main()
