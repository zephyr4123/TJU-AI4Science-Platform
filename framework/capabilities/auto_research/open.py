"""开一次实验与给已停的实验加预算。

开实验的第一件事是过设计那包的契约（`experiment.pack`）与预检（`experiment.headroom`），
过不了就不开（P-7）。加预算只改快照里的 budget 与停止标记——要不要继续是协调层的
决定（P-10），怎么继续必须留痕。
"""

from __future__ import annotations

import json
import logging
import shutil
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

from framework import paths
from framework.experiment import env, gitwork, headroom, layout
from framework.experiment import pack as packs
from framework.experiment.checkpoint import read_checkpoint, write_checkpoint
from framework.experiment.context import PackInvalid, load_scoring

__all__ = ["PackInvalid", "EnvBuildError", "open_experiment", "extend_experiment"]
EnvBuildError = env.EnvBuildError

LOGGER = logging.getLogger("ai4sci.experiment")

# 拷设计那包时不带过去的目录：.git 是别的仓的状态，执行层日志目录是上一次跑的残留，
# 包目录下的 .venv 是给 make_run0.sh 用的——实验有自己的一份，按同一份 lock 重建；
# meta.yaml / signed.json 是框架给那次产出记的账，不是包的一部分
IGNORED = (".git", layout.EXECUTOR_SCRATCH, "__pycache__", env.VENV_DIRNAME, "meta.yaml",
           "signed.json")


def open_experiment(
    run_dir: Path, pack: Path, requirement: Path, *, output_id: str,
    domains_root: Path | None = None, chat_id: str | None = None,
) -> None:
    """把已经建好的产出目录 `experiment/<n>/` 铺成一次实验：校验 → 预检 → 拷 work/ → 快照 scoring
    与需求
    → 快照领域包 → 建环境 → git init → 基线进 checkpoint。

    开跑是花钱的第一步，所以两道前置检查都在这：包不合约不开、预检说这道题无解不开（都是
    `PackInvalid`）。
    环境建不出来就把铺了一半的东西清掉再抛：一个没有环境的实验跑不了任何一轮。
    """
    pack = Path(pack).resolve()
    run_dir = Path(run_dir).resolve()
    domains_root = Path(domains_root) if domains_root else paths.domains_root()
    problems = packs.validate_pack(pack, domains_root)
    if problems:
        raise PackInvalid("设计那包不合约，不开跑：\n" + "\n".join(problems))
    problems = headroom.assess(pack).problems()
    if problems:
        raise PackInvalid("预检没过，不开跑：\n" + "\n".join(problems))

    (run_dir / layout.ITERS_DIRNAME).mkdir()
    shutil.copy2(pack / packs.SCORING_NAME, layout.scoring(run_dir))
    layout.requirement(run_dir).parent.mkdir(exist_ok=True)
    shutil.copy2(requirement, layout.requirement(run_dir))
    work = layout.work(run_dir)
    shutil.copytree(pack, work, ignore=shutil.ignore_patterns(*IGNORED))
    layout.journal(run_dir).touch()  # 协调层写的东西，框架只建空文件

    scoring = load_scoring(run_dir)
    _snapshot_domain(domains_root / scoring.get("domain", packs.DEFAULT_DOMAIN), run_dir)
    try:
        env.build_venv(work, layout.venv(run_dir))
    except env.EnvBuildError:
        for child in run_dir.iterdir():
            if child.name != "meta.yaml":
                shutil.rmtree(child) if child.is_dir() else child.unlink()
        raise
    baseline = json.loads((layout.baseline(work) / "results.json").read_text(encoding="utf-8"))
    best_metric = baseline["metrics"][packs.primary_metric(scoring)["name"]]
    best_commit = gitwork.init_repo(work, f"设计基线：{output_id}")
    write_checkpoint(run_dir, {
        "output": output_id, "last_iter": 0, "best_iter": 0, "best_metric": best_metric,
        "best_commit": best_commit, "stop_reason": None, "chat_id": chat_id,
    })
    LOGGER.info("experiment_open run_dir=%s best_metric=%s", run_dir, best_metric)


def _snapshot_domain(domain_dir: Path, run_dir: Path) -> None:
    """领域包的实验追加段与全部 skill 随实验快照一份；没有就不留，也不回退到别的领域。

    skill 走 prompt 而不是执行层 CLI 的原生 skill 目录：执行层的隔离参数把原生加载关掉了
    （纲领 domains.md，Q-2）。快照进来是为了跑起来后不回头看领域包。
    """
    src = domain_dir / "prompts" / "experiment.md"
    if src.is_file():
        dst = layout.domain_prompt(run_dir)
        dst.parent.mkdir(exist_ok=True)
        shutil.copy2(src, dst)
    for skill in sorted((domain_dir / "skills").glob("*/SKILL.md")):
        dst = layout.domain_skills(run_dir) / f"{skill.parent.name}.md"
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(skill, dst)


def extend_experiment(
    run_dir: Path, *, patience: int | None = None, max_iterations: int | None = None,
    max_cost_usd: float | None = None, reason: str = "",
) -> dict[str, Any]:
    """协调层给已停的实验加预算：改快照里的 budget、清 stop_reason 与 stop.json、journal 记一行。

    只改这三样：要不要继续是协调层的决定（P-10），但怎么继续必须留痕——journal.md 是
    协调层自己的本子，加预算这条记在这里而不是账本里，账本只记轮次。
    """
    run_dir = Path(run_dir).resolve()
    scoring = load_scoring(run_dir)
    budget = scoring["budget"]
    changes = []
    for key, value in (("patience", patience), ("max_iterations", max_iterations),
                       ("max_cost_usd", max_cost_usd)):
        if value is None:
            continue
        assert value > 0, f"{key} 必须是正数，得到 {value!r}"
        changes.append(f"{key}: {budget.get(key)} → {value}")
        budget[key] = value
    layout.scoring(run_dir).write_text(
        yaml.safe_dump(scoring, allow_unicode=True, sort_keys=False), encoding="utf-8")
    state = read_checkpoint(run_dir)
    cleared = state.get("stop_reason")
    # resumed_after_iter：不可修复的判定只数这一轮之后的账本行。加预算本身就是协调层在说
    # "之前那几次失败我看过了、不算"（真跑时执行层连不上模型三次被判不可修复，加预算后
    # 内环一起来又从账本尾部数到同样三行、当场再停，等于加预算无效）
    write_checkpoint(run_dir, {**state, "stop_reason": None,
                               "resumed_after_iter": state["last_iter"]})
    layout.stop(run_dir).unlink(missing_ok=True)
    line = (f"- {datetime.now(UTC).isoformat(timespec='seconds')} 加预算："
            f"清掉 stop_reason={cleared}"
            f"；{'；'.join(changes) or '预算未改'}；原因：{reason or '未说明'}\n")
    with layout.journal(run_dir).open("a", encoding="utf-8") as fh:
        fh.write(line)
    LOGGER.info("experiment_extend run_dir=%s cleared=%s changes=%s", run_dir, cleared, changes)
    return {"cleared": cleared, "changes": changes}
