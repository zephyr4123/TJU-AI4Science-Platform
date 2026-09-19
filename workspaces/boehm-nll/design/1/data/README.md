# data/ · Boehm_JProteomeRes2014 的 PEtab 问题定义

九个文件原样取自 [Benchmark-Models-PEtab](https://github.com/Benchmarking-Initiative/Benchmark-Models-PEtab) 的 `Benchmark-Models/Boehm_JProteomeRes2014/`（BSD-3-Clause，Copyright (c) 2020, Benchmarking-Initiative；引用 Zenodo <https://doi.org/10.5281/zenodo.8155057>）。原论文：Boehm ME, Adlung L, Schilling M, et al. J Proteome Res 2014，<https://pubmed.ncbi.nlm.nih.gov/25333863/>。

这是问题定义，不是训练数据：参数边界、观测公式、噪声模型、48 个测量点都在这里，**执行层不许改**（改了判 `readonly_violated`）。`code/` 只读它、harness 也只读它，NLL 由 harness 用同一份问题重算。`simulatedData_*.tsv` 与 `visualizationSpecification_*.tsv` 是 benchmark 附带的，任务不用，留着保持与上游一致。

来源案例卡：外层 `docs/cases/boehm-stat5-petab/README.md`。
