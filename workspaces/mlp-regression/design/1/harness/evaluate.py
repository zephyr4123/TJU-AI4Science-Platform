"""评测层：只吃产物文件，算分，写 results.json（P-6）。

框架注入、执行层改不了（改了 SHA256SUMS 对不上，validate 与 runner 都会拦）。
输入只有两样：code/ 写出来的 predictions.json，与 data/val.json 里的真值。

elapsed_s 从哪来：launcher.sh 在起跑前把 epoch 写进环境变量 AI4SCI_START_EPOCH，
这里减一下就是"训练 + 评测"的整段墙钟，也就是 manifest.budget.wall_clock_s 要卡的那个数。
单独跑 evaluate.py（没有 launcher）时环境变量不在，退而读 code/ 写的 timing.json 里的
train_wall_s；两个都没有就报错退出，绝不填 0 假装量过。

退出码：0 正常；2 预测文件缺失或读不出；3 长度对不上；4 出现 NaN / Inf；5 计时缺失。
非零一律不写 results.json——没有 results.json 就是没有成绩，这是防假成功的最后一道。
"""

import json
import math
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
    raise AssertionError("不可达")  # _fail 一定抛，这行只为让类型检查闭合


def _elapsed_s() -> float:
    raw = os.environ.get("AI4SCI_START_EPOCH")
    if raw:
        try:
            started = float(raw)
        except ValueError:
            _fail(5, f"AI4SCI_START_EPOCH 期望数字，实际 {raw!r}")
        return max(0.0, time.time() - started)
    timing = TASK_DIR / "timing.json"
    if timing.is_file():
        value = json.loads(timing.read_text(encoding="utf-8")).get("train_wall_s")
        if isinstance(value, (int, float)) and math.isfinite(value) and value >= 0:
            return float(value)
    _fail(5, "拿不到墙钟：AI4SCI_START_EPOCH 未设且 timing.json 不可用")
    raise AssertionError("不可达")


def main() -> None:
    seed_raw = os.environ.get("AI4SCI_SEED", str(DEFAULT_SEED))
    try:
        seed = int(seed_raw)
    except ValueError:
        _fail(2, f"AI4SCI_SEED 期望整数，实际 {seed_raw!r}")

    preds_doc = _load(TASK_DIR / "predictions.json", 2)
    y_pred = preds_doc.get("y_pred") if isinstance(preds_doc, dict) else None
    if not isinstance(y_pred, list):
        _fail(2, "predictions.json 缺少数组字段 y_pred")

    val = _load(TASK_DIR / "data" / "val.json", 2)
    y_true = val["y"]
    if len(y_pred) != len(y_true):
        _fail(3, f"预测条数对不上：期望 {len(y_true)}，实际 {len(y_pred)}")

    for i, value in enumerate(y_pred):
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            _fail(4, f"predictions.json[{i}] 不是数字：{value!r}")
        if not math.isfinite(value):
            _fail(4, f"predictions.json[{i}] 是 NaN / Inf：{value!r}")

    val_mse = sum((p - t) ** 2 for p, t in zip(y_pred, y_true, strict=True)) / len(y_true)
    if not math.isfinite(val_mse):
        _fail(4, f"val_mse 不是有限数：{val_mse!r}")

    results = {
        "metrics": {"val_mse": val_mse},
        "elapsed_s": _elapsed_s(),
        "seed": seed,
        "status": "ok",
    }
    (TASK_DIR / "results.json").write_text(json.dumps(results), encoding="utf-8")
    print(f"val_mse={val_mse:.6f} seed={seed} elapsed_s={results['elapsed_s']:.2f}")


if __name__ == "__main__":
    main()
