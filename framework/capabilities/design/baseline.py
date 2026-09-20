"""跑基线：「写评分脚本、跑基线」的后半段——起 `harness/make_run0.sh` 出 baseline/，跑完机器预检。

为什么不让人直接 `bash harness/make_run0.sh`：launcher 从 AI4SCI_BUDGET_S / AI4SCI_INNER_K 读数，
人手工起就得自己想着导出，忘了就是一次"看着像跑了"的基线。这里把两处的环境收成一处
（`experiment.env.harness_env`），基线和内环跑的是同一份约定。

跑完不停下来等人看基线：原来那个人工停点看的三四个数（基线、σ、门、尽头）机器能算
（`experiment.headroom`），判无解就抛并说清，否则把数字写在结论行里。
"""

from __future__ import annotations

import sys
from pathlib import Path

from compute import Compute
from framework.contracts.capability import CapabilityFailed
from framework.experiment import env, headroom
from framework.experiment import pack as packs

# 基线的墙钟上限：make_run0 跑 1 + repeat_k 次，每次 wall_clock_s；给足再加一截
BASELINE_TIMEOUT_RATIO = 1.5


def run_baseline(pack: Path, compute: Compute) -> str:
    """在 `compute` 上跑基线：那包同步过去 → 那边按 env/ 建 venv → 起 make_run0.sh → 回来 → 预检；
    跑完返回结论行的尾巴（inner_k 与预检摘要）；跑不了、预检没过就抛 CapabilityFailed。
    本机算力时「过去」「回来」都是同一个目录，什么都不搬（P-23：远端只跑 harness）。"""
    pack = Path(pack).resolve()
    script = pack / "harness" / "make_run0.sh"
    if not script.is_file():
        raise CapabilityFailed("缺 harness/make_run0.sh：评分脚本还没写出来")
    scoring = packs.read_scoring(pack)
    budget = scoring.get("budget") if isinstance(scoring, dict) else None
    if not isinstance(budget, dict) or not isinstance(budget.get("wall_clock_s"), (int, float)):
        raise CapabilityFailed(f"{packs.SCORING_NAME} 缺 budget.wall_clock_s")
    inner_k = budget.get("inner_k", 1)
    if not isinstance(inner_k, int) or inner_k < 1:
        raise CapabilityFailed(
            f"{packs.SCORING_NAME} 的 budget.inner_k 要是正整数，实际 {inner_k!r}")
    repeat_k = budget.get("repeat_k", 3)
    remote = compute.remote_dir_for(pack)
    compute.sync(pack, remote)
    # 环境是基线的一部分，不是人要记得先跑的另一条命令；建不出来就是基线跑不了
    try:
        python = env.build_venv_on(compute, remote, f"{remote}/{env.VENV_DIRNAME}")
    except env.EnvBuildError as exc:
        raise CapabilityFailed(str(exc)) from exc
    harness_env = env.harness_env(Path(python), float(budget["wall_clock_s"]), inner_k)
    timeout_s = float(budget["wall_clock_s"]) * (1 + int(repeat_k)) * BASELINE_TIMEOUT_RATIO
    outcome = compute.run(remote, ["bash", "harness/make_run0.sh"], harness_env, timeout_s)
    # harness 的两路输出都走 stderr（诊断）：stdout 只留给协调层读的那一行结论（P-14）
    for text in (outcome.stdout, outcome.stderr):
        if text.strip():
            print(text.rstrip(), file=sys.stderr)
    compute.get(remote, pack)
    if not outcome.ok:
        raise CapabilityFailed(f"make_run0.sh 退出码 {outcome.exit_code}，基线不可信")
    try:
        room = headroom.assess(pack)
    except FileNotFoundError as exc:
        raise CapabilityFailed(str(exc)) from exc
    problems = room.problems()
    if problems:
        raise CapabilityFailed("基线跑完了，预检没过：\n" + "\n".join(problems)
                               + f"\n{room.summary()}")
    return f"inner_k={inner_k}\t{room.summary()}"
