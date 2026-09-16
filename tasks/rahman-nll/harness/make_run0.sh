#!/usr/bin/env bash
# 复现 run_0/：基线一次 + repeat_k(5) 次重复 + sigma.json。run_0 是改进率的分母，也是统计门的基线。
set -euo pipefail
TASK_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$TASK_DIR"
export AI4SCI_PYTHON="${AI4SCI_PYTHON:-$TASK_DIR/.venv/bin/python}"
if [ ! -x "$AI4SCI_PYTHON" ]; then
  echo "make_run0: 任务环境不存在：$AI4SCI_PYTHON（先跑 ai4sci task env build $TASK_DIR）" >&2
  exit 1
fi
SEEDS=(42 43 44 45 46)   # 与 manifest.budget.repeat_k=5 对应
BASE_SEED=42
rm -rf run_0
mkdir -p run_0/repeats
AI4SCI_SEED="$BASE_SEED" harness/launcher.sh
cp results.json run_0/results.json
for seed in "${SEEDS[@]}"; do
  AI4SCI_SEED="$seed" harness/launcher.sh
  cp results.json "run_0/repeats/results-${seed}.json"
done
# sigma 用样本标准差（n-1），纯标准库算，每个指标一条
"$AI4SCI_PYTHON" - <<'PY'
import json
import statistics
from pathlib import Path

run0 = Path("run_0")
docs = [json.loads(p.read_text(encoding="utf-8")) for p in sorted(run0.glob("repeats/results-*.json"))]
docs.sort(key=lambda d: d["seed"])
seeds = [d["seed"] for d in docs]
sigma = {}
for name in docs[0]["metrics"]:
    values = [d["metrics"][name] for d in docs]
    sigma[name] = {"sigma": statistics.stdev(values) if len(values) > 1 else 0.0,
                   "seeds": seeds, "values": values}
(run0 / "sigma.json").write_text(json.dumps(sigma), encoding="utf-8")
print("sigma.json:", {k: round(v["sigma"], 6) for k, v in sigma.items()})
PY
rm -f params_*.json results.json
echo "run_0 就绪"
