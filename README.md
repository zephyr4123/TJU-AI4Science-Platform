<h1 align="center">tju-ai4science-platform</h1>

<p align="center">TJU AI for Science · 生产代码仓</p>

## 这是什么

科研全自动化平台的生产代码。四层：协调层（人 + agent）做科研判断，框架是诚实执行的基底，执行层 coding agent CLI 是唯一执行者，工具是确定性脚本。纲领、spec 与决策记录在外层协作仓 [`tju-ai4science`](https://github.com/zephyr4123/TJU-AI4Science) 的 `docs/`，本仓由它的 `./repos clone all` 拉到 `platform/` 目录下。

## 目录

```
platform/
├── coordinator/   两位助理的指南：README.md 主页面的研究助理、studio.md 编辑台的造流助理（执行层不加载）
├── framework/     框架：契约、工作区、能力、ai4sci CLI、页面后端；零模型调用
│   ├── cli/           一个子命令一个模块
│   ├── capabilities/  一个能力一个子包（design/ 评分脚本与基线、auto_research/ 自动实验、analysis/ 分析初稿、verify/ 数字核对），互不 import，各带五栏描述符
│   ├── chat/          两位助理的对话、看板读盘、HTTP + SSE 服务
│   ├── experiment/    实验这一族能力私下的约定：scoring.yaml 与三份 schema、env 与 uv venv、预检、账本、笔记、结果
│   ├── executor/      组 prompt、起执行层会话、留档日志
│   ├── workspace/     工作区的磁盘：根、产出目录、流的进度、后台作业
│   └── contracts/     框架认的东西：阶段表、需求与确认、产出与签字、工作流文件、能力描述符
├── backends/      执行层适配器：claude_code.py …
├── compute/       算力适配器：local.py …
├── tools/         确定性脚本
├── domains/       领域包，按工具链命名（generic/ 兜底、petab/ 参数估计）；prompts/ 与 skills/ 随实验快照进执行层提示
├── workflows/     工作流库：阶段 + 断点的走法，编辑台改；工作区取实例
├── templates/     需求模板库：generic.md 通用，ai.md / cs.md / materials.md 按学科加
├── workspaces/    一个工作区一个课题：<id>/{requirement.md, requirement.lock, materials/, flows/, <七个阶段>/<n>/, .ai4sci/}；样例 mlp-regression 玩具、boehm-nll、rahman-nll
├── studio/        编辑台的对话，不进 git
├── docs/          start-a-workspace.md：接一个课题
├── tests/         框架测试
├── Makefile       check / venv / lock / package / release
└── CHANGELOG.md
```

工作区的根是需求（纲领 P-19）：`requirement.md` 由人和助理对话后由助理按模板写，人确认（`requirement.lock`）之后阶段才开工，这是框架唯一内置的门。七个阶段各一个目录，每次执行一个编号子目录 `<stage>/<n>/`，`meta.yaml` 记它读了哪几次产出（`from`，带 sha256）；被下游引用或人签过字的产出就冻结。断点由拼流的人定：一个断点 = 上一项的产出要人签字下游才能读，零个断点就是全自动。

命令行上：`cap` 能力（agent 调用的 tool，纯函数：`--from STAGE/N` 点名读什么，`--flow` 挂到哪条流，`--detach` 起成后台作业）、`requirement confirm` 确认需求、`sign STAGE/N` 给产出签字、`output new` 不经能力开一次产出、`show` 查询、`flow take` 取流、`workspace` / `chat` / `serve` 入口。命令不带工作区路径：cd 进 `workspaces/<id>/`，CLI 往上找 `requirement.md`（纲领 P-15）。两位助理分权（P-16）：主页面的研究助理只用流，编辑台的造流助理只造流。依赖只许自上而下：`cli → capabilities → chat → experiment → executor → workspace → contracts`；`backends/` 与 `compute/` 是端口，framework 用它们、它们不认识 framework。这条规矩由 `tests/test_layering.py` 用 ast 逐条查。

## 怎么跑

```bash
make venv                                   # 建 .venv，按 requirements.lock 装依赖（含 uv）
make check                                  # 门禁：CHANGELOG 校验 + ruff + pytest + 页面
cd workspaces/mlp-regression && ../../.venv/bin/ai4sci show workspace   # 这个工作区：需求状态、七个阶段各有什么、流走到哪
AI4SCI_LIVE=1 make test                     # 连真 CLI 的冒烟测试，会花钱，CI 不跑
```

科研分七个阶段（文献、假设、设计、实验、分析、写作、验证，纲领 P-18）：每个阶段里几颗能力，一条流是经过几个阶段、每个阶段挂哪些能力、阶段之间哪儿要停下来等人签字（断点）。出厂的 `research` 流：设计 → 断点 → 实验 → 分析 → 验证 → 断点。样例工作区已确认需求、已有 `design/1`，由协调层手工串（框架不连跑，见 `coordinator/README.md`；下面省略 `.venv/bin/` 前缀）：

```bash
cd workspaces/mlp-regression
ai4sci flow take research                                  # 把库里的流取成这个工作区的实例 flows/research.yaml
ai4sci sign design/1 --note "评分脚本算的是我要的数"          # 断点：人签字，下游才能读它
ai4sci cap auto-research --from design/1 --max-iters 5 --detach   # 开 experiment/1、一轮一轮改；后台作业，show job 看进度
ai4sci cap analysis --from experiment/1                    # 执行层写 analysis/1/analysis.md
ai4sci cap verify --from analysis/1                        # 零模型核对数字，退出码就是 PASS / FAIL
ai4sci show caps                                           # 七个研究阶段、每个阶段的能力与五栏；show workflows 列流经过哪几个阶段
```

执行层用哪个模型、超时多久走环境变量：`AI4SCI_EXECUTOR_MODEL=sonnet`、`AI4SCI_EXECUTOR_TIMEOUT_S=600`；协调层同理 `AI4SCI_COORDINATOR_MODEL` / `_EFFORT`（思考深度 low / medium / high / xhigh / max）/ `_TIMEOUT_S` / `_MAX_BUDGET_USD`。这些是起 `ai4sci serve` 或 `ai4sci chat` 的人在环境里配的缺省，协调 agent 敲的命令上不带（纲领 P-14：它面前只有裸 `ai4sci`）；人在页面的输入框上或 `ai4sci chat new|send --model --effort` 随时换，选了记进那段对话（`GET /backends` 列出每家后端有哪些可选）。

课题跑在自己的环境里：`cap design` 把 `materials/env/` 带进设计那包，`cap auto-research` 开实验时按它建 `experiment/<n>/.venv`，harness 只经 `$AI4SCI_PYTHON` 起解释器，平台 venv 一个包不多装。接一个新课题看 [`docs/start-a-workspace.md`](docs/start-a-workspace.md)。

## 版本与发布

1. 改动合并时把条目写进 `CHANGELOG.md` 的 Unreleased。
2. `make release VERSION=0.2.0`：轮转 CHANGELOG、提交、打 tag，不 push。
3. 推 tag 触发 GitHub Release，0.x 自动标 pre-release。
