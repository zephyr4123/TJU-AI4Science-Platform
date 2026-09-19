# 接一个课题

把你手里"一段能跑的代码 + 一个越小（或越大）越好的数"接进平台，让实验内环替你调。读完照做，不用问人。验收标准就是这句：**换一个人、换一个课题，照这份文档接进来就能跑。** 卡在哪一步，就是这份文档的 bug，请开 issue。

大多数人不用读这份：在页面上新建工作区、跟研究助理说清要解决什么、确认需求，剩下的它照流程做。这份是给在终端里当协调层的人、和想知道磁盘上到底发生了什么的人。

## 你要先有

1. 一段能在**几分钟内**跑完一次的代码，单入口（一个脚本、一条命令）。
2. 一个**标量指标**，方向明确：越小越好或越大越好。
3. 数据，如果代码要读的话。

评分脚本（`harness/evaluate.py`，整套机制里唯一不许 AI 碰的东西）不用你写：设计能力起执行层照需求写，人核对。

## 目录

一个工作区一个课题（纲领 P-15 P-19）。`ai4sci workspace new <id> --title <标题> --template <模板>`，或页面上「新建」：

```
workspaces/<id>/
├── requirement.md       需求：课题的根。按模板起草，人和助理对话后由助理写
├── requirement.lock     确认记录：人确认后才有；是框架唯一内置的门
├── materials/           原件：你给的数据、代码；只追加
│   └── env/             python-version + requirements.lock（你环境的 pip freeze）
├── flows/               流程实例：从库里取来的走法，改参数在这儿改
├── literature/          七个阶段各一个目录，每次执行一个编号子目录 <stage>/<n>/
├── hypothesis/
├── design/              design/1/：scoring.yaml、harness/、code/、data/、env/、baseline/
├── experiment/          experiment/1/：work/、ledger.tsv、notebook.md、iters/、checkpoint.json
├── analysis/            analysis/1/analysis.md
├── writing/
├── verification/        verification/1/report.json
└── .ai4sci/             平台记录：chats/ jobs/ logs/ requirement/v<n>.md
```

`<id>` 只用小写字母、数字、连字符。每次产出目录里 `meta.yaml` 记它读了谁（`from`，带 sha256）、挂在哪条流程第几步；`signed.json` 是人签字的记录。被下游引用或签过字的产出就冻结，改了 hash 对不上，下游拒开工。

## 1. 需求

`requirement.md` 一级标题是课题名，二级标题是节，节里「待填」页面显示成空格。模板在 `templates/`（`ai4sci show templates` 列，`show template <name>` 看原文），通用一份、按学科加，**没有规定必须有哪些节**。实验类课题至少要说清：要优化什么数、方向、数据在哪、一次跑多久、比基线好多少才算数（统计门）、什么时候停。

写好了确认：

```bash
cd workspaces/<id>
ai4sci requirement confirm --by <你>     # 写 requirement.lock，存档 .ai4sci/requirement/v1.md
```

确认之后再改文件，页面显示改了几行、未确认；确认下一版就是再跑一次这条命令。没确认，任何能力都不开。

## 2. materials/

代码与数据整棵放进去，`env/` 两个文件：

```
materials/env/python-version      3.14
materials/env/requirements.lock   numpy==2.5.3
                                  scipy==1.18.1
```

- 版本必须钉死（`==`），`>=`、URL、`-e` 一律不收。
- 平台用 [uv](https://docs.astral.sh/uv/) 找或拉这个版本的解释器、按 lock 建 venv；你的依赖不会装进平台的环境，平台的也不会混进你的。
- 拿到精确版本最省事的办法：先在任何地方装好，`pip freeze` 抄过来。

## 3. 设计：评分脚本与基线

```bash
ai4sci cap design                 # 执行层照需求写 scoring.yaml、harness/、code/；框架封 harness、跑基线出 baseline/、预检
ai4sci show output design/1       # 记录、文件清单
```

`design/1/` 就是实验这一族能力私下的那包东西（框架不认它，只有实验族的能力读）：

| 文件 | 是什么 |
|---|---|
| `scoring.yaml` | 评分契约：指标名与方向、预算（一次跑多久、最多几轮、重复几次、统计门）、可选 `attainable` 尽头值 |
| `harness/` | 评分脚本，封好后 hash 锁定：`launcher.sh` 唯一入口（清产物 → 跑 code/ → 跑 evaluate.py）、`evaluate.py` 读产物写 results.json、`make_run0.sh` 跑出基线 + 重复 + σ、`SHA256SUMS` |
| `code/` | 基线代码：AI 唯一能改的地方 |
| `data/` `env/` | 从 materials/ 搬来的 |
| `baseline/` | 基线成绩 + 重复 + `sigma.json`：改进率的分母、统计门的基线 |

harness 三条硬规矩，`experiment/pack.py` 都会查：

1. **Python 只经 `"$AI4SCI_PYTHON"` 起。** 框架跑 harness 时把这次实验 venv 的解释器放进这个变量；脚本里出现裸 `python` / `python3` 直接判不合法。框架同时保证给 `AI4SCI_BUDGET_S`（一次跑的墙钟预算，等于 `wall_clock_s`）和 `AI4SCI_INNER_K`（评分内部重复次数，等于 `budget.inner_k`）：脚本用 `"${AI4SCI_INNER_K:?}"` 这种写法拿，拿不到就停；**给这几个变量写默认值判不合法**（`os.environ.get("AI4SCI_INNER_K", 5)` 会算出一份看着合法的假成绩）。`AI4SCI_SEED` 缺省 42 是唯一允许的默认值。
2. **`evaluate.py` 只读产物文件**，算完写 `results.json`，形状固定：
   ```json
   {"metrics": {"val_mse": 0.0231}, "elapsed_s": 0.27, "seed": 42, "status": "ok"}
   ```
   产物缺失、长度不对、NaN：打一句话到 stderr，`SystemExit(非零)`，**不写 results.json**。没有 results.json 就是没有成绩，这是防假成功的最后一道。
3. **`SHA256SUMS` 与磁盘一致。** 封好之后谁都不许改 harness；评分脚本算得不对就带意见让执行层改第二版：`ai4sci cap design --continue design/1 --feedback "…"`。

预检退 1 说"无解"是门太高或题太浅（`scoring.yaml` 主指标可写 `attainable` 尽头值），改需求或松门，别硬跑。

**人核对**：`evaluate.py` 算的是不是你要的数、`baseline/` 的成绩合不合常识。流程里这儿是断点，签了下游才能读：

```bash
ai4sci sign design/1 --by <你> --note "评分脚本算的是我要的数"
```

## 4. 跑起来

```bash
ai4sci flow take research                                          # 库里的流程取成实例 flows/research.yaml（只有一条流程时命令上不用写 --flow）
ai4sci cap auto-research --from design/1 --max-iters 5 --detach    # 开 experiment/1，一轮一轮改；后台作业
ai4sci show job <id>                                               # 进度；跑完框架叫醒对话
ai4sci cap auto-research --continue experiment/1 --max-iters 10    # 接着同一次实验再跑
ai4sci cap analysis --from experiment/1                            # analysis/1/analysis.md
ai4sci cap verify --from analysis/1                                # verification/1/report.json，退出码就是 PASS / FAIL
ai4sci sign verification/1 --by <你>                               # 断点：验收
```

`cap auto-research` 开实验时按 `design/1/env/` 建 `experiment/1/.venv`、把那包搬进 `work/` 起一个 git 仓，之后不再回头看设计目录。哪次产出喂给谁是你（或助理）看着磁盘定的：`--from` 可以点名多次产出（分析多次实验），没有「缺省读最新」。

## 常见报错

| stderr | 意思 | 怎么办 |
|---|---|---|
| `需求还没确认` / `需求 v1 确认之后又改过` | 没有 requirement.lock，或改过没确认 | `ai4sci requirement confirm` |
| `design/1 被引用或签字之后改过了` | 签过字或被引用的产出目录变了 | 别改它；在它的阶段下新开一次产出，下游 `--from` 新的那个 |
| `流 research 在 design/1 之后有断点` | 流程里这儿要人签了下游才能读 | `ai4sci sign design/1` |
| `工作区有几条流程，说清照哪条` | flows/ 下不止一个实例 | 命令加 `--flow <name>` |
| `env/: 目录缺失` | materials/ 没带环境 | 建 `materials/env/` 两个文件，零依赖也要有空的 lock |
| `harness/launcher.sh:12: 裸调 python` | launcher 用了 PATH 上的 python | 让执行层改：`--continue design/1 --feedback` |
| `harness/evaluate.py:45: 给 AI4SCI_INNER_K 写了默认值` | 评分脚本拿不到框架保证的变量时自己兜底 | 同上 |
| `requirements.lock:3: 期望钉死的 name==version` | 依赖没钉版本 | 写成 `name==x.y.z` |
| `baseline/repeats/: 期望恰好 budget.repeat_k=3 个` | 重复次数与 scoring.yaml 不符 | 同上 |
| `统计门是 0` | 重复跑完全一致（σ=0） | scoring.yaml 加 `budget.min_delta` |
| `uv venv --python 3.12 失败` | 本机没有该版本且拉不下来 | 看 stderr；网络通的话 uv 会自动下载 |

## 谁做什么

研究者：说清课题、给材料、确认需求、核对评分脚本、验收。研究助理（页面上的那位）：写需求、取流程、按流程调用能力、看着磁盘决定下一步喂什么、停下来等人签。执行层（能力起的会话）：只在自己那次产出目录里写。框架：开门（需求确认）、开产出目录、封 harness、跑打分、记账本、判冻结与签字。协调层的操作步骤见 `coordinator/README.md`。第一个真课题 `workspaces/boehm-nll/` 就是这么接进来的，它的 `requirement.md` 是样本。
