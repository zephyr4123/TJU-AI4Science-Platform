# TJU AI for Science · platform（生产代码仓）

给 agent 与新成员的约定。本仓是内仓：外层协作仓 `tju-ai4science` 把它 clone 到 `platform/` 目录下，外层对它的 git 完全不知情。架构纲领与 spec 在外层 `docs/`，这里只写规矩。

## 目录（按纲领四层）

| 目录 | 放什么 |
|---|---|
| `coordinator/` | 协调层 skill 包：怎么当科研助理、怎么驱动框架。注入到当协调层的 CLI；执行层会话不许加载 |
| `framework/` | 框架：能力、runner、契约 schema、验证、裁判、`ai4sci` CLI。零模型调用，不随任务改 |
| `backends/` | 执行层适配器：一个 coding agent CLI 一个文件；端口 `Runner` 定义在 `backends/__init__.py` |
| `compute/` | 算力适配器：一个后端一个文件；端口 `Compute` 定义在 `compute/__init__.py` |
| `tools/` | 确定性脚本：文献 API、引用校验、出图、harness 基类 |
| `domains/` | 领域包，一个领域一个目录；`generic/` 兜底；含执行层的 skill |
| `tasks/` | 任务包，一个任务一个目录：`manifest.yaml` `harness/` `code/` `data/` `run_0/` |
| `runs/` | 运行产物，不进 git |
| `tests/` | 框架测试；单测跟着模块走 |

依赖只指向一个方向：`framework/` → `backends/`、`compute/`、`tools/`；适配器只 import 自己包根的端口定义，不 import `framework/`。任何目录都不依赖外层仓的路径。

## 红线

1. 框架零模型调用：`framework/` 下 grep 不到 anthropic / openai / claude_sdk（纲领 P-1）。
2. 不吞异常：ruff 的 BLE 规则开着，裸 `except` 与不 raise 的 `except Exception` 过不了 lint（P-7）。
3. 每个抽象带真实调用点，每个配置项有读取点与断言，集成点必须有测试（P-8）。
4. 密钥与敏感配置只进环境变量或 `.env`（已 gitignore），绝不进代码；ssh 主机与密钥路径同理。
5. Python 一律走 `.venv`（`make venv`），依赖钉在 `requirements.lock`，改依赖走 `make lock`。
6. 每个改动合并时写进 `CHANGELOG.md` 的 Unreleased；发版只走 `make release VERSION=x.y.z`。
7. `make check` 是提交前门禁，与 CI 完全相同：changelog + ruff + pytest。真 CLI 冒烟测试默认 skip，`AI4SCI_LIVE=1` 才跑，CI 不跑。
8. 跨仓变更以外层仓的 GitHub issue 为锚，commit message 引用它。
9. `.claude/` 是本机会话产物，已 gitignore；不要读取或依赖其中内容。

## 版本与发布

- 从 0.1.0 起步，0.x 不承诺兼容；正式发布才进入 1.0.0。tag 形如 `vX.Y.Z`，内测 `-rc.N`。
- 推送 tag 触发 `release.yml`：对账 CHANGELOG → `make check` → `make package` → 建 Release 并附包，0.x 自动标 pre-release。
- commit message 用中文，技术名词保留英文；一个逻辑单元一个 commit。
