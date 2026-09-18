# TJU AI for Science · platform（生产代码仓）

给 agent 与新成员的约定。本仓是内仓：外层协作仓 `tju-ai4science` 把它 clone 到 `platform/` 目录下，外层对它的 git 完全不知情。架构纲领与 spec 在外层 `docs/`，这里只写规矩。

## 目录（按纲领四层）

| 目录 | 放什么 |
|---|---|
| `coordinator/` | 两位助理的指南（纲领 P-16）：`README.md` 主页面的研究助理——怎么当科研助理、怎么驱动框架、怎么从库里取一条流改参数照着跑，不造流；`studio.md` 编辑台的造流助理——怎么把能力拼成流存进 `workflows/`，不跑实验。人在终端当协调层时由 CLI 读进来；服务起的会话由 `framework/chat/guide.py` 按域塞进 system prompt；执行层会话不许加载 |
| `framework/` | 框架：能力、runner、契约 schema、验证、裁判、`ai4sci` CLI。零模型调用，不随任务改 |
| `backends/` | agent 适配器：一个 coding agent CLI 一个文件；两个端口都定义在 `backends/__init__.py`：`Runner`（执行层，一次会话）与 `Chat`（协调层，多轮续接、事件流；起会话时把本 venv 的 bin 追加进 PATH、关后台、Bash 超时对齐本轮、`AI4SCI_CHAT_ID` 告诉按钮自己属于哪段对话；`knobs()` 自报有哪些模型、哪几档思考深度与缺省，每轮的 `tuning` 翻成 `--model` / `--effort`，页面与终端只许从清单里选）。换一家 CLI 就是加一个文件，主人红线：涉及 agent 的一律可替换 |
| `compute/` | 算力适配器：一个后端一个文件；端口 `Compute` 定义在 `compute/__init__.py` |
| `tools/` | 确定性脚本：文献 API、引用校验、出图、harness 基类 |
| `domains/` | 领域包，按工具链命名，一个领域一个目录；`generic/` 兜底、`petab/` 参数估计；`prompts/<能力>.md` 与 `skills/*/SKILL.md` 由 `cap start` 快照进 run、随执行层提示的「领域约定」段注入（执行层的隔离参数关掉了 CLI 原生 skill 加载） |
| `workspaces/` | 一个工作区一份需求（纲领 P-15）：`workspaces/<id>/workspace.yaml` 标记、`task/` 任务包、`flows/` 流实例、`chats/` `runs/` `jobs/`。任务包骨架由 `ai4sci cap init` 铺（材料整棵搬进 `data/`、`env/` 两个文件、manifest 与 design.md 是带说明的模板，「待填」没换完发布键不签；manifest 的 `id` 等于工作区名）：`manifest.yaml`（`format_version` 必填）`design.md`（产物契约与「怎么算好」）`publish.json`（发布记录：`ai4sci sign task` 签前两个文件；`cap design` `cap baseline` `cap start` 没它不开，改了要重发）`env/`（python-version + requirements.lock）`harness/` `code/` `data/` `run_0/`；框架起 harness 时保证给 `AI4SCI_PYTHON` `AI4SCI_BUDGET_S` `AI4SCI_INNER_K`（后者来自 `budget.inner_k`），harness 给它们写默认值过不了校验；`task/.venv/` 与 `run_0/` 由 `ai4sci cap baseline` 建与跑（跑完预检：门与 `metrics[].attainable` 尽头值）。三个样例工作区（mlp-regression 玩具、boehm-nll、rahman-nll 两个真任务）只有 `task/` 与标记进 git；`runs/` `chats/` `jobs/` 不进。数据根 `AI4SCI_HOME` 缺省仓根 |
| `workflows/` | 工作流**库**：通用的拼法，不依附课题，一个一个 YAML（`name` / `title` / `summary` / `assumes` / `steps`，步骤是能力 `cap`、人按的键 `key`、或纯人的事，能力步骤可带 `with:` 参数）。编辑台的造流助理与 `POST /workflows` 改它；主页面的研究助理只读，`ai4sci flow take <name>` 复制成工作区 `flows/` 里的实例再改参数、开 run 时快照进 run（流分三层：库 → 实例 → 快照）。`ai4sci show workflows` / `show flows` / `GET /workflows` / `GET /workspaces/<id>/flows` 读它们，能力步骤按吃吐文件核对通不通；`covers` `remarks` `used_by` 都是算出来的，文件里不写 |
| `ui/` | 界面层，一种界面一个目录，全是 `ai4sci serve` 端点的客户端（`ui/README.md` 写契约）：`web/` 网页（React 19 + Tailwind v4 + shadcn，Vite 构建到 `web/dist`，`serve` 缺省端它；依赖只进 `web/node_modules`，`make ui` 构建、`make ui-check` 门禁），`tui/` 留位置。需求看板的**发布**与结果看板的**验收**两颗键在页面上，是"只有人能按"的唯一保证 |
| `docs/` | 面向接任务的人的指南 |
| `studio/` | 编辑台的对话（造流助理），不进 git；在数据根下 |
| `tests/` | 框架测试；单测跟着模块走 |

依赖只指向一个方向：`framework/` → `backends/`、`compute/`、`tools/`；适配器只 import 自己包根的端口定义，不 import `framework/`。任何目录都不依赖外层仓的路径。仓根与几个根目录（数据根 `AI4SCI_HOME`、工作流库 `AI4SCI_WORKFLOWS_ROOT`、领域包 `AI4SCI_DOMAINS_ROOT`）的读取点只在 `framework/paths.py`，各层从它拿，不各自算 `parents[n]`。

### `framework/` 的子包

按概念分包，依赖**只许自上而下**（`cli → capabilities → chat → executor → memory → run → contracts`），同层与包内随意：

| 子包 | 放什么 | 可以 import |
|---|---|---|
| `cli/` | 命令行上就五类东西，一类一个模块：`cap` 能力（子命令从描述符生成：task 级不带位置参数、动的是当前工作区的任务包，run 级带 `run_id`，`--backend` / `--compute` 按需要，每个 Param 一个选项，bool 是开关；每颗都有 `--detach`：同一条命令起成独立进程当作业，子进程跑完回写记录、属于某段对话的去叫醒；run 级能力跑成后记它落在流的第几步）、`sign` 键（`task` 发布当前工作区的需求、`run` 验收，人按）、`show` 查询（`workspaces` / `task` / `run`（含作业与便条）/ `jobs` / `job` / `flows`（工作区的流实例）/ `caps` 按七个阶段列 / `workflows`（库）/ `flow`，只读，与 serve 的 GET 同一批函数）、`flow take` 取流（库里的一条复制成工作区的实例）、`workspace new` / `chat`（`--studio` 选编辑台的造流助理）/ `serve` 入口；`_common.current_workspace` 从 cwd 往上找 `workspace.yaml`（`AI4SCI_WORKSPACE` 可指定），找不到退 2 说清怎么办；`__init__` 装配 parser 并导出 `main` | 下面全部 |
| `capabilities/` | 一个能力一个子包，互不 import，每个导出 `DESCRIPTOR` 与 `run(run_dir, ports, **params)`（task 级是 `run(workspace, ports, ...)`，动的是工作区的任务包），`discover()` 扫目录并按 level 断言签名，扫完再断言整份清单：同级别里没有两颗能力声明同一个输出路径、每个输入路径是种子或同级能力的输出（纲领 P-13 文档即接口：文件名就是接口，run 级产物放 `<能力名>/` 下）；task 级：`init/` 起任务包（建工作区的 `task/`、搬材料、放模板）、`design/` 接任务（薄壳，干活的在 executor，日志落工作区 `runs/design/`）、`baseline/` 跑基线 + 预检、`start/` 开一次实验（`run/lifecycle.new_run` 的薄壳，run 落工作区 `runs/`，`--workflow` 只认工作区 `flows/` 里的实例；任务段到 run 段的桥，`contracts.flow` 认这个名字）；run 级：`experiment/` 实验内环（`loop` / `judge` / `gate` / `failures` / `prompt.md`）、`analysis/` 分析（`analyze` + `prompt.md`）、`verify/` 验证（`checks` 零模型） | executor、memory、run、contracts |
| `chat/` | 两位助理的对话与页面后端：`scope` 定域（工作区：cwd 是工作区、可写 `task/` `flows/` `runs/`、库 `workflows/` 可读不可写（端口 `readable_paths`，适配器 `--add-dir`）、对话在工作区 `chats/`；编辑台：cwd 是库的上级、只可写 `workflows/`、对话在 `studio/chats/`），`guide` 按域把 `coordinator/README.md` 或 `studio.md` 加前言塞进 system prompt（Bash 放行 `ai4sci`，带路径的老写法也放行，指南只教裸写法，红线 10 11）、`conversation` 建对话 / 发一轮 / 落盘 `<域>/chats/<id>/`（meta、每轮 message 与原生事件流、transcript、忙锁、`read_turns` / `title` 读回结构；一轮有 `origin`：人，或框架来叫醒）、`notify` 作业跑完以「框架」身份给同一个工作区里的那段对话发一轮（忙就等，等不到记回作业）、`boards` 看板读盘（工作区一行与一整份、任务包的阶段与钥匙、预检；run 的 best、账本、分析、验证、验收；NaN 出门前换 None）、`server` 标准库 HTTP + SSE（端点清单在文件头，按 `/workspaces/<id>/…` 与 `/studio/…` 分域；`/stages` 直接读契约，`/cap` `/workflows` `/flow/check` 与工作区的流实例由 cli 以函数传入；不是接口前缀的 GET 路径端 `ui_dir` 的静态文件，单页应用回 index.html） | memory、run、contracts |
| `executor/` | 组 prompt（`prompting`）、起执行层会话并留档日志（`session`）、接任务的设计步骤（`design` + `design_prompt.md`：执行层写 harness 与基线草稿，框架封 harness、ruff、校验；能力 `capabilities/design` 是它的薄壳） | memory、run、contracts |
| `memory/` | 账本 `ledger`、实验笔记 `notebook`；项目级记忆以后加在这 | run、contracts |
| `run/` | 一个 run 的磁盘状态与它的家：`workspace` 工作区（标记、六个目录、从 cwd 往上找、起与列）、`layout` 路径、`checkpoint`、`context` 只读上下文、`lifecycle` 建 run / 续命 / 能力目录轮转、`gitwork`、`artifacts` 结果索引、`accept` 验收记录、`jobs` 后台作业（只认作业目录 `<工作区>/jobs/`：记录 + 日志，独立会话起 `framework.cli`，pid 探活判 lost）、`flow_state` 便条（`cap start --workflow` 快照那条流进 `runs/<id>/workflow/`，`flow.json` 记步序，在等谁现算）（`accept.json` 签 best 与验证结论，best 变了记录就 stale；与 `contracts.publish` 对称，放这层因为它读 checkpoint） | contracts |
| `contracts/` | `schemas/*.json`、任务包发现与校验 `packs`、发布记录 `publish`（钥匙）、接任务预检 `headroom`（门高的唯一定义）、流通不通 `flow`（桥是能力 `start`）、工作流文件 `workflows`、任务环境 `env`（读 env/、uv 建 venv）、产物读取 `results`、能力描述符与入口形状 `capability`（`STAGES` 七个科研阶段：每颗能力 `stage` 归一个，`title` / `what` 是给研究者看的人话，界面不另抄）、`analysis.md` 数据表契约 `analysis`、验证报告 `report` | 谁都不 import（framework 内） |

`backends/` 与 `compute/` 是端口：framework 任何子包都可以 import 它们，它们不许 import framework。这条与上表都由 `tests/test_layering.py` 用 ast 逐条查，不是靠人 review。

## 红线

1. 框架零模型调用：`framework/` 下 grep 不到 anthropic / openai / claude_sdk（纲领 P-1）。
2. 不吞异常：ruff 的 BLE 规则开着，裸 `except` 与不 raise 的 `except Exception` 过不了 lint（P-7）。
3. 每个抽象带真实调用点，每个配置项有读取点与断言，集成点必须有测试（P-8）。
4. 密钥与敏感配置只进环境变量或 `.env`（已 gitignore），绝不进代码；ssh 主机与密钥路径同理。
5. Python 一律走 `.venv`（`make venv`），依赖钉在 `requirements.lock`，改依赖走 `make lock`。任务的依赖不进平台 venv：任务包自带 `env/`，框架用 uv 建任务级 venv，harness 只经 `$AI4SCI_PYTHON` 起解释器（裸 `python3` 过不了 `task validate`）。
6. 每个改动合并时写进 `CHANGELOG.md` 的 Unreleased；发版只走 `make release VERSION=x.y.z`。
7. `make check` 是提交前门禁，与 CI 完全相同：changelog + ruff + pytest + 页面的 `ui-check`（tsc + oxlint + vitest + 构建）。真 CLI 冒烟测试默认 skip，`AI4SCI_LIVE=1` 才跑，CI 不跑。
8. 跨仓变更以外层仓的 GitHub issue 为锚，commit message 引用它。
9. `.claude/` 是本机会话产物，已 gitignore；不要读取或依赖其中内容。
10. 助理面前只有 `ai4sci` 一个入口（纲领 P-14 CLI 主导封装）：白名单是 `Bash(ai4sci *)`（带 `.venv/bin/` 的老写法也放行，前期别设坎），配置（模型、预算、超时、目录）归起服务的人的环境变量、命令上不带，命令也不带工作区路径（P-15：cwd 就是工作区）；两份指南里每条命令以 `ai4sci ` 开头、不带路径不挂前缀不接管道（`test_chat_guide` 守着）。agent 需要而没有的动作是平台缺口：加能力，不放行裸命令。给研究者看的话（指南、页面、agent 的回话）不用「按钮」「能力单元」这类内部词，每条命令翻成一句直白话。
11. 造流与用流分权（纲领 P-16）：主页面的研究助理只能用流（`flow take` 取、改实例、照着跑），不造流、不造能力；编辑台的造流助理只写 `workflows/`，不跑实验、不碰工作区。分权靠 `chat/scope.py` 的可写目录与按域分前缀的端点，不靠指南里的一句「请不要」；研究助理的指南里没有 `workflows/<name>.yaml` 的写法（`test_chat_guide` 守着）。
12. 素材不进仓（纲领 P-17）：页面里的图片 / 视频只写自己 CDN 的 URL，且只在 `ui/web/src/assets.ts` 一处；`git ls-files ui/` 里没有 png / jpg / mp4（`make ui-check` 守着）；图标全站一套 Phosphor 内联。素材从来源站下到本机、处理好再推桶，不直接引第三方源；清单与许可记在 `docs/DESIGN.md`「素材」。

## 版本与发布

- 从 0.1.0 起步，0.x 不承诺兼容；正式发布才进入 1.0.0。tag 形如 `vX.Y.Z`，内测 `-rc.N`。
- 推送 tag 触发 `release.yml`：对账 CHANGELOG → `make check` → `make package` → 建 Release 并附包，0.x 自动标 pre-release。
- commit message 用中文，技术名词保留英文；一个逻辑单元一个 commit。
