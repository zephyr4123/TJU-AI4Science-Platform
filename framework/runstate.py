"""一个 run 的磁盘状态：建 run、manifest 快照、checkpoint、跑循环要的那份上下文。

从 `loop.py` 分出来的理由只有一个：那边只该剩"一轮怎么走、什么时候停"。
这里的东西是**状态**，被 loop、resume、CLI 的 status 三处共用。

磁盘布局（纲领 workflow.md §1）：
    runs/<run_id>/ manifest.yaml checkpoint.json journal.md
                   work/（任务包拷贝，自己的 git 仓）
                   experiment/{ledger.tsv, stop.json, runs/run_N/}
"""

from __future__ import annotations

import json
import logging
import os
import shutil
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

from framework import gitwork, packs

LOGGER = logging.getLogger("ai4sci.loop")

RUNS_ROOT_ENV = "AI4SCI_RUNS_ROOT"
EXECUTOR_TIMEOUT_ENV = "AI4SCI_EXECUTOR_TIMEOUT_S"
DEFAULT_EXECUTOR_TIMEOUT_S = 900.0
DEFAULT_PATIENCE = 5  # manifest 不写 budget.patience 时的缺省（读取点在 load_context）
DEFAULT_MIN_DELTA = 0.0  # manifest 不写 budget.min_delta 时的缺省（读取点同上）
DIRECTIONS = ("minimize", "maximize")
# 拷贝任务包时不带过去的目录：.git 是别的仓的状态，.ai4sci 是执行层日志
IGNORED_DIRS = (".git", ".ai4sci", "__pycache__")


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
    max_iterations: int
    patience: int
    max_cost_usd: float | None
    seed: int
    domain_extra: str


# --------------------------------------------------------------------------
# 配置读取点：每个都在这里断言一次，非法值就抛，不静默回落默认（P-7 / P-8）
# --------------------------------------------------------------------------
def default_runs_root() -> Path:
    """runs 根目录：环境变量 AI4SCI_RUNS_ROOT 优先，否则 <仓根>/runs。"""
    raw = os.environ.get(RUNS_ROOT_ENV)
    root = Path(raw) if raw else Path(__file__).resolve().parent.parent / "runs"
    root.mkdir(parents=True, exist_ok=True)
    assert root.is_dir(), f"{RUNS_ROOT_ENV} 指向的不是目录：{root}"
    return root


def executor_timeout_s() -> float:
    """执行层单轮墙钟上限（秒）。它与 harness 的预算是两根轴：改代码慢不等于跑得慢。"""
    raw = os.environ.get(EXECUTOR_TIMEOUT_ENV)
    value = DEFAULT_EXECUTOR_TIMEOUT_S if raw is None else float(raw)
    assert value > 0, f"{EXECUTOR_TIMEOUT_ENV} 必须是正数，得到 {value!r}"
    return value


# --------------------------------------------------------------------------
# checkpoint：原子写，续跑只看它
# --------------------------------------------------------------------------
def read_checkpoint(run_dir: Path) -> dict[str, Any]:
    return json.loads((Path(run_dir) / "checkpoint.json").read_text(encoding="utf-8"))


def write_checkpoint(run_dir: Path, data: dict[str, Any]) -> None:
    """先写 tmp 再 os.replace：断电时要么是旧的完整版本，要么是新的，没有半截。"""
    data = {**data, "updated_at": datetime.now(UTC).isoformat()}
    path = Path(run_dir) / "checkpoint.json"
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, path)


# --------------------------------------------------------------------------
# 建 run
# --------------------------------------------------------------------------
def new_run(
    task_dir: Path, runs_root: Path, run_id: str, *, domains_root: Path | None = None
) -> Path:
    """建 runs/<run_id>/：先过契约校验，再拷 work/ 并 git init，checkpoint 记基线。"""
    task_dir = Path(task_dir).resolve()
    domains_root = Path(domains_root) if domains_root else task_dir.parent.parent / "domains"
    problems = packs.validate_task(task_dir, domains_root)
    if problems:
        raise TaskInvalid("任务包不合契约，不开跑：\n" + "\n".join(problems))

    run_dir = Path(runs_root).resolve() / run_id
    if run_dir.exists():
        raise FileExistsError(f"run 已存在，不覆盖：{run_dir}")
    (run_dir / "experiment" / "runs").mkdir(parents=True)
    shutil.copy2(task_dir / packs.MANIFEST_NAME, run_dir / packs.MANIFEST_NAME)
    work = run_dir / "work"
    shutil.copytree(task_dir, work, ignore=shutil.ignore_patterns(*IGNORED_DIRS))
    (run_dir / "journal.md").touch()  # 协调层写的东西，框架只建空文件

    manifest = load_manifest(run_dir)
    _snapshot_domain_prompt(domains_root / manifest.get("domain", packs.DEFAULT_DOMAIN), run_dir)
    baseline = json.loads((work / "run_0" / "results.json").read_text(encoding="utf-8"))
    best_metric = baseline["metrics"][primary_metric(manifest)["name"]]
    best_commit = gitwork.init_repo(work, f"任务包基线：{manifest['id']}")
    write_checkpoint(run_dir, {
        "run_id": run_id, "last_iter": 0, "best_iter": 0, "best_metric": best_metric,
        "best_commit": best_commit, "stop_reason": None,
    })
    LOGGER.info("run_new run_dir=%s best_metric=%s", run_dir, best_metric)
    return run_dir


def _snapshot_domain_prompt(domain_dir: Path, run_dir: Path) -> None:
    """领域包的实验追加段随 run 快照一份；没有就不留（缺了不追加，也不回退到别的模板）。"""
    src = domain_dir / "prompts" / "experiment.md"
    if src.is_file():
        (run_dir / "prompts").mkdir(exist_ok=True)
        shutil.copy2(src, run_dir / "prompts" / "experiment-domain.md")


def extend_run(
    run_dir: Path, *, patience: int | None = None, max_iterations: int | None = None,
    max_cost_usd: float | None = None, reason: str = "",
) -> dict[str, Any]:
    """协调层给已停的 run 续命：改快照里的 budget、清 stop_reason 与 stop.json、journal 记一行。

    只改这三样：要不要继续是协调层的决定（P-10），但怎么继续必须留痕——journal.md 是
    协调层自己的本子，续命这条记在这里而不是账本里，账本只记轮次。
    """
    run_dir = Path(run_dir).resolve()
    manifest = load_manifest(run_dir)
    budget = manifest["budget"]
    changes = []
    for key, value in (("patience", patience), ("max_iterations", max_iterations),
                       ("max_cost_usd", max_cost_usd)):
        if value is None:
            continue
        assert value > 0, f"{key} 必须是正数，得到 {value!r}"
        changes.append(f"{key}: {budget.get(key)} → {value}")
        budget[key] = value
    (run_dir / packs.MANIFEST_NAME).write_text(
        yaml.safe_dump(manifest, allow_unicode=True, sort_keys=False), encoding="utf-8")
    state = read_checkpoint(run_dir)
    cleared = state.get("stop_reason")
    write_checkpoint(run_dir, {**state, "stop_reason": None})
    (run_dir / "experiment" / "stop.json").unlink(missing_ok=True)
    line = (f"- {datetime.now(UTC).isoformat(timespec='seconds')} 续命：清掉 stop_reason={cleared}"
            f"；{'；'.join(changes) or '预算未改'}；原因：{reason or '未说明'}\n")
    with (run_dir / "journal.md").open("a", encoding="utf-8") as fh:
        fh.write(line)
    LOGGER.info("run_extend run_dir=%s cleared=%s changes=%s", run_dir, cleared, changes)
    return {"cleared": cleared, "changes": changes}


def load_manifest(run_dir: Path) -> dict[str, Any]:
    """只读 run 目录里的 manifest 快照：跑起来后不再回头看任务包（纲领磁盘布局）。"""
    return yaml.safe_load((Path(run_dir) / packs.MANIFEST_NAME).read_text(encoding="utf-8"))


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
    work = run_dir / "work"
    sigma_doc = json.loads((work / "run_0" / "sigma.json").read_text(encoding="utf-8"))
    seed = json.loads((work / "run_0" / "results.json").read_text(encoding="utf-8"))["seed"]
    patience = budget.get("patience", DEFAULT_PATIENCE)
    assert isinstance(patience, int) and patience >= 1, f"budget.patience 要是正整数：{patience!r}"
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
    domain_prompt = run_dir / "prompts" / "experiment-domain.md"
    return RunContext(
        run_dir=run_dir, work=work, experiment=run_dir / "experiment",
        ledger_path=run_dir / "experiment" / "ledger.tsv", question=manifest["question"],
        metric_name=metric["name"], direction=direction, sigma=sigma,
        accept_sigma=float(budget["accept_sigma"]), min_delta=min_delta,
        wall_clock_s=float(budget["wall_clock_s"]),
        max_iterations=int(budget["max_iterations"]), patience=patience, max_cost_usd=max_cost,
        seed=int(seed),
        domain_extra=domain_prompt.read_text(encoding="utf-8") if domain_prompt.is_file() else "",
    )
