# 任务：把论文自己的代码原样跑起来，算出论文报的那几个数

你在一个科研自动化平台的**设计产出目录**里工作，这一次是**复现一篇论文**：不写训练代码、不改方法，只让上游代码在这台机器上跑起来，把它的输出算成论文报的数。目录里已经有：

- `code/`：$upstream 这是别人的仓库，先读它的 README、入口脚本、配置文件，弄清怎么跑、跑完输出什么、在哪。
- `data/`：研究者带来的其它原件（数据、论文解析出来的 `paper.md` / `structured.json` 之类，可能为空）。
- `env/`：平台按它建环境（按上游的 requirements 算的清单，或机器上现成的解释器）。

你要写四个文件：

- `scoring.yaml`：评分契约——指标就是论文报的那几个数，`attainable` 填论文值（形状见下）
- `harness/launcher.sh`：唯一执行入口，清产物 → 按论文的配置起 `code/` → 跑 evaluate.py
- `harness/evaluate.py`：读上游代码的输出，按论文的定义算指标，写 results.json
- `harness/make_run0.sh`：跑一次基线 + `repeat_k` 次重复 + σ → `baseline/`

## 硬规矩

1. **只写 `scoring.yaml`、`harness/` 与 `code/` 下的文件。** 不碰 `data/`、`env/`。不写 `harness/SHA256SUMS`（框架生成）。
2. **`code/` 尽量不改。** 复现的意义在「原样」。老代码跑不起来时（路径写死、API 过时、缺一个文件）允许最小的改动，每处改动在收尾自述里说清改了什么、为什么；框架会把 `code/` 相对上游的 diff 留档给研究者看。**不许改方法、超参、评测定义、随机种子的语义**——那不是修复，是另一个实验。
3. 你不能运行代码。你能运行的命令只有文末工具包里的 `ai4sci skill …`；写完由框架改权限、算校验和、跑 lint、跑校验、在算力上跑一次，报错会喂回给你。每一行想清楚再写，宁可简单。
4. 脚本里起 Python 只准写 `"$$AI4SCI_PYTHON"`，绝不能写裸 `python` / `python3`：任务跑在平台建的环境里，这个变量由框架或 make_run0.sh 给。上游代码里自己 `subprocess` 起 `python` 的地方由它去。
5. `evaluate.py` 是评分脚本：**指标必须由它按论文的定义从上游的输出重算**（预测文件、日志里的最终数、保存的表），不许信上游 stdout 打印的一句话；算不出来就拒收。
6. 拒收产物（文件缺失、形状不对、NaN、越界）时：打一句话到 stderr，`raise SystemExit(非零)`，**不写 results.json，不抛 traceback**。
7. 注释用中文，写"为什么"，不复述代码在做什么。文件短、单入口、可调参数集中放顶上并注明含义。
8. 行宽不超过 $lint_line_length 列，`harness/` 下的 Python 要过 ruff（规则集 $lint_select）：import 按 isort 排序、没有未用的 import、不许裸 except。`code/` 不查 lint。
9. 缺东西（数据要另外下载、要 API key、要 GPU 而这台机器没有、上游依赖 env/ 里没有）就**别硬凑**：把缺什么写在收尾自述里，让研究助理去补；密钥永远不写进任何文件，脚本从环境变量读，拿不到就停。

## 平台契约（所有任务一样）

- `scoring.yaml` 的形状（YAML，只有这些键）：

  ```yaml
  format_version: 1
  metrics:
    - {name: <论文里那个数的名字>, direction: minimize|maximize, primary: true, attainable: <论文报的值>}
    - {name: <论文里另一个数>, direction: maximize, attainable: <论文值>}     # 可以多个，只记录
  budget:
    wall_clock_s: <上游代码跑一次要多久，秒；按 README / 论文写的时间给足，宁多勿少>
    max_iterations: 1
    repeat_k: <论文种子数 − 1（论文报 5 个种子就 4）；论文没写种子才按时间定：跑一次几分钟就 2 或 3，要几小时就 1>
    accept_sigma: 2.0
    inner_k: 1
  requirements:
    - {id: R1, type: numeric, must_pass: true, description: <一句话：主指标与论文值差距在需求给的容差内>}
  ```

  `attainable` 是论文值，框架把它和跑出来的数并排给研究者看；对没对上由研究者判，你不用写判定逻辑。

- `results.json` 写在目录根，形状固定，`metrics` 必须包含 scoring.yaml 声明的**每一个**指标：

  ```json
  {"metrics": {"<指标名>": <有限数>}, "elapsed_s": <float>, "seed": <int>, "status": "ok"}
  ```

- 框架起 launcher 时**保证**给出四个环境变量，harness 拿不到就必须停，**不许写默认值**（`os.environ.get(名字, 默认)`、`$${名字:-默认}` 一律不许；框架校验会抓）：
  - `AI4SCI_PYTHON`：解释器。
  - `AI4SCI_BUDGET_S`：一次跑的墙钟预算，等于 scoring.yaml 的 `wall_clock_s`。上游代码不认预算就只用它当超时（`timeout` 命令）。
  - `AI4SCI_INNER_K`：评分内部重复次数，等于 `budget.inner_k`；复现写 1，launcher 照它循环即可。
  - `AI4SCI_START_EPOCH`：launcher 起跑时自己设，evaluate.py 用它算 `elapsed_s`。
- **种子照论文。** 论文（或它的 README / 需求）报了哪几个种子就跑哪几个：`AI4SCI_SEED` 是唯一允许缺省的，缺省是**论文的第一个种子**（论文没写种子才用 42）；上游代码认种子就把它传进去（命令行参数或环境变量，按它的写法）；不认就照原样跑，重复之间的差异就是它自己的随机性。
- `make_run0.sh`：基线一次（论文的第一个种子）+ `budget.repeat_k` 次重复（论文其余的种子，`repeat_k` = 论文种子数 − 1；论文没写种子才 42、43 … 往上数）+ `baseline/sigma.json`，σ 是样本标准差，**每个指标一条**：`{"<指标名>": {"sigma": <float>, "seeds": [...], "values": [...]}}`。**不许把论文的种子换成平台的**——换了就不是原样重跑，对不上时也说不清是种子还是别的。
- evaluate.py 退出码：0 正常；2 产物缺失或读不出；3 形状 / 长度对不上；4 NaN / Inf / 越界；5 计时缺失。

## 研究需求（研究者与助理对齐并确认过的：哪篇论文、哪几个数、复现到第几级、对上的标准）

$requirement

## 材料来源（文献阶段：助理找到了什么、选了哪个、为什么）

$sources

## 工具链

领域的库怎么用在文末工具包里对应的 skill 里：先 `ai4sci skill show <name>` 读完再写；拿不准就联网查（见文末）。上游代码的用法以它自己的 README 与源码为准。

## 参考骨架（形状照抄，内容按上游代码改）

### harness/launcher.sh

```bash
#!/usr/bin/env bash
# 唯一执行入口：清上一轮的产物 → 按论文的配置起上游代码 → 评分。"results.json 存在"永远等于"这一轮真跑出了成绩"。
set -euo pipefail
: "$${AI4SCI_PYTHON:?未设 AI4SCI_PYTHON}"
: "$${AI4SCI_BUDGET_S:?未设 AI4SCI_BUDGET_S}"
: "$${AI4SCI_INNER_K:?未设 AI4SCI_INNER_K}"
TASK_DIR="$$(cd "$$(dirname "$${BASH_SOURCE[0]}")/.." && pwd)"
cd "$$TASK_DIR"
SEED="$${AI4SCI_SEED:-42}"
rm -rf outputs results.json          # 上游代码的输出目录按它的写法改
AI4SCI_START_EPOCH="$$("$$AI4SCI_PYTHON" -c 'import time; print(time.time())')"
export AI4SCI_START_EPOCH
# 按论文的配置起上游代码：入口、参数、种子照它的 README；超过预算就杀
( cd code && timeout "$${AI4SCI_BUDGET_S%.*}" "$$AI4SCI_PYTHON" <入口>.py --seed "$$SEED" <论文里的参数> )
"$$AI4SCI_PYTHON" harness/evaluate.py
```

### harness/make_run0.sh

```bash
#!/usr/bin/env bash
# 复现结果：基线一次 + repeat_k 次重复 + σ。
set -euo pipefail
TASK_DIR="$$(cd "$$(dirname "$${BASH_SOURCE[0]}")/.." && pwd)"
cd "$$TASK_DIR"
export AI4SCI_PYTHON="$${AI4SCI_PYTHON:-$$TASK_DIR/.venv/bin/python}"
: "$${AI4SCI_BUDGET_S:?未设 AI4SCI_BUDGET_S：经 ai4sci cap reproduction 起}"
: "$${AI4SCI_INNER_K:?未设 AI4SCI_INNER_K：经 ai4sci cap reproduction 起}"
if [ ! -x "$$AI4SCI_PYTHON" ]; then
  echo "make_run0: 任务环境不存在：$$AI4SCI_PYTHON" >&2
  exit 1
fi
SEEDS=(43 44)   # 与 scoring.budget.repeat_k 对应；改一处就要改另一处
rm -rf baseline
mkdir -p baseline/repeats
AI4SCI_SEED=42 harness/launcher.sh
cp results.json baseline/results.json
for seed in "$${SEEDS[@]}"; do
  AI4SCI_SEED="$$seed" harness/launcher.sh
  cp results.json "baseline/repeats/results-$${seed}.json"
done
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
rm -rf outputs results.json
echo "baseline 就绪"
```

### harness/evaluate.py（骨架）

```python
"""评分脚本：只吃上游代码的输出文件，按论文的定义算指标，写 results.json。非零退出一律不写 results.json。"""

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


def _elapsed_s() -> float:
    start = os.environ.get("AI4SCI_START_EPOCH")
    if start is None:
        _fail(5, "拿不到 AI4SCI_START_EPOCH，不填 0 假装量过")
    return time.time() - float(start)


def main() -> None:
    # …读 code/ 跑出来的输出文件（2 缺失）、查形状（3）、查有限与边界（4），按论文的定义算指标…
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

写完后用四行自述结束：写了哪几个文件；`code/` 改了哪几处、为什么（没改就写「没改」）；缺什么（数据、密钥、算力、依赖）要研究助理去补；你不确定的地方，建议框架校验时重点看什么。
