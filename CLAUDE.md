# TJU AI for Science · platform（生产代码仓）

给 agent 与新成员的约定。本仓是内仓：外层协作仓 `tju-ai4science` 把它 clone 到 `platform/` 目录下，外层对它的 git 完全不知情。架构纲领与 spec 在外层 `docs/`，这里只写规矩。

## 目录（按纲领四层）

| 目录 | 放什么 |
|---|---|
| `coordinator/` | 两位助理的指南（纲领 P-16）：`README.md` 主页面的研究助理——怎么当科研助理、怎么驱动框架、怎么从库里取一条流改参数照着跑，不造流；`studio.md` 编辑台的造流助理——怎么把能力拼成流存进 `workflows/`，不跑实验。人在终端当协调层时由 CLI 读进来；服务起的会话由 `framework/chat/guide.py` 按域塞进 system prompt；执行层会话不许加载 |
| `framework/` | 框架：契约、工作区、能力、`ai4sci` CLI、页面后端。零模型调用，不随课题改 |
| `backends/` | agent 适配器：一个 coding agent CLI 一个文件；两个端口都定义在 `backends/__init__.py`：`Runner`（执行层，一次会话）与 `Chat`（协调层，多轮续接、事件流；起会话时把本 venv 的 bin 追加进 PATH、关后台、Bash 超时对齐本轮、`AI4SCI_CHAT_ID` 告诉它调用的命令自己属于哪段对话；`knobs()` 自报有哪些模型、哪几档思考深度与缺省，每轮的 `tuning` 翻成 `--model` / `--effort`，页面与终端只许从清单里选）。换一家 CLI 就是加一个文件，主人红线：涉及 agent 的一律可替换 |
| `compute/` | 算力适配器：一个后端一个文件；端口 `Compute` 定义在 `compute/__init__.py` |
| `tools/` | 确定性脚本：文献 API、引用校验、出图、harness 基类 |
| `domains/` | 领域包，按工具链命名，一个领域一个目录；`generic/` 兜底、`petab/` 参数估计；`prompts/<能力>.md` 与 `skills/*/SKILL.md` 由 `cap auto-research` 开实验时快照进产出目录、随执行层提示的「领域约定」段注入（执行层的隔离参数关掉了 CLI 原生 skill 加载）。纲领 P-18 里领域包只是打包单位：里面的 skill 拆开各归各的能力 |
| `workspaces/` | 一个工作区一个课题（纲领 P-15 P-19）：`workspaces/<id>/requirement.md` 是标记也是根（需求，人和助理对话后由助理写，按 `templates/` 里的模板起草），`requirement.lock` 是确认记录（`ai4sci requirement confirm` / 页面上人确认；签 sha256，之后再改就 dirty，要确认下一版，历次原文存 `.ai4sci/requirement/v<n>.md`）；**它是框架唯一内置的门**：没确认任何能力都不开。`materials/` 原件（研究者给的数据、代码、`env/` 两个文件：python-version + requirements.lock），只追加。`flows/` 流实例。七个阶段各一个目录（`literature/ hypothesis/ design/ experiment/ analysis/ writing/ verification/`），每次执行一个编号子目录 `<stage>/<n>/`：`meta.yaml` 记 id（就是路径）、标题、谁、状态、`from`（读了哪几次产出，带 sha256）、params、挂在哪条流第几步、需求第几版；`signed.json` 是人签字的记录（签 tree hash；目录改了记录就 stale）。产出被下游 `from` 引用或签过字就冻结（hash 不对拒开工）。`.ai4sci/` 平台记录：`chats/` `jobs/` `logs/` `requirement/`。三个样例工作区（mlp-regression 玩具、boehm-nll、rahman-nll 两个真课题）进 git 的只有需求、materials/、flows/、design/；实验及之后的产出与 `.ai4sci/`（除 requirement/）不进。数据根 `AI4SCI_HOME` 缺省仓根 |
| `workflows/` | 工作流**库**：通用的走法，不依附课题，一个一个 YAML（`name` / `title` / `summary` / `stages`；一项是阶段名、`阶段: [能力]`、`阶段: {能力: 参数}`、`断点` 或 `断点: 一句话`——断点 = 上一项的产出要人签字下游才能读，几个断点、放哪由拼流的人定，零个就是全自动；可选 `layout` 是画布上每一项的坐标，人摆过才有，框架只原样存取；纲领 P-18 P-19）。编辑台的造流助理与页面的画布（`POST /workflows`）改它；主页面的研究助理只读，`ai4sci flow take <name>` 复制成工作区 `flows/` 里的实例再改参数。`ai4sci show workflows` / `show flows` / `GET /workflows` / `GET /workspaces/<id>/flows` 读它们，只查阶段名、点名的能力在不在那个阶段、参数、断点位置（阶段之间没有显式的输入输出接口、不做数据流校验）；`covers` `remarks` `used_by` 与每条实例的进度都是从磁盘算出来的，文件里不写。出厂只有一条 `research` |
| `templates/` | 需求模板的库：`generic.md` 通用一份，`ai.md` `cs.md` `materials.md` 按学科加，再加一个学科就是再放一个文件（`AI4SCI_TEMPLATES_ROOT` 可指定）。格式开放：一级标题是课题名，二级标题是节，节里「待填」页面显示成空格；框架不规定必须有哪些节。`ai4sci show templates` / `show template <name>` / `GET /templates` 读，`workspace new --template` 与页面新建时按它起草 |
| `ui/` | 界面层，一种界面一个目录，全是 `ai4sci serve` 端点的客户端（`ui/README.md` 写契约）：`web/` 网页（React 19 + Tailwind v4 + shadcn，Vite 构建到 `web/dist`，`serve` 缺省端它；依赖只进 `web/node_modules`，`make ui` 构建、`make ui-check` 门禁），`tui/` 留位置。需求的**确认**与产出的**签字**两处在页面上，是"只有人能确认"的唯一保证 |
| `docs/` | 面向接课题的人的指南 |
| `studio/` | 编辑台的对话（造流助理），不进 git；在数据根下 |
| `tests/` | 框架测试；单测跟着模块走 |

依赖只指向一个方向：`framework/` → `backends/`、`compute/`、`tools/`；适配器只 import 自己包根的端口定义，不 import `framework/`。任何目录都不依赖外层仓的路径。仓根与几个根目录（数据根 `AI4SCI_HOME`、工作流库 `AI4SCI_WORKFLOWS_ROOT`、领域包 `AI4SCI_DOMAINS_ROOT`、需求模板库 `AI4SCI_TEMPLATES_ROOT`）的读取点只在 `framework/paths.py`，各层从它拿，不各自算 `parents[n]`。

### `framework/` 的子包

按概念分包，依赖**只许自上而下**（`cli → capabilities → chat → experiment → executor → workspace → contracts`），同层与包内随意：

| 子包 | 放什么 | 可以 import |
|---|---|---|
| `cli/` | 命令行上的东西一类一个模块：`cap` 能力（agent 调用的 tool；子命令从描述符生成，每颗都是纯函数——`--from STAGE/N` 点名读哪几次产出（可多次），没有「缺省读最新」；`--flow` 挂到哪条流（工作区里只有一条时不用写；断点后的产出没签字或签了又改了就拒开工）；continuable 的能力有 `--continue STAGE/N` 接着同一次产出干；`--backend` / `--compute` 按需要，每个 Param 一个选项，bool 是开关；`--detach` 把同一条命令起成独立进程当作业，作业记录挂上产出 id，跑完回写、属于某段对话的去叫醒；驱动顺序：查需求确认 → 解析输入（在不在、成没成、冻结的 hash 对不对）→ 定流与步 → 开产出目录 → 跑 → 收尾写 meta）、`requirement confirm` 确认需求、`sign STAGE/N` 给一次产出签字、`output new <stage>` 不经能力开一次产出目录（助理自己写的东西也是产出）、`show` 查询（`workspaces` / `workspace` / `outputs` / `output` / `jobs` / `job` / `flows` / `caps` / `workflows` / `templates` / `template`，只读，与 serve 的 GET 同一批函数）、`flow take` 取流、`workspace new`（`--template`）/ `chat`（`--studio` 选编辑台的造流助理）/ `serve` 入口；`_common.current_workspace` 从 cwd 往上找 `requirement.md`（`AI4SCI_WORKSPACE` 可指定），找不到退 2 说清怎么办；`__init__` 装配 parser 并导出 `main` | 下面全部 |
| `capabilities/` | 一个能力一个子包，互不 import，每个导出 `DESCRIPTOR`（属于哪个阶段 + 五栏：干什么 / 不干什么 / 要带什么进来 / 留下什么 / 什么时候停，讲机制、带专业术语；`continuable` 标它能不能接着同一次产出干；纲领 P-18）与 `run(output_dir, inputs, ports, **params)`（`inputs` 是 `--from` 解析出来的产出，按阶段取），`discover()` 扫目录并断言签名；子包名下划线对命令名连字符。能力之间没有显式的输入输出接口：描述符里没有路径表，要的东西不在自己开始执行时报错。四颗：`design/` 写评分脚本、跑基线（设计阶段：`drafting` 组提示、起执行层、判越界、封 harness、ruff、校验，`baseline` 起 make_run0.sh 出 baseline/、预检；`--continue design/<n> --feedback` 让执行层改第二版）、`auto_research/` auto-research（实验阶段：`--from design/<n>`，`open` 把那包搬进 `work/`、按 lock 建 venv、起 git、快照 scoring.yaml 与需求；内环 `loop` / `judge` / `gate` / `failures` / `prompt.md`；`--continue experiment/<n>` 续跑与续命）、`analysis/` 写分析初稿（`--from experiment/<n>` 可多个，`analyze` + `prompt.md`）、`verify/` 核对数字（`--from analysis/<n>`，`checks` 零模型，写 report.json） | experiment、executor、workspace、contracts |
| `chat/` | 两位助理的对话与页面后端：`scope` 定域（工作区：cwd 是工作区、可写整个工作区、库 `workflows/` 与 `templates/` 可读不可写（端口 `readable_paths`，适配器 `--add-dir`）、对话在 `.ai4sci/chats/`；编辑台：cwd 是库的上级、只可写 `workflows/`、对话在 `studio/chats/`），`guide` 按域把 `coordinator/README.md` 或 `studio.md` 加前言塞进 system prompt（Bash 放行 `ai4sci`，带路径的老写法也放行，指南只教裸写法，红线 10 11）、`conversation` 建对话 / 发一轮 / 落盘 `<域>/chats/<id>/`（meta、每轮 message、原生事件流 events.jsonl 与不分后端的框架事件 trace.jsonl、transcript、忙锁、`read_turns` 读回结构含每轮 events、`title`；一轮有 `origin`：人，或框架来叫醒）、`notify` 作业跑完以「框架」身份给同一个工作区里的那段对话发一轮（忙就等，等不到记回作业）、`boards` 看板读盘（工作区一行与一整份、需求的原文 / 分节 / 确认状态 / 上一版原文、七个阶段的产出、一次产出的记录 / 签字 / 文件清单（小文本带正文）、每条流的进度、模板清单；NaN 出门前换 None）、`server` 标准库 HTTP + SSE（端点清单在文件头，按 `/workspaces/<id>/…` 与 `/studio/…` 分域；`/stages` `/templates` 直接读契约与库，`/cap` `/workflows` `/workflows/check` 与描述符表由 cli 以函数传入；不是接口前缀的 GET 路径端 `ui_dir` 的静态文件，单页应用回 index.html） | experiment、executor、workspace、contracts |
| `experiment/` | 实验这一族能力（design / auto-research / analysis / verify）私下的约定，框架的契约层不认识它（纲领 P-19）：`pack` 设计那包合不合约（`scoring.yaml`、harness/、code/、env/、baseline/；`schemas/` 三份 JSON Schema：scoring / results / report）、`env`（读 env/、uv 建 venv、起 harness 时保证给 `AI4SCI_PYTHON` `AI4SCI_BUDGET_S` `AI4SCI_INNER_K`，harness 给它们写默认值过不了校验）、`headroom` 预检（门高的唯一定义）、`layout` 一次实验目录里的路径（`work/`、`ledger.tsv`、`notebook.md`、`iters/iter_N/`、`executor/iter-N/`、`checkpoint.json`、`.venv/`）、`checkpoint`、`context` 只读上下文、`gitwork`、`ledger` 账本、`notebook` 实验笔记、`artifacts` 结果索引、`results` 成绩读取、`analysis` 数据表契约、`report` 验证报告、`prompting` 账本摘要 | executor、workspace、contracts |
| `executor/` | 起执行层会话：组 prompt（`prompting`，通用段）、起会话并留档日志（`session`） | workspace、contracts |
| `workspace/` | 工作区的磁盘：`root`（标记 requirement.md、从 cwd 往上找、按模板起、列）、`outputs`（`<stage>/<n>/` 的开与收：编号、meta、冻结判断）、`progress`（每条流实例走到哪、在等谁——作业 / 签字 / 助理 / 完了——从产出的 meta 与签字现算，没有进度文件）、`jobs` 后台作业（`.ai4sci/jobs/`：记录 + 日志，独立会话起 `framework.cli`，pid 探活判 lost，`attach_output` 挂上产出 id） | contracts |
| `contracts/` | 框架认的东西，只有这几样：`stages` 七个研究阶段的名字与目录名、`requirement`（requirement.md / requirement.lock：标题、分节、状态、确认、`require_confirmed` 那道门）、`output`（产出 id、`meta.yaml`、`tree_hash`、`signed.json` 与签字状态）、`workflows` 工作流文件（阶段 + 断点的解析与检查、`stop_after` / `matching_step`）、`capability` 能力描述符与入口形状（`Capability` / `Inputs` / `Param` / `Ports`；`title` 与五栏 `COLUMNS` 是给人读的，界面不另抄） | 谁都不 import（framework 内） |

`backends/` 与 `compute/` 是端口：framework 任何子包都可以 import 它们，它们不许 import framework。这条与上表都由 `tests/test_layering.py` 用 ast 逐条查，不是靠人 review。

## 红线

1. 框架零模型调用：`framework/` 下 grep 不到 anthropic / openai / claude_sdk（纲领 P-1）。
2. 不吞异常：ruff 的 BLE 规则开着，裸 `except` 与不 raise 的 `except Exception` 过不了 lint（P-7）。
3. 每个抽象带真实调用点，每个配置项有读取点与断言，集成点必须有测试（P-8）。
4. 密钥与敏感配置只进环境变量或 `.env`（已 gitignore），绝不进代码；ssh 主机与密钥路径同理。
5. Python 一律走 `.venv`（`make venv`），依赖钉在 `requirements.lock`，改依赖走 `make lock`。课题的依赖不进平台 venv：原件 `materials/env/` 两个文件跟着设计那包走，框架用 uv 给每次实验建自己的 venv，harness 只经 `$AI4SCI_PYTHON` 起解释器（裸 `python3` 过不了 `experiment/pack.py` 的校验）。
6. 每个改动合并时写进 `CHANGELOG.md` 的 Unreleased；发版只走 `make release VERSION=x.y.z`。
7. `make check` 是提交前门禁，与 CI 完全相同：changelog + ruff + pytest + 页面的 `ui-check`（tsc + oxlint + vitest + 构建）。真 CLI 冒烟测试默认 skip，`AI4SCI_LIVE=1` 才跑，CI 不跑。
8. 跨仓变更以外层仓的 GitHub issue 为锚，commit message 引用它。
9. `.claude/` 是本机会话产物，已 gitignore；不要读取或依赖其中内容。
10. 助理面前只有 `ai4sci` 一个入口（纲领 P-14 CLI 主导封装）：白名单是 `Bash(ai4sci *)`（带 `.venv/bin/` 的老写法也放行，前期别设坎），配置（模型、预算、超时、目录）归起服务的人的环境变量、命令上不带，命令也不带工作区路径（P-15：cwd 就是工作区）；两份指南里每条命令以 `ai4sci ` 开头、不带路径不挂前缀不接管道（`test_chat_guide` 守着）。agent 需要而没有的动作是平台缺口：加能力，不放行裸命令。给研究者看的话（指南、页面、agent 的回话）不用「能力单元」这类内部词，每条命令翻成一句直白话；文档与指南用直白的工程语言：命令就是 agent 调用的 tool，「人按」就是人确认，不写「按钮」「键」这种比喻（主人 2026-09-18）。
11. 造流与用流分权（纲领 P-16）：主页面的研究助理只能用流（`flow take` 取、改实例、照着跑），不造流、不造能力；编辑台的造流助理只写 `workflows/`，不跑实验、不碰工作区。分权靠 `chat/scope.py` 的可写目录与按域分前缀的端点，不靠指南里的一句「请不要」；研究助理的指南里没有 `workflows/<name>.yaml` 的写法（`test_chat_guide` 守着）。
12. 素材不进仓（纲领 P-17）：页面里的图片 / 视频只写自己 CDN 的 URL，且只在 `ui/web/src/assets.ts` 一处；`git ls-files ui/` 里没有 png / jpg / mp4（`make ui-check` 守着）；图标全站一套 Phosphor 内联。素材从来源站下到本机、处理好再推桶，不直接引第三方源；清单与许可记在 `docs/DESIGN.md`「素材」。
13. 框架只管文件夹怎么摆，不管里面装什么（纲领 P-19）：框架认的文件只有 `requirement.md` / `requirement.lock` / `meta.yaml` / `signed.json` / 流文件 / 描述符；`scoring.yaml` 这类是某一族能力私下的约定，放那族自己的包里（`framework/experiment/`），不进 `contracts/`。需求确认是唯一内置的门；断点几个、放哪由拼流的人定。能力是纯函数：读什么用 `--from` 点名，没有「缺省读最新」——哪次产出该喂给谁，是助理看着磁盘做的判断。

## 版本与发布

- 从 0.1.0 起步，0.x 不承诺兼容；正式发布才进入 1.0.0。tag 形如 `vX.Y.Z`，内测 `-rc.N`。
- 推送 tag 触发 `release.yml`：对账 CHANGELOG → `make check` → `make package` → 建 Release 并附包，0.x 自动标 pre-release。
- commit message 用中文，技术名词保留英文；一个逻辑单元一个 commit。
