# AutoResearch：给研究助理的说明

什么时候用：设计阶段的评分脚本封好、基线跑过、人签了之后，在实验阶段一轮一轮改代码，过统计门才算改进。

怎么跑：`ai4sci cap auto-research --from design/<n> --ws <名字> --detach`（`--max-iters` 是这一批跑几轮；流程实例里写了就照它）。接着上一次跑：`--continue experiment/<n>`，还是同一次产出。

结局（结论行开头的 `stop <原因>`）：
- `batch_exhausted`：这批轮数用完，实验没停。想继续就 `--continue experiment/<n>` 再跑一批；不跑了就往下走。
- `patience` / `max_iterations` / `max_cost_usd` / `unrecoverable`：实验停了，原因在 `stop.json`。读 `notebook.md` 决定：加预算接着跑（`--continue experiment/<n> --patience <轮数> --reason <为什么>`，改预算、清停止标记后接着跑）、回设计阶段重开一次，还是就此往下走。跟研究者商量，加预算是人的决定。
- 退 1 说有跑到一半的一轮（in-flight）：上次被杀在半路，`--continue experiment/<n> --resume`；对不上（`ResumeMismatch`）就停下来找人，不要手改 `checkpoint.json`。

记录：`experiment/<n>/.ai4sci/journal.md` 是你的本子，每个决定一行——为什么进这个阶段、看到什么、下一步。它不算进产出的 hash，实验被读过、签过之后照样能记。不要替执行层改 `work/code/`，不要手改 `ledger.tsv`、`checkpoint.json`：账本与 git 的对账会把改动抓出来。
