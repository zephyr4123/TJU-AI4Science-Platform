# 变更日志

本仓库所有值得注意的变更都记录在这里。格式遵循 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)，版本号遵循 [语义化版本 2.0.0](https://semver.org/lang/zh-CN/)。

- 每个改动合并时，把条目写进 **Unreleased**；发布时 `make release VERSION=x.y.z` 把它轮转成版本小节并打 tag，推送 tag 即触发流水线出包并建 GitHub Release。
- 1.0.0 之前是开发期：0.x 不承诺兼容性，正式发布才进入 1.0.0。
- 条目分类用：新增 / 变更 / 修复 / 移除 / 安全。

## [Unreleased]

### 新增
- 执行层适配器 `backends/`（R-1，外层 #20）：`Runner` 端口与 `RunResult`；Claude Code 适配器走 `claude -p --output-format stream-json`，隔离位 `--setting-sources "" --strict-mcp-config --disable-slash-commands`（不加载本机 CLAUDE.md / skill / MCP / plugin / hook，一句 pong 从 $0.46 降到 $0.05），权限 `dontAsk` + `allowedTools` 白名单且绝对路径规则用 `//`，超时 `kill_tree` 逐进程组杀（CLI 的 Bash 子进程自成进程组，只 killpg 自己会留孤儿），`changed_files` 用调用前后 sha256 快照 diff 不采信 CLI 自报，超时拿不到 result 事件时成本填 NaN 不填 0，事件流与 stderr 落盘 `.ai4sci/`。真 CLI 冒烟测试 `AI4SCI_LIVE=1` 才跑
- 任务包契约与 CLI（R-2，外层 #21）：`framework/schemas/manifest.schema.json` 与 `results.schema.json`（没有读取点的字段不进 schema，本轮 `conditions` 未进）；`framework/packs.py` 扫目录发现任务包、逐条校验（schema、id 等于目录名、恰好一个 primary、domain 存在、harness 三件套与 SHA256SUMS 对账、run_0 基线与 repeat_k 次重复与 σ、elapsed 不超预算 1.5 倍）；`ai4sci task validate <dir>` 与 `task list`，退出码 0 / 1 / 2
- 算力端口与本地后端 `compute/`（外层 #23）：`Compute` 协议五个动作（put / submit / wait / cancel / get）与 `Job`、`ExitStatus`；`submit` 立刻返回句柄并把它落盘成 `run_N/job.json`，续跑靠它重新接上或收尸；`ExitStatus.exit_code` 用 `None` 表达"已死但退出码未知"（续跑读回的 job 不是本进程的子进程，填 0 就是把未知讲成成功）；local 后端 `Popen(start_new_session=True)` 起独立进程组、stdout/stderr 落 `.job/`，超时逐进程组杀干净（僵尸不算活着——`killpg(pgid, 0)` 会把没被收走的尸体读成还在跑，改用 ps 查非僵尸成员）；名字对不上报错列出可用名字，绝不静默回退
- 实验内环 runner `framework/loop.py`（外层 #24）：一轮走 revert-to-best → 执行层只改 `code/` → 事后快照 diff 判越界 → runner 提交（作者固定 `ai4sci runner`）→ 快照进 `experiment/runs/run_N/` 起独立进程跑 harness → 六类失败确定性分类（`framework/failures.py`，优先级固定：只读被改 → 超时 → 缺依赖 → 崩溃 → 结果缺失 / 不合 schema / harness 自报 status 不是 ok → 指标 NaN，附一句修复提示喂给下一轮）。崩溃只认 stderr 里的 traceback：真任务包的 launcher 是 `set -euo pipefail`、evaluate 拒收产物时按契约 `SystemExit` 加一句话退出，退出码分不出"假成功"和"跑崩了"，退非 0 而没有 traceback 一律先看产物判 no_results（退非 0 但产物齐全的极端情况仍归 crash）→ 过统计门（delta > `max(accept_sigma×σ, budget.min_delta)`）才 keep，否则先 `refs/attempts/iter-N` 留档再 reset 回 best；新增可选 `budget.min_delta`（缺省 0）兜住 σ=0 的退化，σ 与 min_delta 同时为 0 时 fail-closed 不开跑；改动全被任务包 `.gitignore` 挡住时记 noop 并把原因写进账本 → 账本 `experiment/ledger.tsv` 追加一行并与 git 对账（`framework/ledger.py`，keep 行的 parent 必须接上一条 keep 的 commit、首条接基线）→ checkpoint 原子写；停止条件轮数上限 / 连续 patience 轮不改进（新增 `budget.patience`，缺省 5）/ 同类失败连续 3 次判不可修复 / `budget.max_cost_usd` 用尽，任一触发写 `experiment/stop.json`；`--max-iters` 是**本次增量**不是 run 的总额（上限取 `min(manifest.max_iterations, 已跑轮数 + max_iters)`），配额用完只返回 `batch_exhausted` 且不写 stop，再跑一次接着往下；`loop resume` 读 checkpoint + 账本 + git 三方对账，对不上就抛不猜，被杀在半路的那一轮记 `interrupted` 并回到 best；两个结算尾巴上的崩溃窗口（只剩标记没删 / 账本领先 checkpoint 一行）以账本为准补齐，`loop run` 见到 in-flight 标记直接拒跑并指回 `loop resume`，被 Ctrl-C 打断时先杀掉在飞的 harness 再把异常抛上去；提示模板 `framework/prompts/experiment.md`，账本摘要常数大小（最近 5 行）；CLI 加 `ai4sci run new` / `loop run` / `loop resume` / `status`（`status` 末尾跑一次账本 × git 对账，有问题逐条打 stderr 并退 1）
- 实验笔记与续命（外层 #28 #26）：`experiment/notebook.md` 一个 run 一本，runner 每轮追加执行层自述（stream-json 最终 result 文本，截 600 字）+ `git diff --stat` + 裁决，下一轮整本进 prompt，执行层收尾按"假设 / 改动 / 预期"三行自述。真跑第 2 轮与第 5 轮做了同一个改动暴露的缺陷：新会话是为了上下文不膨胀，不是为了失忆。`ai4sci run extend <id> --patience / --max-iterations / --max-cost-usd --reason`：改快照里的 budget、清 stop_reason 与 stop.json、journal.md 记一行，协调层给已停的 run 续命不用手改文件
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
