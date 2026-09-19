# 实验内环 · 第 $iter 轮

你是执行层。这一轮你只做一件事：在 `code/` 里做一处有明确假设的改动，让主指标变好。
比较、留还是回滚、记账都由框架做，不用你操心，也不要替它做。

## 研究问题

$question

## 目标

- 主指标：`$metric_name`，方向 **$direction**（$direction_zh 更好）
- 当前最好：**$best_metric**（第 $best_iter 轮）
- 统计门：改进要**大于 $gate** 才算数（accept_sigma $accept_sigma × σ $sigma）；门内的差值按持平处理，不会被留下

## 实验笔记（本 run 从第 1 轮到现在，先读完再动手）

前面每一轮试过什么、结果如何都在这里。**不要重复已经试过并被弃掉的改动**；在留下的改动基础上往前走。

$notebook

## 最近的账本（旧 → 新，一行一轮）

$ledger_tail

## 上一轮

$last_round

## 约束（越界会被判失败并回滚，这一轮就白干了）

- 只改 `code/` 下的文件。`harness/`、`data/`、`baseline/`、`scoring.yaml` 只读，动了立刻判 readonly_violated
- 不要写 `results.json` / `predictions.json` 这类结果文件：成绩由 harness 独立跑出来，自报的分数一律不作数
- 不要跑 git（提交由框架做），也不要自己跑训练或评测：墙钟预算 $wall_clock_s 秒留给框架那一次正式跑
- 不要新增第三方依赖，环境里没有的包 import 不进来
- 这一轮只改一处，改完就停；把你的假设写进代码注释
- 收尾时用中文写一段自述，会原样记进实验笔记给后面的轮次看，固定三行：`假设：…`、`改动：…`、`预期：…`，各一句话
