# 十分钟接一个任务

把你手里"一段能跑的代码 + 一个越小（或越大）越好的数"接进平台，让实验内环替你调。读完照做，不用问人。验收标准就是这句：**换一个人、换一个任务，照这份文档接进来就能跑。** 卡在哪一步，就是这份文档的 bug，请开 issue。

## 你要先有

1. 一段能在**几分钟内**跑完一次的代码，单入口（一个脚本、一条命令）。
2. 一个**标量指标**，方向明确：越小越好或越大越好。
3. 一个能算这个指标的独立脚本，它只读你代码写出来的产物文件，不读你代码的内存。

没有第 3 条就先写它：这是 `harness/evaluate.py`，也是整套机制里唯一不许 AI 碰的东西。

## 目录

先起一个工作区（`ai4sci workspace new <name>`，或页面上「新建工作区」），任务包住在它的 `task/` 下（纲领 P-15：一个工作区一份需求）。下面的命令都在工作区目录里跑，不带路径。

```
workspaces/<name>/task/
├── manifest.yaml        任务声明：问题、指标、预算、验收
├── design.md            产物契约与「怎么算好」；发布签它，ai4sci cap design 照它写
├── publish.json         发布记录：ai4sci sign task 写，后面的按钮都查它
├── env/                 任务自带环境
│   ├── python-version   一行，如 3.14
│   └── requirements.lock  逐行 name==version；零依赖就留空文件
├── harness/             评测，只读，hash 锁定
│   ├── launcher.sh      唯一入口：清产物 → 跑 code/ → 跑 evaluate.py
│   ├── evaluate.py      读产物算分，写 results.json
│   ├── make_run0.sh     跑出基线 + 重复 + σ
│   └── SHA256SUMS       上面几个文件的 sha256
├── code/                你的基线；AI 唯一能改的地方
├── data/                输入与真值；可选
└── run_0/               make_run0.sh 生成：基线成绩 + 重复 + σ
```

`<name>` 只用小写字母、数字、连字符，是工作区名，manifest 的 `id` 必须与它相同。

## 1. manifest.yaml

```yaml
format_version: 1
id: <name>
domain: generic                  # 有对应的领域包（domains/<id>/）就写它的名字
source: docs/cases/<slug>        # 可选：这个任务从哪来
title: 一句话标题
question: >
  一段话说清研究问题：在什么预算下，什么策略能把哪个指标压到多低
metrics:
  - name: val_mse                # 指标名，results.json 里同名
    direction: minimize          # 或 maximize
    primary: true                # 恰好一个
budget:
  wall_clock_s: 60               # 一次跑完的墙钟预算；超 1.5 倍判超时
  max_iterations: 30             # 内环最多跑几轮
  repeat_k: 3                    # 同配置重复几次估噪声
  # inner_k: 1                   # 评分脚本内部把 code/ 跑几次取均值当一次成绩；不写按 1
  accept_sigma: 2.0              # 改进要大于几倍 σ 才算数
  # min_delta: 0.001             # 重复跑完全一致（σ=0）时必填：最小改进量
requirements:
  - id: R1
    type: numeric
    must_pass: true
    description: 主指标优于 run_0 基线且过统计门
```

方向、预算、统计门是**你**定的，不是平台猜的。填错的代价是内环白跑。

## 2. env/

```
env/python-version      3.14
env/requirements.lock   numpy==2.5.3
                        scipy==1.18.1
```

- 版本必须钉死（`==`），`>=`、URL、`-e` 一律不收。
- 平台用 [uv](https://docs.astral.sh/uv/) 找或拉这个版本的解释器、按 lock 建 venv；你的依赖不会装进平台的环境，平台的也不会混进你的。
- 拿到精确版本最省事的办法：先在任何地方装好，`pip freeze` 抄过来。

## 3. harness/

三条硬规矩，`ai4sci show task` 都会查：

1. **Python 只经 `"$AI4SCI_PYTHON"` 起。** 框架跑你的 harness 时把任务 venv 的解释器放进这个变量；脚本里出现裸 `python` / `python3` 直接判不合法。框架同时保证给 `AI4SCI_BUDGET_S`（一次跑的墙钟预算，等于 `wall_clock_s`）和 `AI4SCI_INNER_K`（评分内部重复次数，等于 `budget.inner_k`）：launcher 用 `"${AI4SCI_INNER_K:?}"` 这种写法拿，拿不到就停；**给这几个变量写默认值判不合法**（`os.environ.get("AI4SCI_INNER_K", 5)` 这种会算出一份看着合法的假成绩）。`AI4SCI_SEED` 缺省 42 是唯一允许的默认值。
2. **`evaluate.py` 只读产物文件**，算完写 `results.json`，形状固定：
   ```json
   {"metrics": {"val_mse": 0.0231}, "elapsed_s": 0.27, "seed": 42, "status": "ok"}
   ```
   产物缺失、长度不对、NaN：打一句话到 stderr，`SystemExit(非零)`，**不写 results.json**。没有 results.json 就是没有成绩，这是防假成功的最后一道。
3. **`SHA256SUMS` 与磁盘一致。** 改了任何 harness 文件就重新生成：
   ```bash
   cd workspaces/<name>/task/harness && shasum -a 256 launcher.sh evaluate.py make_run0.sh > SHA256SUMS
   ```

`launcher.sh` 的骨架（照抄 `workspaces/mlp-regression/task/harness/launcher.sh`）：

```bash
#!/usr/bin/env bash
set -euo pipefail
: "${AI4SCI_PYTHON:?未设 AI4SCI_PYTHON：经 ai4sci cap baseline 起，不要手工跑}"
: "${AI4SCI_BUDGET_S:?}"      # 框架与 ai4sci cap baseline 都会给
: "${AI4SCI_INNER_K:?}"
TASK_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$TASK_DIR"
rm -f <你的产物文件> results.json
AI4SCI_START_EPOCH="$("$AI4SCI_PYTHON" -c 'import time; print(time.time())')"
export AI4SCI_START_EPOCH
"$AI4SCI_PYTHON" code/<入口>.py
"$AI4SCI_PYTHON" harness/evaluate.py
```

`code/` 从环境变量 `AI4SCI_SEED` 拿种子；同一 seed 必须复现同一结果。`make_run0.sh` 照抄 `mlp-regression` 的，只改指标名与种子列表；它由 `ai4sci cap baseline` 起，预算与 inner_k 从那里来。

## 4. 四条命令

```bash
cd workspaces/<name>
ai4sci sign task --by <你>        # 发布：签 manifest.yaml 与 design.md，写 publish.json
ai4sci cap baseline               # 跑 make_run0.sh：基线 + repeat_k 次重复 + σ → run_0/，跑完预检
ai4sci show task                  # 退 0 才算接进来了
```

没发布，`cap baseline` 与 `cap start` 都不开；发布后改了 manifest 或 design.md 要重新发布。预检退 1 说"无解"是门太高或题太浅（manifest 主指标可写 `attainable` 尽头值），改题或松门，别硬跑。

`validate` 退 1 时 stderr 一行一条告诉你哪个文件哪个字段期望什么、实际什么。

## 5. 跑起来

```bash
ai4sci cap start --run-id demo
ai4sci cap experiment demo --max-iters 5
ai4sci show run demo
```

`cap start` 会按你的 `env/` 给这个 run 单独建一份环境（`runs/demo/.venv`，在工作区里），跑起来后不再回头看任务目录。

## 常见报错

| stderr | 意思 | 怎么办 |
|---|---|---|
| `字段 <顶层>: 'format_version' is a required property` | manifest 缺契约版本 | 第一行加 `format_version: 1` |
| `env/: 目录缺失` | 没带环境 | 建 `env/` 两个文件，零依赖也要有空的 lock |
| `harness/launcher.sh:12: 裸调 python` | launcher 用了 PATH 上的 python | 改成 `"$AI4SCI_PYTHON"` |
| `harness/evaluate.py:45: 给 AI4SCI_INNER_K 写了默认值` | 评分脚本拿不到框架保证的变量时自己兜底 | 改成拿不到就 `SystemExit(非零)` |
| `requirements.lock:3: 期望钉死的 name==version` | 依赖没钉版本 | 写成 `name==x.y.z` |
| `harness/evaluate.py: sha256 不一致` | 改了 harness 没更新校验和 | 重新生成 SHA256SUMS |
| `run_0/repeats/: 期望恰好 budget.repeat_k=3 个` | 重复次数与 manifest 不符 | 改 make_run0.sh 的 SEEDS 或 manifest 的 repeat_k |
| `σ=0，统计门退化为 0` | 重复跑完全一致 | manifest 加 `budget.min_delta` |
| `uv venv --python 3.12 失败` | 本机没有该版本且拉不下来 | 看 stderr；网络通的话 uv 会自动下载 |

## 谁做什么

真实任务通常不是一个人手写全部文件：协调层（人 + agent）填 `manifest.yaml`、把产物契约与基线策略写进 `task/design.md`；人看过这两个文件后 `ai4sci sign task` 发布；然后 `ai4sci cap design` 起执行层 agent 在只放行 `harness/` `code/` 的会话里写基线与评测草稿，框架替你加执行位、写 SHA256SUMS、跑 lint 与校验；协调 agent 把 `evaluate.py` 和 design.md 的「怎么算好」逐条对过，再跑第 4 节的后两条命令。分工与理由见外层纲领 `docs/architecture/packs.md` §2，协调层的操作步骤见 `coordinator/README.md` 固定流之二。第一个真任务 `workspaces/boehm-nll/` 就是这么接进来的，它的 `design.md` 是样本。
