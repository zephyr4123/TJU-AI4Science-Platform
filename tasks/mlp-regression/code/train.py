"""基线：纯 Python 单隐层 MLP（1 → 16 → 1，tanh，逐样本 SGD）。

这是执行层唯一能改的文件。单入口、参数全在顶上，改哪里一眼能看见。

约定（改的时候别破坏）：
  * 只读 data/train.json 与 data/val_inputs.json；data/val.json 里的真值归 harness，
    自己算分等于自己给自己打分（P-2），框架会当作假成功处理。
  * 只写 predictions.json 与 timing.json，不写 results.json。
  * 种子从环境变量 AI4SCI_SEED 来，预算从 AI4SCI_BUDGET_S 来；跑到预算 80% 就收工，
    让 harness 有时间评分（packs.md §2 的 harness 接口约束）。
零依赖是硬要求：不许 import numpy 之类，任务包要能在裸 python3 上跑。
"""

import json
import math
import os
import random
import time
from pathlib import Path

# ---------------- 可调参数：调参就改这几行 ----------------
HIDDEN = 16  # 隐层宽度
LEARNING_RATE = 0.05  # SGD 步长
EPOCHS = 400  # 最多训练多少轮，实际可能被预算提前掐断
INIT_SCALE = 1.0  # 初始权重的均匀分布半宽
# --------------------------------------------------------

DEFAULT_SEED = 42
DEFAULT_BUDGET_S = 30.0
BUDGET_USE_RATIO = 0.8  # 只花预算的 80%，剩下的留给评分

TASK_DIR = Path(__file__).resolve().parent.parent


def _env_int(name: str, default: int) -> int:
    """读整数环境变量；写错了就当场退出，不静默用默认值（P-7）。"""
    raw = os.environ.get(name)
    if raw is None or raw == "":
        return default
    try:
        value = int(raw)
    except ValueError as exc:
        raise SystemExit(f"{name} 期望整数，实际 {raw!r}") from exc
    assert isinstance(value, int), f"{name} 解析后应为 int，实际 {type(value).__name__}"
    return value


def _env_float(name: str, default: float) -> float:
    raw = os.environ.get(name)
    if raw is None or raw == "":
        return default
    try:
        value = float(raw)
    except ValueError as exc:
        raise SystemExit(f"{name} 期望数字，实际 {raw!r}") from exc
    if not math.isfinite(value) or value <= 0:
        raise SystemExit(f"{name} 期望正的有限数，实际 {value!r}")
    return value


def _load(path: Path) -> dict:
    if not path.is_file():
        raise SystemExit(f"数据文件缺失：{path}")
    return json.loads(path.read_text(encoding="utf-8"))


class MLP:
    """1 → HIDDEN → 1，隐层 tanh，输出线性。权重用列表存，够小不需要矩阵库。"""

    def __init__(self, hidden: int, rng: random.Random) -> None:
        self.w1 = [rng.uniform(-INIT_SCALE, INIT_SCALE) for _ in range(hidden)]
        self.b1 = [rng.uniform(-INIT_SCALE, INIT_SCALE) for _ in range(hidden)]
        self.w2 = [rng.uniform(-INIT_SCALE, INIT_SCALE) for _ in range(hidden)]
        self.b2 = 0.0

    def forward(self, x: float) -> tuple[float, list[float]]:
        hidden = [math.tanh(self.w1[j] * x + self.b1[j]) for j in range(len(self.w1))]
        out = sum(self.w2[j] * hidden[j] for j in range(len(hidden))) + self.b2
        return out, hidden

    def predict(self, x: float) -> float:
        return self.forward(x)[0]

    def sgd_step(self, x: float, y: float, lr: float) -> None:
        """一条样本一次更新，损失 (out - y)^2 的解析梯度。"""
        out, hidden = self.forward(x)
        d_out = 2.0 * (out - y)
        for j in range(len(hidden)):
            d_hidden = d_out * self.w2[j]
            d_pre = d_hidden * (1.0 - hidden[j] * hidden[j])  # tanh' = 1 - tanh^2
            self.w2[j] -= lr * d_out * hidden[j]
            self.w1[j] -= lr * d_pre * x
            self.b1[j] -= lr * d_pre
        self.b2 -= lr * d_out


def main() -> None:
    started = time.time()
    seed = _env_int("AI4SCI_SEED", DEFAULT_SEED)
    budget_s = _env_float("AI4SCI_BUDGET_S", DEFAULT_BUDGET_S)
    deadline = started + budget_s * BUDGET_USE_RATIO

    train = _load(TASK_DIR / "data" / "train.json")
    val_inputs = _load(TASK_DIR / "data" / "val_inputs.json")
    xs, ys = train["x"], train["y"]
    assert len(xs) == len(ys), f"train.json 的 x 与 y 长度不一致：{len(xs)} vs {len(ys)}"

    rng = random.Random(seed)
    model = MLP(HIDDEN, rng)
    order = list(range(len(xs)))

    epochs_done = 0
    stop_reason = "epochs"
    for _ in range(EPOCHS):
        if time.time() >= deadline:
            stop_reason = "budget"  # 到 80% 预算优雅停，不是崩，也不是超时
            break
        rng.shuffle(order)
        for i in order:
            model.sgd_step(xs[i], ys[i], LEARNING_RATE)
        epochs_done += 1

    preds = [model.predict(x) for x in val_inputs["x"]]
    (TASK_DIR / "predictions.json").write_text(json.dumps({"y_pred": preds}), encoding="utf-8")
    train_wall_s = time.time() - started
    (TASK_DIR / "timing.json").write_text(
        json.dumps({"train_wall_s": train_wall_s, "epochs_done": epochs_done, "seed": seed}),
        encoding="utf-8",
    )
    print(
        f"seed={seed} epochs={epochs_done}/{EPOCHS} stop={stop_reason} "
        f"train_wall_s={train_wall_s:.2f} 写出 {len(preds)} 条预测"
    )


if __name__ == "__main__":
    main()
