"""生成 data/ 下的数据集，只在准备任务包时跑一次，产物提交进仓。

为什么放在 harness/ 而不是 code/：data/ 对执行层是只读的，谁生成它就该在执行层碰不到
的地方（packs.md §2）。种子写死，任何人重跑都得到同一份数据。

产物三份：
  train.json       训练集，code/ 读它
  val_inputs.json  验证集的 x（只有 x，没有 y），code/ 读它来产 predictions.json
  val.json         验证集的 x 与 y，只有 harness/evaluate.py 读——真值不进执行层的视野
"""

import json
import math
import random
from pathlib import Path

DATA_SEED = 20260910  # 数据集的种子，与训练种子 AI4SCI_SEED 是两回事，永不改
X_LOW, X_HIGH = -2.0, 2.0
NOISE_SIGMA = 0.1
N_TRAIN = 200
N_VAL = 100

DATA_DIR = Path(__file__).resolve().parent.parent / "data"


def truth(x: float) -> float:
    """真函数；噪声另加。"""
    return math.sin(3.0 * x) + 0.3 * x


def sample(rng: random.Random, n: int) -> tuple[list[float], list[float]]:
    xs = [rng.uniform(X_LOW, X_HIGH) for _ in range(n)]
    ys = [truth(x) + rng.gauss(0.0, NOISE_SIGMA) for x in xs]
    return xs, ys


def main() -> None:
    rng = random.Random(DATA_SEED)
    train_x, train_y = sample(rng, N_TRAIN)
    val_x, val_y = sample(rng, N_VAL)
    DATA_DIR.mkdir(exist_ok=True)
    _dump(DATA_DIR / "train.json", {"x": train_x, "y": train_y})
    _dump(DATA_DIR / "val_inputs.json", {"x": val_x})
    _dump(DATA_DIR / "val.json", {"x": val_x, "y": val_y})
    print(f"写好 {N_TRAIN} 个训练点、{N_VAL} 个验证点，种子 {DATA_SEED}")


def _dump(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")


if __name__ == "__main__":
    main()
