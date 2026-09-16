#!/usr/bin/env bash
# 唯一执行入口：runner 在任务目录里无参执行它（packs.md §2）。
# 先清干净上一轮的产物，再训练、再评分——这样"results.json 存在"永远等于"这一轮真跑出了成绩"。
set -euo pipefail

# 任务跑在自己的 venv 里：解释器只从 AI4SCI_PYTHON 来（框架提交 harness 时设，make_run0.sh 缺省指到
# 任务目录的 .venv）。没设就停在这里，绝不退回到 PATH 上碰巧的那个 python3（packs.md §2）。
: "${AI4SCI_PYTHON:?未设 AI4SCI_PYTHON：先 ai4sci task env build <task_dir>，或由框架提交}"

TASK_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$TASK_DIR"

rm -f predictions.json timing.json results.json

# 整段墙钟从这里开始计，evaluate.py 读它写进 results.json 的 elapsed_s。
AI4SCI_START_EPOCH="$("$AI4SCI_PYTHON" -c 'import time; print(time.time())')"
export AI4SCI_START_EPOCH

"$AI4SCI_PYTHON" code/train.py
"$AI4SCI_PYTHON" harness/evaluate.py
