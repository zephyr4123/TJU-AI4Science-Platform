# 变更日志

本仓库所有值得注意的变更都记录在这里。格式遵循 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)，版本号遵循 [语义化版本 2.0.0](https://semver.org/lang/zh-CN/)。

- 每个改动合并时，把条目写进 **Unreleased**；发布时 `make release VERSION=x.y.z` 把它轮转成版本小节并打 tag，推送 tag 即触发流水线出包并建 GitHub Release。
- 1.0.0 之前是开发期：0.x 不承诺兼容性，正式发布才进入 1.0.0。
- 条目分类用：新增 / 变更 / 修复 / 移除 / 安全。

## [Unreleased]

### 新增
- 执行层适配器 `backends/`（R-1，外层 #20）：`Runner` 端口与 `RunResult`；Claude Code 适配器走 `claude -p --output-format stream-json`，隔离位 `--setting-sources "" --strict-mcp-config --disable-slash-commands`（不加载本机 CLAUDE.md / skill / MCP / plugin / hook，一句 pong 从 $0.46 降到 $0.05），权限 `dontAsk` + `allowedTools` 白名单且绝对路径规则用 `//`，超时 `kill_tree` 逐进程组杀（CLI 的 Bash 子进程自成进程组，只 killpg 自己会留孤儿），`changed_files` 用调用前后 sha256 快照 diff 不采信 CLI 自报，超时拿不到 result 事件时成本填 NaN 不填 0，事件流与 stderr 落盘 `.ai4sci/`。真 CLI 冒烟测试 `AI4SCI_LIVE=1` 才跑
- 任务包契约与 CLI（R-2，外层 #21）：`framework/schemas/manifest.schema.json` 与 `results.schema.json`（没有读取点的字段不进 schema，本轮 `conditions` 未进）；`framework/packs.py` 扫目录发现任务包、逐条校验（schema、id 等于目录名、恰好一个 primary、domain 存在、harness 三件套与 SHA256SUMS 对账、run_0 基线与 repeat_k 次重复与 σ、elapsed 不超预算 1.5 倍）；`ai4sci task validate <dir>` 与 `task list`，退出码 0 / 1 / 2
- 玩具任务 `tasks/mlp-regression/`（R-3，外层 #12 #21）：纯 Python 单隐层 MLP 拟合含噪一维函数，单标量 `val_mse` minimize，一次 0.25 s；harness 只吃 predictions.json 算分，预测缺失 / 长度不对 / NaN 一律退非 0 且不写 results.json；`run_0/` 含基线、三个种子的重复与 σ（0.0036，基线 0.0231），`harness/make_run0.sh` 可复现

### 变更
- 目录按纲领四层重建：`coordinator/ framework/ backends/ compute/ tools/ domains/ tasks/ runs/ tests/`，原 monorepo 占位目录（apps / packages / workers / db / infra）删除
- 定栈 Python：`pyproject.toml`、`.venv` + `requirements.lock`、ruff（含 BLE 裸 except 门禁）+ pytest 接进 `make check`，CI 装 Python 3.14。框架依赖只有 pyyaml 与 jsonschema，数值库是任务包自己的事

## [0.1.0] - 2026-09-08

### 新增
- 生产代码 monorepo 骨架：`apps/web`、`apps/api`、`packages/core`、`workers/`、`db/`、`infra/`、`tests/` 位置约定
- 变更日志与发布流水线：CHANGELOG 机器校验、`make release` 轮转、tag 触发 CI 出包并建 GitHub Release
- `make check` 门禁入口（lint / test 为占位，定栈后接入）

[Unreleased]: https://github.com/zephyr4123/TJU-AI4Science-Platform/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/zephyr4123/TJU-AI4Science-Platform/releases/tag/v0.1.0
