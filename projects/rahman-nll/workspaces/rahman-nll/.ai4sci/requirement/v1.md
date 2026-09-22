# Rahman 2016 传染病模型多起点参数估计的稳定性

## 问题

对 Rahman_MBS2016 这个 9 个自由参数、23 个测量点的 PEtab 问题，每次优化 2 秒墙钟， 什么样的起点撒法、起点数与优化器组合能让负对数似然（NLL）在 25 次独立优化上的均值最低—— 也就是最少失手；谷底在 21.18 附近，研究者现在的朴素跑法 25 次均值约 21.57、约三成的次数 停在 22.2 那个次好的坑里

## 目标

主指标 `nll_mean`，越小越好；已知可达 21.18。 另记 nll_max, nll_min, n_miss。

## 材料

来源：https://github.com/Benchmarking-Initiative/Benchmark-Models-PEtab/tree/master/Benchmark-Models/Rahman_MBS2016

# data/ · Rahman_MBS2016 的 PEtab 问题定义

八个文件由研究者提供，来源是 [Benchmark-Models-PEtab](https://github.com/Benchmarking-Initiative/Benchmark-Models-PEtab) 的 `Benchmark-Models/Rahman_MBS2016/`（BSD-3-Clause，Copyright (c) 2020, Benchmarking-Initiative；引用 Zenodo <https://doi.org/10.5281/zenodo.8155057>）。原论文：上游 README 的引用表给的 DOI 是 <https://doi.org/10.1016/j.mbs.2016.07.009>（Rahman 等，Mathematical Biosciences 2016；题名未核）。案例卡在外层 `docs/cases/rahman-ode-petab/`。

这是问题定义，不是训练数据：9 个参数的边界与尺度（全部 log10）、观测公式、噪声模型、23 个测量点都在这里，**执行层不许改**（改了判 `readonly_violated`）。`code/` 只读它、harness 也只读它，NLL 由 harness 用同一份问题重算。

`simulatedData_*.tsv` 与 `visualizationSpecification_*.tsv` 是上游附带的，任务不用，留着保持与上游一致。

## 怎么算好

协调层写，执行层照它写 `harness/` 与 `code/`（`ai4sci cap design` 把它原样贴进提示；发布签的就是它和 manifest）。

这个任务问的是**稳定性**不是深度：谷底就在 NLL≈21.18，研究者的朴素跑法已经有六成的次数摸到它，
剩下四成停在 22.2 那个次好的坑里（探针实测见 `manifest.yaml` 顶部注释）。所以主指标是
**25 次独立优化的 NLL 均值**——失手一次把均值抬高约 0.04，压均值就是压失手率。

结构与 `tasks/boehm-nll/` 同构，差别只在：内部重复 25 次（不是 3 次）、每次 2 秒、多一个只记录的
`n_miss`、外层重复 5 次。

### code/optimize.py 产出什么

写 `params.json` 到任务根目录：

```json
{"x_names": ["<9 个自由参数名，顺序与 problem.x_free_indices 一致>"],
 "x_scaled": [<9 个浮点数，log10 尺度，都在 [lb, ub] 内>],
 "seed": 42, "n_starts": 5, "nll_reported": 21.4}
```

`nll_reported` 只是给人看的参考，harness 不读它。约定：

- 种子从 `AI4SCI_SEED` 读（缺省 42），撒起点前 `np.random.seed(seed)`；同一 seed 必须复现同一结果。
- 预算从 `AI4SCI_BUDGET_S` 读（launcher 给的是每次优化的份额，见下），只花 80%，按墙钟自截断，
  写成模块级可调参数。**这条不能省**：这是 launcher 传下来的唯一预算信号，基线不读它，它就成了
  没有读取点的死配置，后面的轮次也学不到「预算是硬的」。基线用 5 个起点本来就花不完 2 秒，
  自截断在基线上不会触发——留着它是为了让契约成立。
- **基线策略就是研究者现在的跑法，原样照抄**：`n_starts = 5`、`startpoint.UniformStartpoints()`、
  `optimize.ScipyOptimizer()` 缺省方法（不指定 method）。它只用掉 2 秒里的约 0.7 秒，剩下的预算是
  故意留着的优化空间——**不要替研究者调好**。
- 只读 `data/`，只写 `params.json`，不写 `results.json`。

### harness/launcher.sh

顶上两个常数：`INNER_K=25`（内部重复次数）、`INNER_BUDGET_S=2`（每次优化的预算秒数，研究者定的，
**直接写死，不要从 manifest 的 `wall_clock_s` 除出来**）。`wall_clock_s=75` 覆盖的是
`INNER_K × (INNER_BUDGET_S + 约 1.1 秒的解释器启动与模型装载开销)`（2026-09-16 实测：import 各库
1.03s、装载 PEtab+RoadRunner 0.06s、每个起点 0.131s），跟每次优化的预算不是同一个量。
注释里要把这层关系写清楚，免得以后有人把两个数「对齐」成每次 3 秒，悄悄改掉研究者定的 2 秒。开头清 `params_*.json` 与 `results.json`；记 `AI4SCI_START_EPOCH` 后循环
`i = 0 .. INNER_K-1`：内部 seed `= AI4SCI_SEED + 100*i`，以
`AI4SCI_SEED=<内部 seed> AI4SCI_BUDGET_S=<INNER_BUDGET_S>` 起 `code/optimize.py`，把 `params.json`
改名 `params_<i>.json`。导出 `AI4SCI_INNER_K` 给 evaluate.py，最后起它。`results.json` 里的 `seed`
是外层的 `AI4SCI_SEED`（缺省 42），不是内部 seed。

### harness/evaluate.py 查什么

从 `AI4SCI_INNER_K` 读 K。**缺失、不是整数、不是正数一律以退出码 5 失败退出**——不许有缺省值、
不许兜底：K 少一个，评的就是另一件事，却照样写出一份看着合法的 results.json，那是假成功。
同理 `AI4SCI_SEED` 不是整数退 2、`AI4SCI_START_EPOCH` 拿不到或不是数字退 5，一律打一句话到
stderr，不抛 traceback。依次读 `params_0.json` … `params_{K-1}.json`，
每份检查：文件存在且是合法 JSON（退 2）；`x_names` 与问题的自由参数名逐个相同、`x_scaled` 长度等于
`problem.dim`（退 3）；每个值有限且在 `[problem.lb, problem.ub]` 内（退 4）。用
`data/Rahman_MBS2016.yaml` 装载 PEtab 问题（只装一次），对每份重算 NLL（非有限数退 4）；
墙钟拿不到退 5。

`n_miss` 是 K 个 NLL 里大于 `MISS_THRESHOLD = 21.5` 的个数——这条线写成模块级常数并在
docstring 里注明来历：谷底 21.18 加上研究者定的最小有意义差距 0.3。

通过就写：

```json
{"metrics": {"nll_mean": <均值>, "nll_max": <最大>, "nll_min": <最小>, "n_miss": <整数>},
 "elapsed_s": <float>, "seed": <int>, "status": "ok"}
```

顶层只有这四个字段。stdout 打一行摘要 `nll_mean=… nll_max=… nll_min=… n_miss=… seed=… elapsed_s=…`。

### harness/make_run0.sh

种子 42 43 44 45 46（与 `repeat_k: 5` 对应），σ 对四个指标各写一条 `{sigma, seeds, values}`，
清产物那行清 `params_*.json`。

## 验收

- R1：主指标 nll_mean 优于 run_0 基线，且差值超过 accept_sigma 倍的重复跑标准差（或 min_delta）
- R2：code/ 只产出 params.json（9 个自由参数，log10 尺度，在 PEtab 边界内）；NLL 由 harness 用同一份 PEtab 问题重算，code/ 自己算的数不进 results.json

## 预算

一次跑 75 秒墙钟，最多改 30 轮；基线重复 5 次算 σ，差值超过 2.0 倍 σ（至少 0.15） 才算改进。
