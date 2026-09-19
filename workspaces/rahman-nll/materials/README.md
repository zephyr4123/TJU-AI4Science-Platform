# data/ · Rahman_MBS2016 的 PEtab 问题定义

八个文件由研究者提供，来源是 [Benchmark-Models-PEtab](https://github.com/Benchmarking-Initiative/Benchmark-Models-PEtab) 的 `Benchmark-Models/Rahman_MBS2016/`（BSD-3-Clause，Copyright (c) 2020, Benchmarking-Initiative；引用 Zenodo <https://doi.org/10.5281/zenodo.8155057>）。原论文：上游 README 的引用表给的 DOI 是 <https://doi.org/10.1016/j.mbs.2016.07.009>（Rahman 等，Mathematical Biosciences 2016；题名未核）。案例卡在外层 `docs/cases/rahman-ode-petab/`。

这是问题定义，不是训练数据：9 个参数的边界与尺度（全部 log10）、观测公式、噪声模型、23 个测量点都在这里，**执行层不许改**（改了判 `readonly_violated`）。`code/` 只读它、harness 也只读它，NLL 由 harness 用同一份问题重算。

`simulatedData_*.tsv` 与 `visualizationSpecification_*.tsv` 是上游附带的，任务不用，留着保持与上游一致。
