<!-- 协调层的设计提示模板（外层 #40 走过一遍后抽出）。用法见 ../README.md「固定流之二」。
     四个占位段由协调层在起会话前填：{manifest}、{产物契约}、{skill 正文}、{参考实现}。
     第一次真用的完整版本（boehm-nll）留在 runs/design-boehm-nll/prompt.md 备查。 -->

# 任务：给一个任务包写 harness 与基线代码

你在一个科研自动化平台的**任务包目录**里工作。任务包已经有 `manifest.yaml`（任务声明）、`data/`（问题定义，PEtab 格式的九个文件）、`env/`（依赖清单，已经建成 venv）。你要写四个文件：

- `harness/launcher.sh` —— 唯一执行入口
- `harness/evaluate.py` —— 评测：读产物、算分、写 results.json
- `harness/make_run0.sh` —— 跑出基线 + 三次重复 + σ
- `code/optimize.py` —— 基线优化策略，以后由另一个 agent 逐轮改它

## 硬规矩

1. **只写 `harness/` 与 `code/` 下的文件**。不碰 `data/`、`env/`、`manifest.yaml`。不写 `harness/SHA256SUMS`（由框架生成）。
2. 你这个会话没有 Bash，不能运行代码。写完之后由框架校验、建环境、跑基线，报错会喂回给你。所以每一行都要想清楚再写，宁可简单。
3. 脚本里起 Python 只准写 `"$AI4SCI_PYTHON"`，绝不能写裸 `python` / `python3`——任务跑在自己的 venv 里，这个变量由框架或 make_run0.sh 给。
4. `evaluate.py` 是裁判：**NLL 必须由它用同一份 PEtab 问题重新算**，不许读 `code/` 自己报的分数。`code/` 只产出参数向量。
5. 拒收产物（文件缺失、长度不对、名字不对、NaN、越界）时：打一句话到 stderr，`raise SystemExit(非零)`，**不写 results.json，不抛 traceback**。
6. 注释用中文，写"为什么"，不复述代码在做什么。文件短、单入口、可调参数集中放顶上并注明含义。不写没人用的函数。

## manifest.yaml（只读，照它的指标名与预算写）

```yaml
{manifest}
```

## 产物契约

{产物契约：code/ 写什么文件、什么形状；evaluate.py 查什么、退出码怎么分；make_run0.sh 的种子与指标名。下面是 boehm-nll 的写法，换任务照改}


`code/optimize.py` 写 `params.json` 到任务根目录：

```json
{"x_names": ["<9 个自由参数名，顺序与 problem.x_free_indices 一致>"],
  "x_scaled": [<9 个浮点数，log10 尺度，都在 [lb, ub] 内>],
  "seed": 42, "n_starts": 5, "nll_reported": 213.18}
```

`nll_reported` 只是给人看的参考，harness 不读它。`code/optimize.py` 的约定：
- 种子从环境变量 `AI4SCI_SEED` 读（缺省 42），撒起点前 `np.random.seed(seed)`；同一 seed 必须复现同一结果。
- 预算从环境变量 `AI4SCI_BUDGET_S` 读（缺省 30 秒，与 manifest 的 wall_clock_s 一致），只花预算的 80%，留时间给评分。基线策略简单到不会超时，但要把预算读进来并写成可调参数，以后改策略的人要用。
- **基线策略就是最朴素的 pyPESTO 默认流程**：`n_starts = 5`、`startpoint.UniformStartpoints()`、`optimize.ScipyOptimizer()` 缺省方法。这是学长给的基线，故意留着优化空间，不要替他调好。
- 只读 `data/`，只写 `params.json`，不写 `results.json`。

`harness/evaluate.py` 读 `params.json` 与 `data/Boehm_JProteomeRes2014.yaml`，检查：文件存在且是合法 JSON（退出码 2）；`x_names` 与问题的自由参数名逐个相同、`x_scaled` 长度等于 `problem.dim`（退出码 3）；每个值是有限数且在 `[problem.lb, problem.ub]` 内（退出码 4）；算出的 NLL 是有限数（退出码 4）；墙钟拿不到（退出码 5）。通过就写：

```json
{"metrics": {"nll": <float>}, "elapsed_s": <float>, "seed": <int>, "status": "ok"}
```

`elapsed_s` 与 `seed` 的取法照参考实现：`AI4SCI_START_EPOCH` 由 launcher 设，`AI4SCI_SEED` 缺省 42。

`harness/make_run0.sh` 与参考实现同形：种子 42 43 44，指标名 `nll`，σ 用样本标准差，产物清干净。`AI4SCI_PYTHON` 缺省指到 `$TASK_DIR/.venv/bin/python`，不存在就报错退出。

## 工具链（全部在这个环境里实测过，没写的 API 不要猜）

{领域包 domains/<d>/skills/*/SKILL.md 的正文，去掉 frontmatter}

## 参考实现（另一个任务包，形状照抄，内容按本任务改）

{tasks/mlp-regression/harness/ 的 launcher.sh、evaluate.py、make_run0.sh 与 code/train.py 头部，原样贴}

## 收尾

四个文件写完后，用三行自述结束：写了哪几个文件；你不确定的地方（比如某个 API 的行为、某个边界）；建议框架校验时重点看什么。
