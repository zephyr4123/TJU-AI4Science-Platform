- `results.json` 写在目录根，形状固定，`metrics` 必须包含 scoring.yaml 声明的**每一个**指标：

  ```json
  {"metrics": {"<指标名>": <有限数>}, "elapsed_s": <float>, "seed": <int>, "status": "ok"}
  ```

- 框架起 launcher 时**保证**给出四个环境变量，harness 拿不到就必须停，**不许写默认值**（`os.environ.get(名字, 默认)`、`${名字:-默认}` 一律不许；框架校验会抓）：
  - `AI4SCI_PYTHON`：解释器。
  - `AI4SCI_BUDGET_S`：一次跑的墙钟预算，等于 scoring.yaml 的 `wall_clock_s`。
  - `AI4SCI_INNER_K`：评分内部重复次数，等于 scoring.yaml 的 `budget.inner_k`（不写就是 1）。launcher 照它循环，并原样传给 evaluate.py；**不要在脚本里写死这个数**。
  - `AI4SCI_START_EPOCH`：launcher 起跑时自己设，evaluate.py 用它算 `elapsed_s`。
- evaluate.py 退出码：0 正常；2 产物缺失或读不出；3 形状 / 长度对不上；4 NaN / Inf / 越界；5 计时缺失。
