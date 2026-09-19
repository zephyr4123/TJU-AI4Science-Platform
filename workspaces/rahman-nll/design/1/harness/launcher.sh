#!/usr/bin/env bash
# 唯一执行入口：清产物 -> 跑 INNER_K 次基线优化(每次独立子进程、独立内部种子) -> 评分。
set -euo pipefail
: "${AI4SCI_PYTHON:?未设 AI4SCI_PYTHON：先 ai4sci task env build <task_dir>，或由框架提交}"
TASK_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$TASK_DIR"

INNER_K=25          # 内部重复次数，与 evaluate.py 的 n_miss/nll_mean 统计口径一致，改一处要改另一处
# 每次优化的预算秒数：研究者的决策，不是从 manifest 的 budget.wall_clock_s 除出来的。
# manifest 的 wall_clock_s=75 覆盖的是 INNER_K × (INNER_BUDGET_S + 约 1.1 秒固定开销：
# 子进程 import 各库 1.03s、装载 PEtab+RoadRunner 0.06s)，跟这个数不是同一个量，别去「对齐」。
INNER_BUDGET_S=2

rm -f params_*.json params.json results.json

OUTER_SEED="${AI4SCI_SEED:-42}"
AI4SCI_START_EPOCH="$("$AI4SCI_PYTHON" -c 'import time; print(time.time())')"
export AI4SCI_START_EPOCH

for i in $(seq 0 $((INNER_K - 1))); do
  inner_seed=$((OUTER_SEED + 100 * i))
  AI4SCI_SEED="$inner_seed" AI4SCI_BUDGET_S="$INNER_BUDGET_S" "$AI4SCI_PYTHON" code/optimize.py
  mv params.json "params_${i}.json"
done

export AI4SCI_SEED="$OUTER_SEED"
export AI4SCI_INNER_K="$INNER_K"
"$AI4SCI_PYTHON" harness/evaluate.py
