# design.md · 产物契约与基线策略

玩具任务（外层 #21），harness 与 code 是手写的；这份是补写的「怎么算好」，发布（`ai4sci task publish`）签的就是它和 manifest。

## code/train.py 产出什么

写 `predictions.json` 到任务根：`{"y_pred": [<验证集逐点预测>]}`，长度等于 `data/` 里验证集的点数。种子从 `AI4SCI_SEED` 读（缺省 42），预算从 `AI4SCI_BUDGET_S` 读、只花 80%，按墙钟自截断。只读 `data/`，不写 `results.json`。

## harness/evaluate.py 查什么

读 `predictions.json`（缺失或不是 JSON 退 2），长度与验证集对不上退 3，有非有限数退 4，拿不到 `AI4SCI_START_EPOCH` 退 5。用 `data/` 的真值重算验证集 MSE，写 `{"metrics": {"val_mse": <float>}, "elapsed_s": <float>, "seed": <int>, "status": "ok"}`。

## 基线策略

单隐层 MLP、固定超参、纯 numpy，故意留着调参空间。`make_run0.sh` 种子 42 43 44（与 `repeat_k: 3` 对应）。
