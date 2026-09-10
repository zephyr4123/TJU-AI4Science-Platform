#!/usr/bin/env bash
# 唯一执行入口：runner 在任务目录里无参执行它（packs.md §2）。
# 先清干净上一轮的产物，再训练、再评分——这样"results.json 存在"永远等于"这一轮真跑出了成绩"。
set -euo pipefail

TASK_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$TASK_DIR"

rm -f predictions.json timing.json results.json

# 整段墙钟从这里开始计，evaluate.py 读它写进 results.json 的 elapsed_s。
AI4SCI_START_EPOCH="$(python3 -c 'import time; print(time.time())')"
export AI4SCI_START_EPOCH

python3 code/train.py
python3 harness/evaluate.py
