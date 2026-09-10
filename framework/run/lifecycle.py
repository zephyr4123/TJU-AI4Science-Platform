"""run 的生命周期：建 run 与给已停的 run 续命。

在 run 层，contracts 之上：建 run 的第一件事是过任务包契约（`contracts.packs`），
过不了就停在门口（P-7）。续命只改快照里的 budget 与停止标记——要不要继续是协调层的
决定（P-10），怎么继续必须留痕。

`TaskInvalid` 的定义在 `context.py`（那里说明了为什么），本模块转出它：调用方从
"建 run / 跑 run"这条线上看到的就该是同一个异常。
"""

from __future__ import annotations

import json
import logging
import shutil
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

from framework.contracts import packs
from framework.run import gitwork, layout
from framework.run.checkpoint import read_checkpoint, write_checkpoint
from framework.run.context import TaskInvalid, load_manifest, primary_metric

__all__ = ["TaskInvalid", "new_run", "extend_run"]

LOGGER = logging.getLogger("ai4sci.run")

# 拷贝任务包时不带过去的目录：.git 是别的仓的状态，执行层日志目录是上一次跑的残留
IGNORED_DIRS = (".git", layout.EXECUTOR_SCRATCH, "__pycache__")


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
    (layout.experiment(run_dir) / "runs").mkdir(parents=True)
    shutil.copy2(task_dir / packs.MANIFEST_NAME, layout.manifest(run_dir))
    work = layout.work(run_dir)
    shutil.copytree(task_dir, work, ignore=shutil.ignore_patterns(*IGNORED_DIRS))
    layout.journal(run_dir).touch()  # 协调层写的东西，框架只建空文件

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
        dst = layout.domain_prompt(run_dir)
        dst.parent.mkdir(exist_ok=True)
        shutil.copy2(src, dst)


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
    layout.manifest(run_dir).write_text(
        yaml.safe_dump(manifest, allow_unicode=True, sort_keys=False), encoding="utf-8")
    state = read_checkpoint(run_dir)
    cleared = state.get("stop_reason")
    write_checkpoint(run_dir, {**state, "stop_reason": None})
    layout.stop(run_dir).unlink(missing_ok=True)
    line = (f"- {datetime.now(UTC).isoformat(timespec='seconds')} 续命：清掉 stop_reason={cleared}"
            f"；{'；'.join(changes) or '预算未改'}；原因：{reason or '未说明'}\n")
    with layout.journal(run_dir).open("a", encoding="utf-8") as fh:
        fh.write(line)
    LOGGER.info("run_extend run_dir=%s cleared=%s changes=%s", run_dir, cleared, changes)
    return {"cleared": cleared, "changes": changes}
