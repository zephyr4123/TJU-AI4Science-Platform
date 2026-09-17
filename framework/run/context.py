"""跑一轮要的那份只读上下文：manifest 快照的读取点与全部取值断言。

在四层的 run 层。它回答的是"这个 run 是按什么配置跑的"，全部从 run 目录里的快照读，
不回头看任务包（纲领 workflow.md §1）。每个配置项在这里断言一次，非法值就抛，不静默
回落默认（P-7 / P-8）。

`TaskInvalid` 定义在这里而不是 `lifecycle.py`：建 run（校验不过）与载入上下文（σ 退化成
0）都要抛它，而 lifecycle 要用本模块的 `load_manifest`。异常放在被依赖的那一侧，两个
模块才能保持单向依赖 lifecycle → context，不必为一个异常绕出循环 import。
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from framework.run import layout

RUNS_ROOT_ENV = "AI4SCI_RUNS_ROOT"
WORKFLOWS_ROOT_ENV = "AI4SCI_WORKFLOWS_ROOT"
EXECUTOR_TIMEOUT_ENV = "AI4SCI_EXECUTOR_TIMEOUT_S"
DEFAULT_EXECUTOR_TIMEOUT_S = 900.0
DEFAULT_PATIENCE = 5  # manifest 不写 budget.patience 时的缺省（读取点在 load_context）
DEFAULT_MIN_DELTA = 0.0  # manifest 不写 budget.min_delta 时的缺省（读取点同上）
DEFAULT_INNER_K = 1  # manifest 不写 budget.inner_k 时的缺省：评分脚本内部只跑一次（读取点同上）
DIRECTIONS = ("minimize", "maximize")


class TaskInvalid(ValueError):
    """任务包不合契约，不给开跑（fail-closed，P-7）。"""


@dataclass
class RunContext:
    """跑一轮要的全部只读配置，全部从 run 目录里的快照读，不回头看任务包。"""

    run_dir: Path
    work: Path
    experiment: Path
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
    python: Path
    domain_extra: str


# --------------------------------------------------------------------------
# 配置读取点：每个都在这里断言一次，非法值就抛，不静默回落默认（P-7 / P-8）
# --------------------------------------------------------------------------
def default_runs_root() -> Path:
    """runs 根目录：环境变量 AI4SCI_RUNS_ROOT 优先，否则 <仓根>/runs。

    `parents[2]` 是 framework/run/context.py 往上三级，即仓根——搬包时这个数字要跟着改，
    所以它只在这一处出现。
    """
    raw = os.environ.get(RUNS_ROOT_ENV)
    root = Path(raw) if raw else Path(__file__).resolve().parents[2] / "runs"
    root.mkdir(parents=True, exist_ok=True)
    assert root.is_dir(), f"{RUNS_ROOT_ENV} 指向的不是目录：{root}"
    return root


def default_workflows_root() -> Path:
    """预装工作流的目录：AI4SCI_WORKFLOWS_ROOT 优先，否则 <仓根>/workflows（同上的 parents[2]）。"""
    raw = os.environ.get(WORKFLOWS_ROOT_ENV)
    root = Path(raw) if raw else Path(__file__).resolve().parents[2] / "workflows"
    assert root.is_dir(), f"{WORKFLOWS_ROOT_ENV} 指向的不是目录：{root}"
    return root


def executor_timeout_s() -> float:
    """执行层单轮墙钟上限（秒）。它与 harness 的预算是两根轴：改代码慢不等于跑得慢。"""
    raw = os.environ.get(EXECUTOR_TIMEOUT_ENV)
    value = DEFAULT_EXECUTOR_TIMEOUT_S if raw is None else float(raw)
    assert value > 0, f"{EXECUTOR_TIMEOUT_ENV} 必须是正数，得到 {value!r}"
    return value


def read_domain_extra(run_dir: Path) -> str:
    """执行层提示末尾的「领域约定」：领域包的能力追加段 + 全部 skill 正文，都从 run 内快照读。

    没有快照就是空串，调用方（prompting.build_prompt）见空串不追加。skill 文件与 Claude Code
    原生 SKILL.md 同格式，这里只取正文、去掉 frontmatter——那段元数据是给 CLI 索引用的，
    塞进 prompt 只会占地方。
    """
    parts: list[str] = []
    prompt = layout.domain_prompt(run_dir)
    if prompt.is_file():
        parts.append(prompt.read_text(encoding="utf-8").strip())
    for skill in sorted(layout.domain_skills(run_dir).glob("*.md")):
        body = strip_frontmatter(skill.read_text(encoding="utf-8")).strip()
        if body:
            parts.append(f"### skill: {skill.stem}\n\n{body}")
    return "\n\n".join(parts)


def strip_frontmatter(text: str) -> str:
    """去掉开头的 `---` … `---` 块；没有 frontmatter 原样返回。"""
    if not text.startswith("---"):
        return text
    end = text.find("\n---", 3)
    return text if end == -1 else text[end + 4 :]


def load_manifest(run_dir: Path) -> dict[str, Any]:
    """只读 run 目录里的 manifest 快照：跑起来后不再回头看任务包（纲领磁盘布局）。"""
    return yaml.safe_load(layout.manifest(run_dir).read_text(encoding="utf-8"))


def primary_metric(manifest: dict[str, Any]) -> dict[str, Any]:
    primary = [m for m in manifest["metrics"] if m.get("primary") is True]
    assert len(primary) == 1, f"manifest 必须恰好一个 primary 指标，实际 {len(primary)} 个"
    return primary[0]


def load_context(run_dir: Path) -> RunContext:
    """把 manifest 快照 + run_0 的 σ 与 seed 合成一份跑循环用的只读上下文。"""
    run_dir = Path(run_dir).resolve()
    manifest = load_manifest(run_dir)
    metric = primary_metric(manifest)
    budget = manifest["budget"]
    work = layout.work(run_dir)
    sigma_doc = json.loads((work / "run_0" / "sigma.json").read_text(encoding="utf-8"))
    seed = json.loads((work / "run_0" / "results.json").read_text(encoding="utf-8"))["seed"]
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
        # 那等于没有门。这时不猜一个默认值，停在门口让人显式给（P-7 fail-closed）。
        raise TaskInvalid(
            f"run_0 的重复跑完全一致，σ=0，统计门退化为 0"
            f"（accept_sigma={budget['accept_sigma']}）：请在 manifest 的 budget.min_delta 里"
            "显式给出最小改进量，或者把 run_0 重跑出真实的 σ"
        )
    python = layout.venv_python(run_dir)
    assert python.is_file(), (
        f"run 的任务环境不存在：{python}"
        "（run new 时应已建好；runs/ 被搬动或 .venv 被删就重建 run）"
    )
    return RunContext(
        run_dir=run_dir, work=work, experiment=layout.experiment(run_dir),
        ledger_path=layout.ledger(run_dir), question=manifest["question"],
        metric_name=metric["name"], direction=direction, sigma=sigma,
        accept_sigma=float(budget["accept_sigma"]), min_delta=min_delta,
        wall_clock_s=float(budget["wall_clock_s"]), inner_k=inner_k,
        max_iterations=int(budget["max_iterations"]), patience=patience, max_cost_usd=max_cost,
        seed=int(seed), python=python, domain_extra=read_domain_extra(run_dir),
    )
