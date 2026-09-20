"""跑一轮要的那份只读上下文：scoring 快照的读取点与全部取值断言。

在实验族的共享层。它回答的是"这次实验是按什么配置跑的"，全部从实验产出目录里的快照读，
不回头看设计那包（纲领 workflow.md §1）。每个配置项在这里断言一次，非法值就抛，不静默
回落默认（P-7 / P-8）。

`PackInvalid` 定义在这里：开实验（校验不过）与载入上下文（σ 退化成 0）都要抛它。
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from framework.experiment import layout
from framework.experiment.checkpoint import read_checkpoint
from framework.experiment.pack import DEFAULT_DOMAIN, primary_metric, read_scoring

DEFAULT_PATIENCE = 5  # scoring 不写 budget.patience 时的缺省（读取点在 load_context）
DEFAULT_MIN_DELTA = 0.0  # scoring 不写 budget.min_delta 时的缺省（读取点同上）
DEFAULT_INNER_K = 1  # scoring 不写 budget.inner_k 时的缺省：评分脚本内部只跑一次（读取点同上）
DIRECTION_ZH = {"minimize": "越小", "maximize": "越大"}
DIRECTIONS = ("minimize", "maximize")


class PackInvalid(ValueError):
    """设计那包不合约，不给开跑（fail-closed，P-7）。"""


@dataclass
class RunContext:
    """跑一轮要的全部只读配置，全部从实验产出目录里的快照读，不回头看设计那包。"""

    run_dir: Path
    work: Path
    ledger_path: Path
    question: str
    metric_name: str
    direction: str
    sigma: float
    accept_sigma: float
    min_delta: float
    wall_clock_s: float
    inner_k: int
    max_iterations: int
    patience: int
    max_cost_usd: float | None
    seed: int
    python: str  # harness 的解释器：在跑实验的那台机器上的路径（checkpoint 记的）
    domain: str  # 设计时选的领域包：执行层的 skill 清单按它拼（纲领 P-22）
    domain_extra: str
    compute_name: str  # 在哪台机器上跑（checkpoint 记的名字），续跑要接同一台


# --------------------------------------------------------------------------
# 配置读取点：每个都在这里断言一次，非法值就抛，不静默回落默认（P-7 / P-8）
# --------------------------------------------------------------------------
def read_domain_extra(run_dir: Path) -> str:
    """执行层提示末尾的「领域约定」：领域包的实验追加段，从产出目录里的快照读。

    没有快照就是空串，调用方（prompting.build_prompt）见空串不追加。领域 skill 不在这里：
    它们走 `<available_skills>` 清单，执行层按需 `ai4sci skill show`（纲领 P-22）。
    """
    prompt = layout.domain_prompt(run_dir)
    return prompt.read_text(encoding="utf-8").strip() if prompt.is_file() else ""


def read_domain(run_dir: Path) -> str:
    """这次实验按哪个领域包开的：scoring 快照里的 `domain`（设计时 `--domain` 盖的章）。"""
    domain = load_scoring(run_dir).get("domain", DEFAULT_DOMAIN)
    assert isinstance(domain, str) and domain, f"scoring.domain 要是领域包名：{domain!r}"
    return domain


def load_scoring(run_dir: Path) -> dict[str, Any]:
    """只读实验产出目录里的 scoring 快照：跑起来后不再回头看设计那包（纲领磁盘布局）。"""
    return read_scoring(run_dir)


def read_question(run_dir: Path) -> str:
    """开实验时快照进来的需求原文：执行层提示里「这道题是什么」就抄它。"""
    return layout.requirement(run_dir).read_text(encoding="utf-8").strip()


def load_context(run_dir: Path) -> RunContext:
    """把 scoring 快照 + 基线的 σ 与 seed 合成一份跑循环用的只读上下文。"""
    run_dir = Path(run_dir).resolve()
    scoring = load_scoring(run_dir)
    metric = primary_metric(scoring)
    budget = scoring["budget"]
    work = layout.work(run_dir)
    base = layout.baseline(work)
    sigma_doc = json.loads((base / "sigma.json").read_text(encoding="utf-8"))
    seed = json.loads((base / "results.json").read_text(encoding="utf-8"))["seed"]
    patience = budget.get("patience", DEFAULT_PATIENCE)
    assert isinstance(patience, int) and patience >= 1, f"budget.patience 要是正整数：{patience!r}"
    inner_k = budget.get("inner_k", DEFAULT_INNER_K)
    assert isinstance(inner_k, int) and inner_k >= 1, f"budget.inner_k 要是正整数：{inner_k!r}"
    max_cost = budget.get("max_cost_usd")
    assert max_cost is None or max_cost > 0, f"budget.max_cost_usd 要是正数：{max_cost!r}"
    direction = metric["direction"]
    assert direction in DIRECTIONS, f"metrics.direction 只认 {DIRECTIONS}，实际 {direction!r}"
    sigma = float(sigma_doc[metric["name"]]["sigma"])
    min_delta = float(budget.get("min_delta", DEFAULT_MIN_DELTA))
    assert min_delta >= 0, f"budget.min_delta 要 >= 0：{min_delta!r}"
    if sigma == 0 and min_delta == 0:
        # σ 与最小改进量同时为 0，统计门就是 0，任何一点点差值都会被判成改进——
        # 那等于没有门。这时不猜一个默认值，直接失败让人显式给（P-7 fail-closed）。
        raise PackInvalid(
            f"基线的重复跑完全一致，σ=0，统计门退化为 0"
            f"（accept_sigma={budget['accept_sigma']}）：请在 scoring.yaml 的 budget.min_delta 里"
            "显式给出最小改进量，或者把基线重跑出真实的 σ"
        )
    state = read_checkpoint(run_dir)
    python = state.get("python")
    assert isinstance(python, str) and python, (
        "checkpoint 里没有 harness 的解释器路径（开实验时在算力上建环境后记的）：重开一次实验")
    if state.get("compute", {}).get("kind", "local") == "local":
        assert Path(python).is_file(), (
            f"实验的任务环境不存在：{python}"
            "（开实验时应已建好；目录被搬动或 .venv 被删就重开一次实验）"
        )
    return RunContext(
        run_dir=run_dir, work=work,
        ledger_path=layout.ledger(run_dir), question=read_question(run_dir),
        metric_name=metric["name"], direction=direction, sigma=sigma,
        accept_sigma=float(budget["accept_sigma"]), min_delta=min_delta,
        wall_clock_s=float(budget["wall_clock_s"]), inner_k=inner_k,
        max_iterations=int(budget["max_iterations"]), patience=patience, max_cost_usd=max_cost,
        seed=int(seed), python=python, domain=read_domain(run_dir),
        compute_name=str(state.get("compute", {}).get("name", "local")),
        domain_extra=read_domain_extra(run_dir),
    )
