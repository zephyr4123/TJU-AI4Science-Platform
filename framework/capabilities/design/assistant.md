# 评分脚本与基线：给研究助理的说明

什么时候用：要改进一个方法、结果能用一个指标自动打分的时候，设计阶段用它写评分契约、评分脚本与基线代码，跑出起点成绩。要拿论文自己的代码原样跑，用设计阶段的另一个步骤。

前提：
- 需求确认了；`materials/` 里有数据与研究者能跑的脚本。
- `materials/env/` 里有 `python-version` 与 `requirements.lock`（研究者的 pip freeze；研究者没有现成环境就 `ai4sci env resolve --python <X.Y> <包名>… --ws <名字>` 算一份完整清单，不要手写，手写的只有顶层包，建环境会报「不完整」）。
- `materials/env/` 改了之后 `--continue design/<n>` 会拒（环境变了），重开一次。
- 领域包缺省 generic，`--domain` 换。

怎么跑：`ai4sci cap design --ws <名字> --detach`（几个工作区共用原件、工作区自己的原件开工时一起搬进 `data/`，同名以工作区的为准）。框架起执行层照需求写 `scoring.yaml`、`harness/`、`code/` 草稿，回来自己封 harness、跑 ruff 与契约校验，都过了就按 `env/` 建环境、跑基线、算预检。日志在 `design/<n>/executor/session-N/`。不要自己跑 `make_run0.sh`：基线的预算和内环用同一组环境变量，框架起才对。

结局：
- 成了：结论行带 `baseline / sigma / gate / room`。接下来对照需求「怎么算好」核对评分脚本，报给人（流程里多半有个断点等人签）。
- 草稿有问题：一行一条在 stderr、退 1。把 stderr 存成文件喂回去：`ai4sci cap design --continue design/<n> --feedback @<文件> --ws <名字> --detach`，执行层看着现状文件照着改。**不要自己替它改 harness**。
- 预检没过（门是 0，或基线到尽头不到一个门）：退 1 并说清，这道题不值得跑，别硬跑；跟研究者商量改题或松门。
- 基线没跑成（环境装不上、机器换了、被叫停）：`--continue design/<n>` 接着干，不用给修改意见。

值不值得跑：问研究者、查文献，尽头有数就让执行层写进 `scoring.yaml` 主指标的 `attainable`，基线跑完框架会算「基线到尽头有几个门的空间」。σ 大不是错：随机性大的基线统计门就严，改进必须超过基线自己的抖动才算数。要不要放宽 `accept_sigma` 是人的决定。
