<h1 align="center">tju-ai4science-platform</h1>

<p align="center">TJU AI for Science · 生产代码仓</p>

## 这是什么

科研全自动化平台的生产代码。四层：协调层（人 + agent）做科研判断，框架是诚实执行的基底，执行层 coding agent CLI 是唯一执行者，工具是确定性脚本。纲领、spec 与决策记录在外层协作仓 [`tju-ai4science`](https://github.com/zephyr4123/TJU-AI4Science) 的 `docs/`，本仓由它的 `./repos clone all` 拉到 `platform/` 目录下。

## 目录

```
platform/
├── coordinator/   协调层 skill 包（执行层不加载）
├── framework/     框架：能力、runner、契约、验证、ai4sci CLI；零模型调用
├── backends/      执行层适配器：claude_code.py …
├── compute/       算力适配器：local.py …
├── tools/         确定性脚本
├── domains/       领域包（generic/ 兜底）
├── tasks/         任务包（mlp-regression/ …）
├── runs/          运行产物，不进 git
├── tests/         框架测试
├── Makefile       check / venv / lock / package / release
└── CHANGELOG.md
```

## 怎么跑

```bash
make venv                                   # 建 .venv，按 requirements.lock 装依赖
make check                                  # 门禁：CHANGELOG 校验 + ruff + pytest
.venv/bin/ai4sci task validate tasks/mlp-regression
AI4SCI_LIVE=1 make test                     # 连真 CLI 的冒烟测试，会花钱，CI 不跑
```

## 版本与发布

1. 改动合并时把条目写进 `CHANGELOG.md` 的 Unreleased。
2. `make release VERSION=0.2.0`：轮转 CHANGELOG、提交、打 tag，不 push。
3. 推 tag 触发 GitHub Release，0.x 自动标 pre-release。
