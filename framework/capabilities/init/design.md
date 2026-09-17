# design.md · 给执行层的产物契约与基线策略

协调层写，执行层照它写 `harness/` 与 `code/`（`ai4sci cap design` 把它原样贴进提示；发布签的就是它和 manifest.yaml）。
这是「怎么算好」的人话版，研究者签字签的是它，不是代码。写法样本：`tasks/boehm-nll/design.md`。

## code/ 产出什么

{{todo}}：执行层要写哪个文件、输出什么形状（比如 `params.json` 有哪些字段、取值范围）。
约定：种子从 `AI4SCI_SEED` 读（缺省 42）；预算从 `AI4SCI_BUDGET_S` 读、按墙钟自截断，写成可调参数。

## harness/launcher.sh

{{todo}}：怎么起 `code/`（用 `$AI4SCI_PYTHON`，不写裸 python）；内部重复几次（顶上的 `INNER_K` 与 manifest 的
`budget.inner_k` 一致）；每次的预算怎么分；产物怎么交给 evaluate.py。

## harness/evaluate.py 查什么

{{todo}}：拒收什么（文件缺、形状不对、越界）、各退什么码；拿 `data/` 里的什么重算指标，不采信 code/ 自报的数；
写进 `results.json` 的字段。框架保证给 `AI4SCI_PYTHON` `AI4SCI_BUDGET_S` `AI4SCI_INNER_K`：拿不到就退非零，不写默认值。

## harness/make_run0.sh

{{todo}}：基线用研究者现在的做法原样跑，不替他调好；重复几次（与 `budget.repeat_k` 对应）、种子怎么定、σ 怎么写。
