#!/usr/bin/env bash
# 复现 run_0/:基线一次 + repeat_k 次重复 + σ。改了 code/optimize.py 或 data/ 后重跑它。
# run_0 是改进率的分母,也是统计门(accept_sigma、min_delta)的基线。
set -euo pipefail

TASK_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$TASK_DIR"

# 任务自带环境:缺省用 ai4sci task env build 建出来的 .venv,没有就明确报错,不碰平台 venv
export AI4SCI_PYTHON="${AI4SCI_PYTHON:-$TASK_DIR/.venv/bin/python}"
if [ ! -x "$AI4SCI_PYTHON" ]; then
  echo "make_run0: 任务环境不存在:$AI4SCI_PYTHON(先跑 ai4sci task env build $TASK_DIR)" >&2
  exit 1
fi

SEEDS=(42 43 44)   # 与 manifest.budget.repeat_k=3 对应,改一处就要改另一处
BASE_SEED=42

rm -rf run_0
mkdir -p run_0/repeats

AI4SCI_SEED="$BASE_SEED" harness/launcher.sh
cp results.json run_0/results.json

for seed in "${SEEDS[@]}"; do
  AI4SCI_SEED="$seed" harness/launcher.sh
  cp results.json "run_0/repeats/results-${seed}.json"
done

# σ 用样本标准差(n-1),纯标准库算;manifest 里的每个指标(nll_mean/nll_min/nll_max)各算一条。
"$AI4SCI_PYTHON" - <<'PY'
import json
import statistics
from pathlib import Path

run0 = Path("run_0")
seeds = []
metric_values = {"nll_mean": [], "nll_min": [], "nll_max": []}
for path in sorted(run0.glob("repeats/results-*.json")):
    doc = json.loads(path.read_text(encoding="utf-8"))
    seeds.append(doc["seed"])
    for name in metric_values:
        metric_values[name].append(doc["metrics"][name])

order = sorted(range(len(seeds)), key=lambda i: seeds[i])
seeds = [seeds[i] for i in order]

sigma = {}
for name, values in metric_values.items():
    values = [values[i] for i in order]
    stdev = statistics.stdev(values) if len(values) > 1 else 0.0
    sigma[name] = {"sigma": stdev, "seeds": seeds, "values": values}
    print(f"sigma.json: {name} sigma={stdev:.6g} seeds={seeds}")

(run0 / "sigma.json").write_text(json.dumps(sigma), encoding="utf-8")
PY

rm -f params.json params_*.json results.json
echo "run_0 就绪"
