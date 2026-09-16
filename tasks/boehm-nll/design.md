# design.md · 给执行层的产物契约与基线策略

协调层写，执行层照它写 `harness/` 与 `code/`（`ai4sci task design` 把它原样贴进提示）。这份是第一个真任务的样本：第一版按单次 NLL 写，2026-09-16 改成 3 个内部 seed 的均值（理由见 manifest.yaml 顶部注释，外层 #40），下面是改后的契约。

## code/optimize.py 产出什么

写 `params.json` 到任务根目录：

```json
{"x_names": ["<9 个自由参数名，顺序与 problem.x_free_indices 一致>"],
 "x_scaled": [<9 个浮点数，log10 尺度，都在 [lb, ub] 内>],
 "seed": 42, "n_starts": 5, "nll_reported": 213.18}
```

`nll_reported` 只是给人看的参考，harness 不读它。约定：

- 种子从 `AI4SCI_SEED` 读（缺省 42），撒起点前 `np.random.seed(seed)`；同一 seed 必须复现同一结果。
- 预算从 `AI4SCI_BUDGET_S` 读（launcher 给的是每次优化的份额，见下），只花 80%，按墙钟自截断，写成可调参数。
- **基线策略就是最朴素的 pyPESTO 默认流程**：`n_starts = 5`、`startpoint.UniformStartpoints()`、`optimize.ScipyOptimizer()` 缺省方法。这是研究者给的基线，故意留着优化空间，不要替他调好。
- 只读 `data/`，只写 `params.json`，不写 `results.json`。

## harness/launcher.sh

顶上两个常数：`INNER_K=3`（内部 seed 数）、`TOTAL_BUDGET_S=60`（与 manifest 的 `wall_clock_s` 一致，注释写明改一处就要改另一处）；每次优化的预算 `INNER_BUDGET_S = TOTAL_BUDGET_S / INNER_K`。开头清 `params_*.json` 与 `results.json`；记 `AI4SCI_START_EPOCH` 后循环 `i = 0 .. INNER_K-1`：内部 seed `= AI4SCI_SEED + 100*i`，以 `AI4SCI_SEED=<内部 seed> AI4SCI_BUDGET_S=<INNER_BUDGET_S>` 起 `code/optimize.py`，把 `params.json` 改名 `params_<i>.json`。导出 `AI4SCI_INNER_K` 给 evaluate.py，最后起它。`results.json` 里的 `seed` 是外层的 `AI4SCI_SEED`（缺省 42），不是内部 seed。

## harness/evaluate.py 查什么

从 `AI4SCI_INNER_K` 读 K（缺失或不是正整数退 5）。依次读 `params_0.json` … `params_{K-1}.json`，每份检查：文件存在且是合法 JSON（退 2）；`x_names` 与问题的自由参数名逐个相同、`x_scaled` 长度等于 `problem.dim`（退 3）；每个值有限且在 `[problem.lb, problem.ub]` 内（退 4）。用 `data/Boehm_JProteomeRes2014.yaml` 装载 PEtab 问题（只装一次），对每份重算 NLL（非有限数退 4）；墙钟拿不到退 5。通过就写：

```json
{"metrics": {"nll_mean": <均值>, "nll_min": <最小>, "nll_max": <最大>},
 "elapsed_s": <float>, "seed": <int>, "status": "ok"}
```

顶层只有这四个字段。stdout 打一行摘要 `nll_mean=… nll_min=… nll_max=… seed=… elapsed_s=…`。

## harness/make_run0.sh

种子 42 43 44（与 `repeat_k: 3` 对应），σ 对三个指标各写一条 `{sigma, seeds, values}`，清产物那行清 `params_*.json`。
