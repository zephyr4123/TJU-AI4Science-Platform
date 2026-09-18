<h1 align="center">tju-ai4science-platform</h1>

<p align="center">TJU AI for Science · 生产代码仓</p>

## 这是什么

科研全自动化平台的生产代码。四层：协调层（人 + agent）做科研判断，框架是诚实执行的基底，执行层 coding agent CLI 是唯一执行者，工具是确定性脚本。纲领、spec 与决策记录在外层协作仓 [`tju-ai4science`](https://github.com/zephyr4123/TJU-AI4Science) 的 `docs/`，本仓由它的 `./repos clone all` 拉到 `platform/` 目录下。

## 目录

```
platform/
├── coordinator/   协调层入口指南（执行层不加载）
├── framework/     框架：能力、runner、契约、验证、ai4sci CLI；零模型调用
│   ├── cli/           一个子命令一个模块
│   ├── capabilities/  一个能力一个子包（init/ 说清课题、design/ 写评分脚本跑基线、auto_research/、analysis/ 写分析初稿、verify/ 核对数字），互不 import，各带五栏描述符
│   ├── executor/      组 prompt、起执行层会话、留档日志
│   ├── memory/        账本、实验笔记
│   ├── run/           run 的布局、checkpoint、上下文、生命周期、work/ 的 git、结果索引
│   └── contracts/     schema、任务包校验、任务环境（env/ 与 uv 建 venv）、产物读取、能力描述符、analysis.md 与 report.json 契约
├── backends/      执行层适配器：claude_code.py …
├── compute/       算力适配器：local.py …
├── tools/         确定性脚本
├── domains/       领域包，按工具链命名（generic/ 兜底、petab/ 参数估计）；prompts/ 与 skills/ 随 run 快照进执行层提示
├── workflows/     工作流库：阶段 + 断点的走法，编辑台改；工作区取实例
├── workspaces/    一个工作区一份需求：<id>/{workspace.yaml, task/, flows/, chats/, runs/, jobs/}；样例 mlp-regression 玩具、boehm-nll、rahman-nll
├── studio/        编辑台的对话，不进 git
├── docs/          add-a-task.md：十分钟接一个任务
├── tests/         框架测试
├── Makefile       check / venv / lock / package / release
└── CHANGELOG.md
```

命令行上就五类东西：`cap` 能力（agent 调用的 tool）、`sign` 人的确认（发布、验收）、`show` 查询、`flow take` 取流、`workspace` / `chat` / `serve` 入口。命令不带工作区路径：cd 进 `workspaces/<id>/`，CLI 往上找 `workspace.yaml`（纲领 P-15）。两位助理分权（P-16）：主页面的研究助理只用流，编辑台的造流助理只造流。依赖只许自上而下：`cli → capabilities → chat → executor → memory → run → contracts`；`backends/` 与 `compute/` 是端口，framework 用它们、它们不认识 framework。这条规矩由 `tests/test_layering.py` 用 ast 逐条查。

## 怎么跑

```bash
make venv                                   # 建 .venv，按 requirements.lock 装依赖（含 uv）
make check                                  # 门禁：CHANGELOG 校验 + ruff + pytest
cd workspaces/mlp-regression && ../../.venv/bin/ai4sci show task   # 校验这个工作区的任务包合不合契约
AI4SCI_LIVE=1 make test                     # 连真 CLI 的冒烟测试，会花钱，CI 不跑
```

科研分七个阶段（文献、假设、设计、实验、分析、写作、验证，纲领 P-18）：每个阶段里几颗能力，一条流是经过几个阶段、每个阶段挂哪些能力、阶段之间哪儿要停下来等人确认（断点）。出厂的 `research` 流从已跑过基线的任务包起，在工作区里由协调层手工串（框架不连跑，见 `coordinator/README.md`；下面省略 `.venv/bin/` 前缀）：

```bash
cd workspaces/mlp-regression
ai4sci flow take research                                     # 把库里的流取成这个工作区的实例 flows/research.yaml
ai4sci cap auto-research --run-id demo --workflow research --max-iters 5 --detach   # 开 run、一轮一轮改；起成后台作业，show job 看进度
ai4sci cap analysis demo                            # 执行层写 analysis/analysis.md
ai4sci cap verify demo                              # 零模型核对数字，退出码就是 PASS / FAIL
ai4sci show caps                                    # 七个研究阶段、每个阶段的能力与五栏（--json 带描述符与 used_by）；show workflows 列流经过哪几个阶段
```

执行层用哪个模型、超时多久走环境变量：`AI4SCI_EXECUTOR_MODEL=sonnet`、`AI4SCI_EXECUTOR_TIMEOUT_S=600`；协调层同理 `AI4SCI_COORDINATOR_MODEL` / `_EFFORT`（思考深度 low / medium / high / xhigh / max）/ `_TIMEOUT_S` / `_MAX_BUDGET_USD`。这些是起 `ai4sci serve` 或 `ai4sci chat` 的人在环境里配的缺省，协调 agent 敲的命令上不带（纲领 P-14：它面前只有裸 `ai4sci`）；人在页面的输入框上或 `ai4sci chat new|send --model --effort` 随时换，选了记进那段对话（`GET /backends` 列出每家后端有哪些可选）。

任务跑在自己的环境里：`cap auto-research` 开 run 时按任务包的 `env/` 建 `<工作区>/runs/<id>/.venv`，harness 只经 `$AI4SCI_PYTHON` 起解释器，平台 venv 一个包不多装。接一个新任务看 [`docs/add-a-task.md`](docs/add-a-task.md)。

## 版本与发布

1. 改动合并时把条目写进 `CHANGELOG.md` 的 Unreleased。
2. `make release VERSION=0.2.0`：轮转 CHANGELOG、提交、打 tag，不 push。
3. 推 tag 触发 GitHub Release，0.x 自动标 pre-release。
