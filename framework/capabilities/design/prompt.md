# 任务：按需求写评分契约、评分脚本与基线代码

你在一个科研自动化平台的**设计产出目录**里工作。目录里已经有 `data/`（研究者带来的原件：数据、代码、文档，可能为空）、`env/`（依赖清单，平台按它建 venv）。研究需求在下面原文给你。你要写五个文件：

- `scoring.yaml`：评分契约——指标、方向、预算、统计门（形状见下）
- `harness/launcher.sh`：唯一执行入口，清产物 → 跑 code/ → 跑 evaluate.py
- `harness/evaluate.py`：评分脚本，读产物、用 `data/` 重算指标、写 results.json
- `harness/make_run0.sh`：跑出基线 + 重复 + σ → `baseline/`
- `code/<入口>.py`：基线；以后由另一个 agent 逐轮改它

## 硬规矩

1. **只写 `scoring.yaml`、`harness/` 与 `code/` 下的文件。** 不碰 `data/`、`env/`。不写 `harness/SHA256SUMS`（框架生成）。
2. 你这个会话没有 Bash，不能运行代码。写完之后由框架改权限、算校验和、跑 lint、跑校验，报错会喂回给你。每一行想清楚再写，宁可简单。
3. 脚本里起 Python 只准写 `"$$AI4SCI_PYTHON"`，绝不能写裸 `python` / `python3`：任务跑在自己的 venv 里，这个变量由框架或 make_run0.sh 给。
4. `evaluate.py` 是评分脚本：**指标必须由它用 `data/` 重算**，不许读 `code/` 自己报的分数；`code/` 只产出产物文件。
5. 拒收产物（文件缺失、形状不对、NaN、越界）时：打一句话到 stderr，`raise SystemExit(非零)`，**不写 results.json，不抛 traceback**。
6. 注释用中文，写"为什么"，不复述代码在做什么。文件短、单入口、可调参数集中放顶上并注明含义。不写没人用的函数。
7. 行宽不超过 $lint_line_length 列，`harness/` 下的 Python 要过 ruff（规则集 $lint_select）：import 按 isort 排序、没有未用的 import、不许裸 except。`code/` 不查 lint。

## 平台契约（所有任务一样）

- `scoring.yaml` 的形状（YAML，只有这些键；数值按需求定，定不了的问题写在收尾自述里）：

  ```yaml
  format_version: 1
  metrics:
    - {name: <指标名>, direction: minimize|maximize, primary: true}   # 恰好一个 primary
    - {name: <另一个指标>, direction: minimize}                        # 可以多个，只记录
  budget:
    wall_clock_s: <一次跑的墙钟预算，秒>
    max_iterations: <最多改几轮>
    repeat_k: <基线重复几次算 σ>
    accept_sigma: <差值要超过几倍 σ 才算改进>
    min_delta: <σ 为 0 时的最小改进量，可省>
    inner_k: <评分脚本内部跑几次取均值，可省，缺省 1>
  requirements:            # 机器判的验收条件，可以为空列表
    - {id: R1, type: numeric, must_pass: true, description: <一句话>}
  ```

- `results.json` 写在目录根，形状固定，`metrics` 必须包含 scoring.yaml 声明的**每一个**指标：

  ```json
  {"metrics": {"<指标名>": <有限数>}, "elapsed_s": <float>, "seed": <int>, "status": "ok"}
  ```

- 框架起 launcher 时**保证**给出四个环境变量，harness 拿不到就必须停，**不许写默认值**（`os.environ.get(名字, 默认)`、`$${名字:-默认}` 一律不许；框架校验会抓）：
  - `AI4SCI_PYTHON`：解释器。
  - `AI4SCI_BUDGET_S`：一次跑的墙钟预算，等于 scoring.yaml 的 `wall_clock_s`。评分内部重复 K 次时，launcher 用它除以 K 得到每次的份额再传给 `code/`；`code/` 只花份额的 80%，按墙钟自截断，不按常数反推工作量。
  - `AI4SCI_INNER_K`：评分内部重复次数，等于 scoring.yaml 的 `budget.inner_k`（不写就是 1）。launcher 照它循环，并原样传给 evaluate.py；**不要在脚本里写死这个数**。
  - `AI4SCI_START_EPOCH`：launcher 起跑时自己设，evaluate.py 用它算 `elapsed_s`。
- `AI4SCI_SEED` 是唯一允许缺省的：缺省 42，同一 seed 必须复现同一结果。
- `make_run0.sh`：基线一次（seed 42）+ scoring `budget.repeat_k` 次重复（seed 42、43、44 …）+ `baseline/sigma.json`，σ 是样本标准差，**每个指标一条**：`{"<指标名>": {"sigma": <float>, "seeds": [...], "values": [...]}}`。
- evaluate.py 退出码：0 正常；2 产物缺失或读不出；3 形状 / 长度对不上；4 NaN / Inf / 越界；5 计时缺失。

## 研究需求（研究者与助理对齐并确认过的，照它做：要优化什么、数据在哪、怎么算好、花多少）

$requirement

$hypothesis

## 工具链（在任务的 venv 里实测过的 API；没写的不要猜）

$skills

## 参考骨架（形状照抄，内容按本任务改）

### harness/launcher.sh

```bash
#!/usr/bin/env bash
# 唯一执行入口：先清干净上一轮的产物，再跑基线、再评分——"results.json 存在"永远等于"这一轮真跑出了成绩"。
set -euo pipefail
# 三个保证变量拿不到就停在这里，不兜底（框架与 ai4sci cap design 都会给）
: "$${AI4SCI_PYTHON:?未设 AI4SCI_PYTHON}"
: "$${AI4SCI_BUDGET_S:?未设 AI4SCI_BUDGET_S}"
: "$${AI4SCI_INNER_K:?未设 AI4SCI_INNER_K}"
TASK_DIR="$$(cd "$$(dirname "$${BASH_SOURCE[0]}")/.." && pwd)"
cd "$$TASK_DIR"
rm -f <产物文件> results.json
AI4SCI_START_EPOCH="$$("$$AI4SCI_PYTHON" -c 'import time; print(time.time())')"
export AI4SCI_START_EPOCH
# inner_k 为 1 时就是一次；大于 1 时按它循环，每次预算 = AI4SCI_BUDGET_S / AI4SCI_INNER_K，产物按序号改名
"$$AI4SCI_PYTHON" code/<入口>.py
"$$AI4SCI_PYTHON" harness/evaluate.py
```

### harness/make_run0.sh

```bash
#!/usr/bin/env bash
# 复现 baseline/：基线一次 + repeat_k 次重复 + σ。baseline 是改进率的分母，也是统计门的基线。
set -euo pipefail
TASK_DIR="$$(cd "$$(dirname "$${BASH_SOURCE[0]}")/.." && pwd)"
cd "$$TASK_DIR"
# 由 ai4sci cap design 起：解释器、预算、inner_k 都从它来；这里只给解释器一个指向任务自己 .venv 的缺省
export AI4SCI_PYTHON="$${AI4SCI_PYTHON:-$$TASK_DIR/.venv/bin/python}"
: "$${AI4SCI_BUDGET_S:?未设 AI4SCI_BUDGET_S：经 ai4sci cap design 起}"
: "$${AI4SCI_INNER_K:?未设 AI4SCI_INNER_K：经 ai4sci cap design 起}"
if [ ! -x "$$AI4SCI_PYTHON" ]; then
  echo "make_run0: 任务环境不存在：$$AI4SCI_PYTHON（由 ai4sci cap design 建）" >&2
  exit 1
fi
SEEDS=(42 43 44)   # 与 scoring.budget.repeat_k 对应；改一处就要改另一处
BASE_SEED=42
rm -rf baseline
mkdir -p baseline/repeats
AI4SCI_SEED="$$BASE_SEED" harness/launcher.sh
cp results.json baseline/results.json
for seed in "$${SEEDS[@]}"; do
  AI4SCI_SEED="$$seed" harness/launcher.sh
  cp results.json "baseline/repeats/results-$${seed}.json"
done
# σ 用样本标准差（n-1），纯标准库算，每个指标一条
"$$AI4SCI_PYTHON" - <<'PY'
import json
import statistics
from pathlib import Path

run0 = Path("baseline")
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
rm -f <产物文件> results.json
echo "baseline 就绪"
```

### harness/evaluate.py（骨架）

```python
"""评测层：只吃产物文件，算分，写 results.json。非零退出一律不写 results.json。"""

import json
import os
import sys
import time
from pathlib import Path

TASK_DIR = Path(__file__).resolve().parent.parent
DEFAULT_SEED = 42


def _fail(code: int, message: str) -> None:
    print(f"evaluate: {message}", file=sys.stderr)
    raise SystemExit(code)


def _load(path: Path, code: int) -> dict:
    if not path.is_file():
        _fail(code, f"文件缺失：{path}")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except ValueError as exc:
        _fail(code, f"{path} 不是合法 JSON：{exc}")
    raise AssertionError("不可达")


def _elapsed_s() -> float:
    start = os.environ.get("AI4SCI_START_EPOCH")
    if start is None:
        _fail(5, "拿不到 AI4SCI_START_EPOCH，不填 0 假装量过")
    return time.time() - float(start)


def main() -> None:
    artifact = _load(TASK_DIR / "<产物文件>", 2)
    # …按需求查形状（3）、查有限与边界（4），用 data/ 重算指标…
    metrics = {"<指标名>": 0.0}
    results = {"metrics": metrics, "elapsed_s": _elapsed_s(),
               "seed": int(os.environ.get("AI4SCI_SEED", DEFAULT_SEED)), "status": "ok"}
    (TASK_DIR / "results.json").write_text(json.dumps(results), encoding="utf-8")


if __name__ == "__main__":
    main()
```

## 现状

$current

$feedback

## 收尾

写完后用三行自述结束：写了哪几个文件；你不确定的地方（某个 API 的行为、某个边界）；建议框架校验时重点看什么。
