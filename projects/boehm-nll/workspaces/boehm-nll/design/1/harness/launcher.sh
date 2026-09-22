#!/usr/bin/env bash
# 唯一执行入口:框架在任务目录里无参执行它。
# 先清干净上一轮的产物,再跑基线优化、再评分——这样"results.json 存在"永远等于"这一轮真跑出了成绩"。
set -euo pipefail

# 任务跑在自己的 venv 里:解释器只从 AI4SCI_PYTHON 来(框架提交 harness 时设,make_run0.sh 缺省指到
# 任务目录的 .venv)。没设就停在这里,绝不退回到 PATH 上碰巧的那个 python3。
: "${AI4SCI_PYTHON:?未设 AI4SCI_PYTHON:先 ai4sci task env build <task_dir>,或由框架提交}"

# 主指标是 INNER_K 个内部 seed 各优化一次的 NLL 均值(改指标的理由见 manifest.yaml 顶部注释,
# 外层 #40)。TOTAL_BUDGET_S 要与 manifest.budget.wall_clock_s 一致,改一处就要改另一处。
INNER_K=3
TOTAL_BUDGET_S=60
INNER_BUDGET_S=$((TOTAL_BUDGET_S / INNER_K))

TASK_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$TASK_DIR"

rm -f params.json params_*.json results.json

# 整段墙钟从这里开始计,evaluate.py 读它写进 results.json 的 elapsed_s。
AI4SCI_START_EPOCH="$("$AI4SCI_PYTHON" -c 'import time; print(time.time())')"
export AI4SCI_START_EPOCH

# AI4SCI_SEED 缺省 42,是 results.json 里记的 seed;内部 seed 只是从它派生出来跑多起点。
OUTER_SEED="${AI4SCI_SEED:-42}"

for ((i = 0; i < INNER_K; i++)); do
  inner_seed=$((OUTER_SEED + 100 * i))
  AI4SCI_SEED="$inner_seed" AI4SCI_BUDGET_S="$INNER_BUDGET_S" "$AI4SCI_PYTHON" code/optimize.py
  mv params.json "params_${i}.json"
done

AI4SCI_SEED="$OUTER_SEED" AI4SCI_INNER_K="$INNER_K" "$AI4SCI_PYTHON" harness/evaluate.py
