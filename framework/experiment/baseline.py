"""跑基线：设计阶段两颗能力共用的后半段——起 `harness/make_run0.sh` 出 baseline/，跑完机器预检。

为什么不让人直接 `bash harness/make_run0.sh`：launcher 从 AI4SCI_BUDGET_S / AI4SCI_INNER_K 读数，
人手工起就得自己想着导出，忘了就是一次"看着像跑了"的基线。这里把两处的环境收成一处
（`experiment.env.harness_env`），基线和内环跑的是同一份约定。

跑完不停下来等人看基线：原来那个人工停点看的三四个数（基线、σ、门、尽头）机器能算
（`experiment.headroom`），判无解就抛并说清，否则把数字写在结论行里。

baseline/ 整个是这一次 make_run0.sh 的产物：跑之前把本地那份删干净，跑完拿回来的才是全部，
拿回来先按开跑的那套合约（`pack.validate_pack` 查全）核一遍——「design ok」就等于
auto-research 会接。第一轮真任务里远端脚本自己 rm -rf 了 baseline/，但拿回来（`get`）只加不删，
上一版基线的 5 个 results-<seed>.json 留在本地 repeats/ 里，人签了字、实验阶段一数文件就拒开。

σ（baseline/sigma.json）由框架从 repeats/ 算（`pack.write_sigma`），不由 make_run0.sh 算：执行层
各算各的，两轮演练都错在 seeds 列表这种细节上，基线跑两个半小时再为它被拒一次不值。
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

from compute import Compute
from framework import paths
from framework.contracts.capability import CapabilityFailed
from framework.experiment import env, headroom
from framework.experiment import pack as packs

# 基线的墙钟上限：make_run0 跑 1 + repeat_k 次，每次 wall_clock_s；给足再加一截
BASELINE_TIMEOUT_RATIO = 1.5


def run_baseline(pack: Path, compute: Compute, *, check_headroom: bool = True) -> str:
    """在 `compute` 上跑基线：那包同步过去 → 那边按 env/ 建 venv → 起 make_run0.sh → 回来 → 预检；
    跑完返回结论行的尾巴（inner_k 与预检摘要）；跑不了、预检没过就抛 CapabilityFailed。
    本机算力时「过去」「回来」都是同一个目录，什么都不搬（P-23：远端只跑 harness）。

    `check_headroom=False` 是复现那颗能力的读取点：基线就是复现结果，「离尽头不够一个门就无解」
    对它不成立（数对上才是目的），预检只算数字不判死。"""
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
    stale = pack / packs.BASELINE_DIRNAME
    if stale.is_dir():
        shutil.rmtree(stale)  # 本机算力时和远端是同一个目录，删一次就够
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
    # σ 框架自己从 repeats 算（脚本算的一律覆盖）；算不了就是 repeats 有问题，下面的校验会说清
    packs.write_sigma(pack, scoring)
    problems = packs.validate_pack(pack, paths.domains_root())
    if problems:
        raise CapabilityFailed("基线跑完了，那包不合约（实验阶段会拒开）：\n" + "\n".join(problems))
    try:
        room = headroom.assess(pack)
    except FileNotFoundError as exc:
        raise CapabilityFailed(str(exc)) from exc
    problems = room.problems() if check_headroom else []
    if problems:
        raise CapabilityFailed("基线跑完了，预检没过：\n" + "\n".join(problems)
                               + f"\n{room.summary()}")
    return f"inner_k={inner_k}\t{room.summary()}"
