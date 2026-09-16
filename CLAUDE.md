# TJU AI for Science · platform（生产代码仓）

给 agent 与新成员的约定。本仓是内仓：外层协作仓 `tju-ai4science` 把它 clone 到 `platform/` 目录下，外层对它的 git 完全不知情。架构纲领与 spec 在外层 `docs/`，这里只写规矩。

## 目录（按纲领四层）

| 目录 | 放什么 |
|---|---|
| `coordinator/` | 协调层入口指南：怎么当科研助理、怎么驱动框架跑固定流。注入到当协调层的 CLI；执行层会话不许加载 |
| `framework/` | 框架：能力、runner、契约 schema、验证、裁判、`ai4sci` CLI。零模型调用，不随任务改 |
| `backends/` | 执行层适配器：一个 coding agent CLI 一个文件；端口 `Runner` 定义在 `backends/__init__.py` |
| `compute/` | 算力适配器：一个后端一个文件；端口 `Compute` 定义在 `compute/__init__.py` |
| `tools/` | 确定性脚本：文献 API、引用校验、出图、harness 基类 |
| `domains/` | 领域包，按工具链命名，一个领域一个目录；`generic/` 兜底、`petab/` 参数估计；`prompts/<能力>.md` 与 `skills/*/SKILL.md` 由 `run new` 快照进 run、随执行层提示的「领域约定」段注入（执行层的隔离参数关掉了 CLI 原生 skill 加载） |
| `tasks/` | 任务包，一个任务一个目录：`manifest.yaml`（`format_version` 必填）`env/`（python-version + requirements.lock）`harness/` `code/` `data/` `run_0/`；`.venv/` 由 `ai4sci task env build` 建，不进 git |
| `docs/` | 面向接任务的人的指南 |
| `runs/` | 运行产物，不进 git；每个 run 自带 `.venv/` |
| `tests/` | 框架测试；单测跟着模块走 |

依赖只指向一个方向：`framework/` → `backends/`、`compute/`、`tools/`；适配器只 import 自己包根的端口定义，不 import `framework/`。任何目录都不依赖外层仓的路径。

### `framework/` 的子包

按概念分包，依赖**只许自上而下**，同层与包内随意：

| 子包 | 放什么 | 可以 import |
|---|---|---|
| `cli/` | 一个子命令一个模块（`task` `run` `loop` `cap` `status`），`__init__` 装配 parser 并导出 `main`；`cap` 的子命令从能力描述符生成 | 下面全部 |
| `capabilities/` | 一个能力一个子包，互不 import，每个导出 `DESCRIPTOR` 与 `run(run_dir, ports, **params)`，`discover()` 扫目录并断言签名；`experiment/` 实验内环（`loop` / `judge` / `gate` / `failures` / `prompt.md`）、`analysis/` 分析（`analyze` + `prompt.md`）、`verify/` 验证（`checks` 零模型） | executor、memory、run、contracts |
| `executor/` | 组 prompt（`prompting`）、起执行层会话并留档日志（`session`） | memory、run、contracts |
| `memory/` | 账本 `ledger`、实验笔记 `notebook`；项目级记忆以后加在这 | run、contracts |
| `run/` | 一个 run 的磁盘状态：`layout` 路径、`checkpoint`、`context` 只读上下文、`lifecycle` 建 run / 续命 / 能力目录轮转、`gitwork`、`artifacts` 结果索引 | contracts |
| `contracts/` | `schemas/*.json`、任务包发现与校验 `packs`、任务环境 `env`（读 env/、uv 建 venv）、产物读取 `results`、能力描述符与入口形状 `capability`、`analysis.md` 数据表契约 `analysis`、验证报告 `report` | 谁都不 import（framework 内） |

`backends/` 与 `compute/` 是端口：framework 任何子包都可以 import 它们，它们不许 import framework。这条与上表都由 `tests/test_layering.py` 用 ast 逐条查，不是靠人 review。

## 红线

1. 框架零模型调用：`framework/` 下 grep 不到 anthropic / openai / claude_sdk（纲领 P-1）。
2. 不吞异常：ruff 的 BLE 规则开着，裸 `except` 与不 raise 的 `except Exception` 过不了 lint（P-7）。
3. 每个抽象带真实调用点，每个配置项有读取点与断言，集成点必须有测试（P-8）。
4. 密钥与敏感配置只进环境变量或 `.env`（已 gitignore），绝不进代码；ssh 主机与密钥路径同理。
5. Python 一律走 `.venv`（`make venv`），依赖钉在 `requirements.lock`，改依赖走 `make lock`。任务的依赖不进平台 venv：任务包自带 `env/`，框架用 uv 建任务级 venv，harness 只经 `$AI4SCI_PYTHON` 起解释器（裸 `python3` 过不了 `task validate`）。
6. 每个改动合并时写进 `CHANGELOG.md` 的 Unreleased；发版只走 `make release VERSION=x.y.z`。
7. `make check` 是提交前门禁，与 CI 完全相同：changelog + ruff + pytest。真 CLI 冒烟测试默认 skip，`AI4SCI_LIVE=1` 才跑，CI 不跑。
8. 跨仓变更以外层仓的 GitHub issue 为锚，commit message 引用它。
9. `.claude/` 是本机会话产物，已 gitignore；不要读取或依赖其中内容。

## 版本与发布

- 从 0.1.0 起步，0.x 不承诺兼容；正式发布才进入 1.0.0。tag 形如 `vX.Y.Z`，内测 `-rc.N`。
- 推送 tag 触发 `release.yml`：对账 CHANGELOG → `make check` → `make package` → 建 Release 并附包，0.x 自动标 pre-release。
- commit message 用中文，技术名词保留英文；一个逻辑单元一个 commit。
