# TJU AI for Science · platform（生产代码仓）

给 agent 与新成员的约定。本仓是内仓：外层协作仓 `tju-ai4science` 把它 clone 到 `platform/` 目录下，外层对它的 git 完全不知情。架构纲领与 spec 在外层 `docs/`，这里只写规矩。

## 目录（按纲领四层）

| 目录 | 放什么 |
|---|---|
| `coordinator/` | 协调层入口指南：怎么当科研助理、怎么驱动框架跑固定流、怎么拼一条自己的流并存进 `workflows/`。人在终端当协调层时由 CLI 读进来；服务起的协调会话由 `framework/chat/guide.py` 塞进 system prompt；执行层会话不许加载 |
| `framework/` | 框架：能力、runner、契约 schema、验证、裁判、`ai4sci` CLI。零模型调用，不随任务改 |
| `backends/` | agent 适配器：一个 coding agent CLI 一个文件；两个端口都定义在 `backends/__init__.py`：`Runner`（执行层，一次会话）与 `Chat`（协调层，多轮续接、事件流；起会话时把本 venv 的 bin 追加进 PATH、关后台、Bash 超时对齐本轮）。换一家 CLI 就是加一个文件，主人红线：涉及 agent 的一律可替换 |
| `compute/` | 算力适配器：一个后端一个文件；端口 `Compute` 定义在 `compute/__init__.py` |
| `tools/` | 确定性脚本：文献 API、引用校验、出图、harness 基类 |
| `domains/` | 领域包，按工具链命名，一个领域一个目录；`generic/` 兜底、`petab/` 参数估计；`prompts/<能力>.md` 与 `skills/*/SKILL.md` 由 `cap start` 快照进 run、随执行层提示的「领域约定」段注入（执行层的隔离参数关掉了 CLI 原生 skill 加载） |
| `tasks/` | 任务包，一个任务一个目录，骨架由 `ai4sci cap init` 铺（材料整棵搬进 `data/`、`env/` 两个文件、manifest 与 design.md 是带说明的模板，「待填」没换完发布键不签）：`manifest.yaml`（`format_version` 必填）`design.md`（产物契约与「怎么算好」）`publish.json`（发布记录：`ai4sci sign task` 签前两个文件；`cap design` `cap baseline` `cap start` 没它不开，改了要重发）`env/`（python-version + requirements.lock）`harness/` `code/` `data/` `run_0/`；框架起 harness 时保证给 `AI4SCI_PYTHON` `AI4SCI_BUDGET_S` `AI4SCI_INNER_K`（后者来自 `budget.inner_k`），harness 给它们写默认值过不了 `task validate`；`.venv/` 与 `run_0/` 都由 `ai4sci cap baseline` 建与跑（跑完预检：门与 `metrics[].attainable` 尽头值），都不进 git |
| `workflows/` | 预装的工作流，一个一个 YAML（`name` / `title` / `summary` / `assumes` / `steps`，步骤是能力 `cap`、人按的键 `key`、或纯人的事）。工作流是拼法不是平台：平台是能力清单，协调 agent 可以照着走也可以自己拼。`ai4sci show workflows` 与 `GET /workflows` 读它，能力步骤按吃吐文件核对通不通；覆盖哪几个阶段（`covers`）、有实验没验证的提醒（`remarks`）、每颗能力用在哪几条流（`used_by`）都是从文件算出来的，文件里不写 |
| `ui/` | 界面层，一种界面一个目录，全是 `ai4sci serve` 端点的客户端（`ui/README.md` 写契约）：`web/` 网页（React 19 + Tailwind v4 + shadcn，Vite 构建到 `web/dist`，`serve` 缺省端它；依赖只进 `web/node_modules`，`make ui` 构建、`make ui-check` 门禁），`tui/` 留位置。需求看板的**发布**与结果看板的**验收**两颗键在页面上，是"只有人能按"的唯一保证 |
| `docs/` | 面向接任务的人的指南 |
| `runs/` | 运行产物，不进 git；每个 run 自带 `.venv/` |
| `tests/` | 框架测试；单测跟着模块走 |

依赖只指向一个方向：`framework/` → `backends/`、`compute/`、`tools/`；适配器只 import 自己包根的端口定义，不 import `framework/`。任何目录都不依赖外层仓的路径。

### `framework/` 的子包

按概念分包，依赖**只许自上而下**（`cli → capabilities → chat → executor → memory → run → contracts`），同层与包内随意：

| 子包 | 放什么 | 可以 import |
|---|---|---|
| `cli/` | 命令行上就四类东西，一类一个模块：`cap` 能力（子命令从描述符生成：位置参数按 level，`creates_target` 的目标可以还不存在，`--backend` / `--compute` 按需要，每个 Param 一个选项，bool 是开关）、`sign` 键（`task` 发布、`run` 验收，人按）、`show` 查询（`tasks` / `task` / `run` / `caps` 按七个阶段列、空阶段也列 / `workflows` / `flow`，只读，与 serve 的 GET 同一批函数）、`chat` / `serve` 入口（`serve` 唯一常驻，`--ui` 指定页面构建目录）；`__init__` 装配 parser 并导出 `main` | 下面全部 |
| `capabilities/` | 一个能力一个子包，互不 import，每个导出 `DESCRIPTOR` 与 `run(run_dir, ports, **params)`（task 级是 `run(task_dir, ports, ...)`），`discover()` 扫目录并按 level 断言签名，扫完再断言整份清单：同级别里没有两颗能力声明同一个输出路径、每个输入路径是种子或同级能力的输出（纲领 P-13 文档即接口：文件名就是接口，run 级产物放 `<能力名>/` 下）；task 级：`init/` 起任务包（搬材料、放模板，唯一一颗自己建目标目录的）、`design/` 接任务（薄壳，干活的在 executor）、`baseline/` 跑基线 + 预检、`start/` 开一次实验（`run/lifecycle.new_run` 的薄壳，任务段到 run 段的桥，`contracts.flow` 认这个名字）；run 级：`experiment/` 实验内环（`loop` / `judge` / `gate` / `failures` / `prompt.md`）、`analysis/` 分析（`analyze` + `prompt.md`）、`verify/` 验证（`checks` 零模型） | executor、memory、run、contracts |
| `chat/` | 协调 agent 的对话与页面后端：`guide` 把 `coordinator/README.md` 加前言塞进 system prompt（可写目录 tasks/ runs/ workflows/，Bash 只放行裸 `ai4sci`，红线 10）、`conversation` 建对话 / 发一轮 / 落盘 `runs/chats/<id>/`（meta、每轮 message 与原生事件流、transcript、忙锁、`read_turns` / `title` 读回结构）、`boards` 三张看板读盘（任务包的阶段与钥匙、预检；run 的 best、账本、分析、验证、验收；NaN 出门前换 None）、`server` 标准库 HTTP + SSE（端点清单在文件头；`/stages` 直接读契约，`/cap` `/workflows` `/flow/check` 由 cli 以函数传入；不是接口前缀的 GET 路径端 `ui_dir` 的静态文件，单页应用回 index.html） | memory、run、contracts |
| `executor/` | 组 prompt（`prompting`）、起执行层会话并留档日志（`session`）、接任务的设计步骤（`design` + `design_prompt.md`：执行层写 harness 与基线草稿，框架封 harness、ruff、校验；能力 `capabilities/design` 是它的薄壳） | memory、run、contracts |
| `memory/` | 账本 `ledger`、实验笔记 `notebook`；项目级记忆以后加在这 | run、contracts |
| `run/` | 一个 run 的磁盘状态：`layout` 路径、`checkpoint`、`context` 只读上下文、`lifecycle` 建 run / 续命 / 能力目录轮转、`gitwork`、`artifacts` 结果索引、`accept` 验收记录（`accept.json` 签 best 与验证结论，best 变了记录就 stale；与 `contracts.publish` 对称，放这层因为它读 checkpoint） | contracts |
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
10. 协调 agent 面前只有 `ai4sci` 一个入口（纲领 P-14 CLI 主导封装）：白名单只有 `Bash(ai4sci *)`，配置（模型、预算、超时）归起服务的人的环境变量、命令上不带；指南里每条命令以 `ai4sci ` 开头、不带路径不挂前缀不接管道（`test_chat_guide` 守着）。agent 需要而没有的动作是平台缺口：加按钮，不放行裸命令。

## 版本与发布

- 从 0.1.0 起步，0.x 不承诺兼容；正式发布才进入 1.0.0。tag 形如 `vX.Y.Z`，内测 `-rc.N`。
- 推送 tag 触发 `release.yml`：对账 CHANGELOG → `make check` → `make package` → 建 Release 并附包，0.x 自动标 pre-release。
- commit message 用中文，技术名词保留英文；一个逻辑单元一个 commit。
