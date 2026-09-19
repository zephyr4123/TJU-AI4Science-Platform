# Boehm 2014 STAT5 模型的多起点参数估计策略

## 问题

对 Boehm_JProteomeRes2014 这个 9 个自由参数、48 个测量点的 PEtab 问题，每次优化 20 秒墙钟， 什么样的起点撒法、起点数与优化器组合能把负对数似然（NLL）在 3 个随机 seed 上的均值压到最低； 名义参数处 NLL 为 138.22

## 目标

主指标 `nll_mean`，越小越好。 另记 nll_min, nll_max。

## 材料

来源：docs/cases/boehm-stat5-petab

# data/ · Boehm_JProteomeRes2014 的 PEtab 问题定义

九个文件原样取自 [Benchmark-Models-PEtab](https://github.com/Benchmarking-Initiative/Benchmark-Models-PEtab) 的 `Benchmark-Models/Boehm_JProteomeRes2014/`（BSD-3-Clause，Copyright (c) 2020, Benchmarking-Initiative；引用 Zenodo <https://doi.org/10.5281/zenodo.8155057>）。原论文：Boehm ME, Adlung L, Schilling M, et al. J Proteome Res 2014，<https://pubmed.ncbi.nlm.nih.gov/25333863/>。

这是问题定义，不是训练数据：参数边界、观测公式、噪声模型、48 个测量点都在这里，**执行层不许改**（改了判 `readonly_violated`）。`code/` 只读它、harness 也只读它，NLL 由 harness 用同一份问题重算。`simulatedData_*.tsv` 与 `visualizationSpecification_*.tsv` 是 benchmark 附带的，任务不用，留着保持与上游一致。

来源案例卡：外层 `docs/cases/boehm-stat5-petab/README.md`。

## 怎么算好

协调层写，执行层照它写 `harness/` 与 `code/`（`ai4sci cap design` 把它原样贴进提示；发布签的就是它和 manifest）。这份是第一个真任务的样本：第一版按单次 NLL 写，2026-09-16 改成 3 个内部 seed 的均值（理由见 manifest.yaml 顶部注释，外层 #40），下面是改后的契约。

### code/optimize.py 产出什么

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

### harness/launcher.sh

顶上两个常数：`INNER_K=3`（内部 seed 数）、`TOTAL_BUDGET_S=60`（与 manifest 的 `wall_clock_s` 一致，注释写明改一处就要改另一处）；每次优化的预算 `INNER_BUDGET_S = TOTAL_BUDGET_S / INNER_K`。开头清 `params_*.json` 与 `results.json`；记 `AI4SCI_START_EPOCH` 后循环 `i = 0 .. INNER_K-1`：内部 seed `= AI4SCI_SEED + 100*i`，以 `AI4SCI_SEED=<内部 seed> AI4SCI_BUDGET_S=<INNER_BUDGET_S>` 起 `code/optimize.py`，把 `params.json` 改名 `params_<i>.json`。导出 `AI4SCI_INNER_K` 给 evaluate.py，最后起它。`results.json` 里的 `seed` 是外层的 `AI4SCI_SEED`（缺省 42），不是内部 seed。

### harness/evaluate.py 查什么

从 `AI4SCI_INNER_K` 读 K（缺失或不是正整数退 5）。依次读 `params_0.json` … `params_{K-1}.json`，每份检查：文件存在且是合法 JSON（退 2）；`x_names` 与问题的自由参数名逐个相同、`x_scaled` 长度等于 `problem.dim`（退 3）；每个值有限且在 `[problem.lb, problem.ub]` 内（退 4）。用 `data/Boehm_JProteomeRes2014.yaml` 装载 PEtab 问题（只装一次），对每份重算 NLL（非有限数退 4）；墙钟拿不到退 5。通过就写：

```json
{"metrics": {"nll_mean": <均值>, "nll_min": <最小>, "nll_max": <最大>},
 "elapsed_s": <float>, "seed": <int>, "status": "ok"}
```

顶层只有这四个字段。stdout 打一行摘要 `nll_mean=… nll_min=… nll_max=… seed=… elapsed_s=…`。

### harness/make_run0.sh

种子 42 43 44（与 `repeat_k: 3` 对应），σ 对三个指标各写一条 `{sigma, seeds, values}`，清产物那行清 `params_*.json`。

## 验收

- R1：主指标 nll 优于 run_0 基线，且差值超过 accept_sigma 倍的重复跑标准差（或 min_delta）
- R2：code/ 只产出 params.json（9 个自由参数，log10 尺度，在 PEtab 边界内）；NLL 由 harness 用同一份 PEtab 问题重算，code/ 自己算的数不进 results.json

## 预算

一次跑 60 秒墙钟，最多改 30 轮；基线重复 3 次算 σ，差值超过 2.0 倍 σ（至少 1.0） 才算改进。
