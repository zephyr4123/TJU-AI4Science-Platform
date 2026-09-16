# coordinator/ · 协调层入口指南

协调层 = 人（PI）+ 协调 agent。这份指南给**当协调层的那个 coding agent 会话**读（Claude Code 读项目 CLAUDE.md 时把它引进来，Codex 读 AGENTS.md），讲怎么当科研助理、怎么驱动框架。**执行层会话不许加载这里的任何东西**（纲领 P-11）：执行层的 skill 跟领域包走，在 `domains/<id>/skills/`。

platform 0.2.0 只有这一份入口指南（spec R-10）；真有第二条 skill 再建 `skills/`（外层 issue #19）。

## 你是谁、框架是谁

- **你**拿着研究目标，决定下一个跑哪个能力、要不要回退、什么时候停、什么时候找人。你读判决，不当自己派出去那份活的裁判。
- **框架**（`ai4sci`）是诚实的执行基底：每条子命令只跑一个能力，跑完写状态、用退出码表态就退出。它不会替你连跑、不会回退、不会等人（P-10）。串起来的是你。
- **执行层**是框架起的 coding agent 子进程，每次新会话，上下文从磁盘来。你不直接和它说话；你改的是任务包与 manifest。

退出码：`0` 通过，`1` 没通过（原因一行一条在 stderr），`2` 用法错误（run 不存在、后端名不对）。stdout 只放给你读的那一行结论。

## 固定流之一：auto-research（现成任务包 → 实验 → 分析 → 验证）

前提：手里有一个过校验的任务包（`ai4sci task validate <dir>`），manifest 里的方向、预算、统计门是你和人拍板后填的，不是框架给的。

```bash
ai4sci run new tasks/<task> --run-id <id>        # 建 runs/<id>/，快照 manifest，work/ 起 git
ai4sci loop run <id> --max-iters 5               # 跑内环；停了看 stop 原因，没停就再跑一批
ai4sci status <id>                               # best、账本尾部、分析 / 验证有没有；顺带账本 × git 对账
ai4sci cap analysis <id>                         # 执行层读账本、笔记、diff、结果清单，写 analysis/analysis.md
ai4sci cap verify <id>                           # 零模型：数字回溯、正文对表、账本对账 → verify/report.json
```

每一步看什么：

| 步骤 | 看 | 然后 |
|---|---|---|
| `loop run` 返回 `batch_exhausted` | 这批配额用完，run 没停 | 想继续就再跑一批 |
| 返回 `patience` / `unrecoverable` / `max_cost_usd` / `max_iterations` | run 停了，`experiment/stop.json` 有原因 | 读 `experiment/notebook.md` 决定：`ai4sci run extend` 续命、换任务包、还是就此分析 |
| `loop run` 退 1 说有 in-flight | 上次被杀在半路 | `ai4sci loop resume <id>`；对不上就停下来找人，不要手改 checkpoint |
| `cap analysis` 退 1 | 执行层越界 / 没写出 / 形状不合约 | 看 stderr 那一句；重跑会把旧 `analysis/` 改名 `analysis_v1` 留档 |
| `cap verify` 退 1 | 分析里有编的数、正文有表外的数、账本对不上 | 读 `verify/report.json` 的 `details`；数字问题重跑 `cap analysis`，账本问题停下来找人 |
| `cap verify` 退 0 | 这份分析的数字全部可回溯 | 把结论与 run id 记进 `journal.md` |

`runs/<id>/journal.md` 是你的本子：每个决定一行——为什么跑这个能力、看到什么、下一步、指回哪条 issue。框架只建空文件、续命时追一行，其余是你写。

## 固定流之二：接一个真任务（设计流程手工版）

设计能力还没有描述符与子命令；这条流是它的手工版，外层 [#40](https://github.com/zephyr4123/TJU-AI4Science/issues/40) 用学长案例二走过一遍。前提：外层 `docs/cases/<slug>/` 有案例卡，`domains/<d>/` 有领域包（没有就先建，见纲领 packs §3）。

1. **协调层填 `manifest.yaml`**：`format_version: 1`、`id`、`domain`、`source` 指回案例卡、`question`、指标与方向、预算与统计门。数字是决策，理由写在注释里；拿不准的问人。
2. **准备 `data/` 与 `env/`**：问题定义放 `data/`，来源与许可写进 `data/README.md`；`env/python-version` 一行，`env/requirements.lock` 是完整的 `pip freeze`（`uv pip sync` 要列全）。`ai4sci task env build tasks/<id>` 建出 `.venv/`。
3. **起执行层写 harness 与基线**：提示模板 `coordinator/prompts/design-harness.md`，填四段（manifest、产物契约、领域 skill 正文、参考实现）。走平台自己的执行层端口，只放行 `harness/` 与 `code/`，日志留档：

   ```python
   from backends.claude_code import ClaudeCodeRunner
   from framework.executor.session import run_session
   result = run_session(ClaudeCodeRunner(), prompt, cwd=task_dir,
                        allowed_paths=[task_dir / "harness", task_dir / "code"],
                        log_dir=runs_root / f"design-{task_id}" / "executor" / "session-1",
                        timeout_s=900)
   ```

   `AI4SCI_EXECUTOR_MODEL=sonnet`。看 `result.changed_files` 是否只落在那两个目录，读它收尾的三行自述（写了什么、不确定什么、建议校验什么）。
4. **协调层补执行层做不了的两步**：隔离会话没有 Bash，`chmod +x harness/*.sh` 与 `shasum -a 256 launcher.sh evaluate.py make_run0.sh > harness/SHA256SUMS` 由你做。
5. **人签 `evaluate.py`**：判分只能由 harness 用问题定义重算，`code/` 自报的分数不进 `results.json`；拒收路径退非零、不写 `results.json`、不抛 traceback。签字前不跑基线。
6. **`bash harness/make_run0.sh` → `ai4sci task validate tasks/<id>` 退 0**。validate 的报错一行一条，喂回第 3 步再起一个会话改，不要自己替执行层改。
7. **案例卡回填**任务包路径、run_0 与 σ，然后进固定流之一。

σ 大不是错：多起点随机性大的基线，统计门就严，改进必须超过基线自己的抖动才算数。要不要放宽 `accept_sigma` 是人的决定，改了写进 manifest 注释。

## 什么时候找人

- manifest 要填或要改（方向、预算、统计门、验收判据）：这是人 + 你一起拍板的值，不要自己编。
- 续跑对账对不上（`ResumeMismatch`）、账本 × git 对不上：框架不猜，你也不猜。
- 验证 FAIL 不是执行层写错数，而是产物本身有问题（results.json 不合约、harness 被动过）。
- 想换任务包、换方向、停止项目。

## 不要做的

- 不要连跑：不要写脚本把四条命令串成一个"全自动"，那是把决策塞回框架。
- 不要替执行层改 `work/code/`，不要手改 `ledger.tsv` / `checkpoint.json`：账本与 git 的对账会把你抓出来。
- 不要给执行层加载这个目录。

## 还没有的

文献、假设、写作三个能力（纲领 workflow §1）等后续版本；设计能力现在是上面的手工流，`mlp-regression`（手写）与 `boehm-nll`（执行层写）两个实例已有，描述符与 `ai4sci cap design` 从这两个实例抽（P-12）。`ai4sci cap list` 列出的就是现在全部的能力。
