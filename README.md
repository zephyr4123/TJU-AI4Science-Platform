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
│   ├── capabilities/  一个能力一个子包（experiment/ 实验内环、analysis/ 分析、verify/ 验证），互不 import，各带描述符
│   ├── executor/      组 prompt、起执行层会话、留档日志
│   ├── memory/        账本、实验笔记
│   ├── run/           run 的布局、checkpoint、上下文、生命周期、work/ 的 git、结果索引
│   └── contracts/     schema、任务包校验、任务环境（env/ 与 uv 建 venv）、产物读取、能力描述符、analysis.md 与 report.json 契约
├── backends/      执行层适配器：claude_code.py …
├── compute/       算力适配器：local.py …
├── tools/         确定性脚本
├── domains/       领域包，按工具链命名（generic/ 兜底、petab/ 参数估计）；prompts/ 与 skills/ 随 run 快照进执行层提示
├── tasks/         任务包（mlp-regression/ 玩具、boehm-nll/ 第一个真任务）；每个自带 env/
├── docs/          add-a-task.md：十分钟接一个任务
├── runs/          运行产物，不进 git；每个 run 自带 .venv/
├── tests/         框架测试
├── Makefile       check / venv / lock / package / release
└── CHANGELOG.md
```

命令行上就四类东西：`cap` 能力、`sign` 键、`show` 查询、`chat` / `serve` 入口。依赖只许自上而下：`cli → capabilities → chat → executor → memory → run → contracts`；`backends/` 与 `compute/` 是端口，framework 用它们、它们不认识 framework。这条规矩由 `tests/test_layering.py` 用 ast 逐条查。

## 怎么跑

```bash
make venv                                   # 建 .venv，按 requirements.lock 装依赖（含 uv）
make check                                  # 门禁：CHANGELOG 校验 + ruff + pytest
.venv/bin/ai4sci show task tasks/mlp-regression        # 校验任务包合不合契约
AI4SCI_LIVE=1 make test                     # 连真 CLI 的冒烟测试，会花钱，CI 不跑
```

一条 auto-research 流，四条命令由协调层手工串（框架不连跑，见 `coordinator/README.md`）：

```bash
.venv/bin/ai4sci cap start tasks/mlp-regression --run-id demo # 开一次实验：建 run
.venv/bin/ai4sci cap experiment demo --max-iters 5            # 实验内环，执行层 Claude Code 改 code/
.venv/bin/ai4sci cap analysis demo                            # 执行层写 analysis/analysis.md
.venv/bin/ai4sci cap verify demo                              # 零模型验证，退出码就是 PASS / FAIL
.venv/bin/ai4sci show caps                                    # 按七个科研阶段列全部能力（--json 带描述符与 used_by）；show workflows 列工作流与覆盖的阶段
```

执行层用哪个模型、超时多久走环境变量：`AI4SCI_EXECUTOR_MODEL=sonnet`、`AI4SCI_EXECUTOR_TIMEOUT_S=600`。

任务跑在自己的环境里：`cap start` 按任务包的 `env/` 建 `runs/<id>/.venv`，harness 只经 `$AI4SCI_PYTHON` 起解释器，平台 venv 一个包不多装。接一个新任务看 [`docs/add-a-task.md`](docs/add-a-task.md)。

## 版本与发布

1. 改动合并时把条目写进 `CHANGELOG.md` 的 Unreleased。
2. `make release VERSION=0.2.0`：轮转 CHANGELOG、提交、打 tag，不 push。
3. 推 tag 触发 GitHub Release，0.x 自动标 pre-release。
