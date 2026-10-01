---
name: petab
description: 用 petab + pyPESTO + libroadrunner 装载 PEtab 问题、算 NLL、跑多起点优化。API 全部在 pypesto 0.7.0 / petab 0.9.0 / libroadrunner 2.10.0 上实测过（2026-09-16）。
---

# PEtab 参数估计工具链

以下每一条都在 Python 3.14、pypesto 0.7.0、petab 0.9.0、libroadrunner 2.10.0 上跑过。没写的 API 不要猜。

## 装载问题

```python
import petab.v1 as petab
from pypesto.petab import PetabImporter

pp = petab.Problem.from_yaml("data/<name>.yaml")   # yaml 里的相对路径相对于 yaml 所在目录
assert petab.lint_problem(pp) is False               # False = 没有问题
problem = PetabImporter(pp, simulator_type="roadrunner").create_problem()
```

- `pypesto.objective.roadrunner.PetabImporterRR` 已弃用，会打 DeprecationWarning，不要用。
- 不要用 AMICI（`simulator_type="amici"`）：它要编译 C++，本环境没装。

## 问题的形状

```python
problem.dim              # 自由参数个数
problem.x_free_indices   # 自由参数在全向量里的下标（固定参数不在里面）
problem.x_names          # 全部参数名，含固定参数，长度 > dim
problem.lb, problem.ub   # 自由参数的边界，已是 scaled（log10）尺度
pp.x_nominal_free_scaled # 自由参数的名义值（scaled），可当一个起点或对照
```

参数尺度看 PEtab parameters 表的 `parameterScale` 列；log10 参数的真实值是 `10 ** x`。

## 目标函数

```python
fval = problem.objective(x_free_scaled)   # 一个 float：NLL，越小越好；输入长度 == problem.dim
```

- **没有梯度**：`problem.objective.has_grad` 是 `False`，`sensi_orders=(0, 1)` 会抛 `ValueError`。`scipy` 的 L-BFGS-B 会自己做有限差分。
- 单次评估亚毫秒级。

## 多起点优化

```python
import numpy as np
import pypesto.optimize as optimize
import pypesto.startpoint as startpoint

problem.startpoint_method = startpoint.LatinHypercubeStartpoints()   # 或 startpoint.UniformStartpoints()
np.random.seed(seed)                                                  # 撒起点前调用，同 seed 完整复现
result = optimize.minimize(
    problem,
    optimizer=optimize.ScipyOptimizer(method="L-BFGS-B"),             # 缺省就是 L-BFGS-B；可换 Powell / Nelder-Mead / TNC / SLSQP
    n_starts=30,
    progress_bar=False,
)
best = result.optimize_result.list[0]      # 已按 fval 升序，[0] 是最好的
best.fval                                  # NLL
x_full = np.asarray(best.x)                # 长度 == len(problem.x_names)，含固定参数
x_free = x_full[problem.x_free_indices]    # 长度 == problem.dim
assert problem.objective(x_free) == best.fval
```

- `optimize.minimize(..., startpoint_method=...)` 这个关键字已弃用，要设 `problem.startpoint_method`。
- `best` 还带 `x0`（起点）、`n_fval`、`exitflag`、`message`，用来判断收敛。
- 参考耗时（本机 CPU）：4 起点 0.5 s，8 起点 0.9 s，30 起点 3.1 s。**别拿这些数反推起点数**：单个起点耗时在 0.1 到 0.3 s 之间浮动（撒在盒子边缘的起点让 ODE 更僵硬），按常数外推到一百多个起点会撞墙钟被杀（boehm-2 第 1 轮）。要用满预算就按墙钟自截断：起点分批跑，每批结束看 `time.monotonic()` 离预算还剩多少，不够一批就停，把已跑完的最优写出。

## 边界

- 起点与结果都必须在 `[problem.lb, problem.ub]` 内；越界的参数向量 harness 拒收。
- 只改优化策略，不改 PEtab 文件；NLL 只能由 harness 算，`code/` 自己算的数只用来挑最优、不写 results.json。
