<h1 align="center">tju-ai4science-platform</h1>

<p align="center">TJU AI for Science · 生产代码仓</p>

## 这是什么

科研全自动化平台的生产代码。四层：协调层（人 + agent）做科研判断，框架是诚实执行的基底，执行层 coding agent CLI 是唯一执行者，工具是确定性脚本。纲领、spec 与决策记录在外层协作仓 [`tju-ai4science`](https://github.com/zephyr4123/TJU-AI4Science) 的 `docs/`，本仓由它的 `./repos clone all` 拉到 `platform/` 目录下。

## 目录

```
platform/
├── coordinator/   两位助理的指南：README.md 主页面的研究助理、studio.md 编辑台的流程助理（执行层不加载）
├── framework/     框架：契约、工作区、能力、ai4sci CLI、页面后端；零模型调用
│   ├── cli/           一个子命令一个模块
│   ├── capabilities/  一个能力一个子包（design/ 评分脚本与基线、auto_research/ 自动实验、analysis/ 分析初稿、verify/ 数字核对），互不 import，各带五栏描述符
│   ├── chat/          两位助理的对话、看板读盘、HTTP + SSE 服务
│   ├── experiment/    实验这一族能力私下的约定：scoring.yaml 与三份 schema、env 与 uv venv、预检、账本、笔记、结果
│   ├── executor/      组 prompt（通用段：领域约定、skill 清单、联网）、起执行层会话、留档日志
│   ├── workspace/     项目与工作区的磁盘：项目、根、产出目录（跨工作区引用）、流程的进度、后台作业、删
│   ├── skills/        skill 库的读取点：扫两处库、校验 SKILL.md 与脚本、拼清单、uv run 起脚本
│   └── contracts/     框架认的东西：阶段表、需求与确认、产出与签字、流程文件、能力描述符
├── backends/      agent 适配器：claude_code.py、codex.py（执行层 + 协调层 + 自检各一份）
├── compute/       算力适配器：local.py 本机、ssh.py 一台能 ssh 上去的 Linux（按人的清单 ~/.config/ai4sci/computes.yaml 选，P-23）
├── tools/         确定性脚本
├── domains/       领域包，按工具链命名（generic/ 兜底、petab/ 参数估计）；prompts/ 随实验快照进执行层提示，skills/ 进执行层的 skill 清单
├── skills/        skill 库（纲领 P-22）：一个目录一个，agentskills.io 格式；pdf/ 解析论文
├── workflows/     流程库：阶段 + 断点的走法，编辑台改；工作区取实例
├── templates/     需求模板库：generic.md 通用，ai.md / cs.md / materials.md 按学科加
├── projects/      一个项目一位助理（P-15 改）：<p>/{project.md, materials/, .ai4sci/chats/, workspaces/<id>/{requirement.md, requirement.lock, materials/, flows/, <七个阶段>/<n>/, .ai4sci/}}；样例三个单工作区项目 mlp-regression 玩具、boehm-nll、rahman-nll
├── studio/        编辑台的对话，不进 git
├── docs/          start-a-workspace.md：接一个课题；add-a-capability.md：接一个能力；add-a-skill.md：接一个 skill
├── tests/         框架测试
├── Makefile       check / venv / lock / skills / package / release
└── CHANGELOG.md
```

工作区的根是需求（纲领 P-19）：`requirement.md` 由人和助理对话后由助理按模板写，人确认（`requirement.lock`）之后阶段才开工，这是框架唯一内置的门。七个阶段各一个目录，每次执行一个编号子目录 `<stage>/<n>/`，`meta.yaml` 记它读了哪几次产出（`from`，带 sha256）；被下游引用或人签过字的产出就冻结。断点由拼流程的人定：一个断点 = 上一项的产出要人签字下游才能读，零个断点就是全自动。

命令行上：`cap` 能力（agent 调用的 tool，纯函数：`--from STAGE/N` 点名读什么，`--flow` 挂到哪条流程，`--detach` 起成后台作业）、`requirement confirm` 确认需求、`sign STAGE/N` 给产出签字、`output new` 不经能力开一次产出、`show` 查询、`flow take` 取流程、`job stop` 停作业、`env resolve` 按包名（或上游的 requirements.txt）算环境清单 / `env use` 用机器上现成的环境、`compute add / check / list / remove / default` 接机器、`skill list / show / run` 工具包、`project new / remove`、`workspace new / remove`、`chat new / send / list / remove`、`output remove`、`flow remove`、`workflow remove`（删人产生的东西：级联到根——产出只删叶子、工作区连对话在 CLI 那边的会话与每台机器上的镜像一起清；出厂的能力、流程、模板不能删）、`serve` 入口。命令不带路径：助理站在项目里，工作区级的命令带 `--ws <名字>`，`show project` 是它的全局视角；人在终端 cd 进 `projects/<p>/workspaces/<id>/`，CLI 往上找 `requirement.md`（纲领 P-15）。同一项目里兄弟工作区的产出写 `--from <工作区>:<stage>/<n>`。两位助理分权（P-16）：主页面的研究助理只用流程，编辑台的流程助理只造流程。依赖只许自上而下：`cli → capabilities → chat → experiment → executor → workspace → skills → contracts`；`backends/` 与 `compute/` 是端口，framework 用它们、它们不认识 framework。这条规矩由 `tests/test_layering.py` 用 ast 逐条查。

## 怎么跑

```bash
make venv                                   # 建 .venv，按 requirements.lock 装依赖（含 uv）
make skills                                 # skill 门禁与预热：每个脚本按锁文件建好环境（唯一联网的一步，make check 也会跑）
make check                                  # 门禁：CHANGELOG 校验 + ruff + skills + pytest + 页面
cd projects/mlp-regression && ../../.venv/bin/ai4sci show project     # 这个项目：每个工作区一行——需求状态、流程走到哪、在等谁
AI4SCI_LIVE=1 make test                     # 连真 CLI 的冒烟测试，会花钱，CI 不跑
AI4SCI_LIVE_SSH=<名字> make test             # 连清单里那台真机器的算力测试（探测、起任务、远端建 venv 跑基线与一轮），CI 不跑
```

科研分七个阶段（文献、假设、设计、实验、分析、写作、验证，纲领 P-18）：每个阶段里几个能力，一条流程是经过几个阶段、每个阶段挂哪些能力、阶段之间哪儿要停下来等人签字（断点）。出厂的 `research` 流程：设计 → 断点 → 实验 → 分析 → 验证 → 断点。样例工作区已确认需求、已有 `design/1`，由协调层手工串（框架不连跑，见 `coordinator/README.md`；下面省略 `.venv/bin/` 前缀）：

```bash
cd projects/mlp-regression/workspaces/mlp-regression          # 人在终端：cd 进工作区就不用 --ws
ai4sci flow take research                                  # 把库里的流程取成这个工作区的实例 flows/research.yaml
ai4sci sign design/1 --note "评分脚本算的是我要的数"          # 断点：人签字，下游才能读它
ai4sci cap auto-research --from design/1 --max-iters 5 --detach   # 开 experiment/1、一轮一轮改；后台作业，show job 看进度
ai4sci cap analysis --from experiment/1                    # 执行层写 analysis/1/analysis.md
ai4sci cap verify --from analysis/1                        # 零模型核对数字，退出码就是 PASS / FAIL
ai4sci show caps                                           # 七个研究阶段、每个阶段的能力与五栏；show workflows 列流程经过哪几个阶段
```

助理与执行层各用哪家 coding agent（Claude Code、Codex，可以不同）、每家新对话用的模型与思考深度，是使用者自己的设置（纲领 P-25 底座归人）：按人的 `~/.config/ai4sci/agents.yaml`，与算力清单并列，`ai4sci agent list | check <名字> | use <名字> --for chat|executor --model --effort` 维护，页面「设置」是同一份。`check` 四句人话：装了没、版本够不够、登录了没、能不能说话；`ai4sci check` 把底座、算力、存放一起查一遍，一项不过退出码非零。旋钮上只有具体值：开新对话把设置里的值抄进这段对话，`ai4sci chat send --model --effort` 或页面输入框随时换、记进那段对话，改设置只影响之后开的对话。Codex 用 ChatGPT 账号登录（`codex login`），订阅报不出美元，成本记 NaN、token 用量在事件里。超时与额度仍走环境变量：`AI4SCI_EXECUTOR_TIMEOUT_S`、`AI4SCI_COORDINATOR_TIMEOUT_S` / `_MAX_TURNS` / `_MAX_BUDGET_USD`。

课题跑在自己的环境里：`cap design` 把 `materials/env/` 带进设计那包，`cap auto-research` 开实验时按它建 `experiment/<n>/.venv`，harness 只经 `$AI4SCI_PYTHON` 起解释器，平台 venv 一个包不多装。接一个新课题看 [`docs/start-a-workspace.md`](docs/start-a-workspace.md)。往平台里加一个能力看 [`docs/add-a-capability.md`](docs/add-a-capability.md)：文件名按阶段定、不按能力定，谁产的记在 meta。

## 版本与发布

1. 改动合并时把条目写进 `CHANGELOG.md` 的 Unreleased。
2. `make release VERSION=0.2.0`：轮转 CHANGELOG、提交、打 tag，不 push。
3. 推 tag 触发 GitHub Release，0.x 自动标 pre-release。
