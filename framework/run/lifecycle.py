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

from framework import paths
from framework.contracts import env, headroom, packs, publish
from framework.run import gitwork, layout
from framework.run.checkpoint import read_checkpoint, write_checkpoint
from framework.run.context import TaskInvalid, load_manifest, primary_metric

__all__ = ["TaskInvalid", "EnvBuildError", "NotPublished", "new_run", "extend_run"]
EnvBuildError = env.EnvBuildError
NotPublished = publish.NotPublished

LOGGER = logging.getLogger("ai4sci.run")

# 拷贝任务包时不带过去的目录：.git 是别的仓的状态，执行层日志目录是上一次跑的残留，
# 任务目录下的 .venv 是给 make_run0.sh 用的——run 有自己的一份，按同一份 lock 重建
IGNORED_DIRS = (".git", layout.EXECUTOR_SCRATCH, "__pycache__", env.VENV_DIRNAME)


def new_run(
    task_dir: Path, runs_root: Path, run_id: str, *, domains_root: Path | None = None,
    chat_id: str | None = None,
) -> Path:
    """建 runs/<run_id>/：钥匙 → 校验 → 预检 → 拷 work/ → 快照领域包 → 建环境 → git init → 基线。

    开跑是花钱的第一步，所以三道门都在这：需求没发布不开（`NotPublished`）、包不合约不开、
    预检说这道题无解不开（都是 `TaskInvalid`）。环境建不出来就把半截的 run 目录删掉再抛：
    一个没有环境的 run 跑不了任何一轮，留着只会让 `loop run` 在更晚的地方以更难懂的方式失败。

    `chat_id` 是哪段对话开的这个 run（外层 #82 #83）：页面靠它知道当前对话最近碰的是哪条流；
    记在 checkpoint 里是因为它是 run 唯一一份状态、内环改写时会保留原有的键。
    """
    task_dir = Path(task_dir).resolve()
    publish.require_published(task_dir)
    domains_root = Path(domains_root) if domains_root else paths.domains_root()
    problems = packs.validate_task(task_dir, domains_root)
    if problems:
        raise TaskInvalid("任务包不合契约，不开跑：\n" + "\n".join(problems))
    problems = headroom.assess(task_dir).problems()
    if problems:
        raise TaskInvalid("预检没过，不开跑：\n" + "\n".join(problems))

    run_dir = Path(runs_root).resolve() / run_id
    if run_dir.exists():
        raise FileExistsError(f"run 已存在，不覆盖：{run_dir}")
    (layout.experiment(run_dir) / "runs").mkdir(parents=True)
    shutil.copy2(task_dir / packs.MANIFEST_NAME, layout.manifest(run_dir))
    work = layout.work(run_dir)
    shutil.copytree(task_dir, work, ignore=shutil.ignore_patterns(*IGNORED_DIRS))
    layout.journal(run_dir).touch()  # 协调层写的东西，框架只建空文件

    manifest = load_manifest(run_dir)
    _snapshot_domain(domains_root / manifest.get("domain", packs.DEFAULT_DOMAIN), run_dir)
    try:
        env.build_venv(work, layout.venv(run_dir))
    except env.EnvBuildError:
        shutil.rmtree(run_dir)
        raise
    baseline = json.loads((work / "run_0" / "results.json").read_text(encoding="utf-8"))
    best_metric = baseline["metrics"][primary_metric(manifest)["name"]]
    best_commit = gitwork.init_repo(work, f"任务包基线：{manifest['id']}")
    write_checkpoint(run_dir, {
        "run_id": run_id, "last_iter": 0, "best_iter": 0, "best_metric": best_metric,
        "best_commit": best_commit, "stop_reason": None, "chat_id": chat_id,
    })
    LOGGER.info("run_new run_dir=%s best_metric=%s", run_dir, best_metric)
    return run_dir


def _snapshot_domain(domain_dir: Path, run_dir: Path) -> None:
    """领域包的实验追加段与全部 skill 随 run 快照一份；没有就不留，也不回退到别的领域。

    skill 走 prompt 而不是执行层 CLI 的原生 skill 目录：执行层的隔离参数把原生加载关掉了
    （纲领 packs.md §3，Q-2）。快照进 run 是为了 run 跑起来后不回头看领域包。
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
    # resumed_after_iter：不可修复的判定只数这一轮之后的账本行。续命本身就是协调层在说
    # "之前那几次失败我看过了、不算"（真跑时执行层连不上模型三次被判不可修复，续命后
    # 内环一起来又从账本尾部数到同样三行、当场再停，等于续命无效）
    write_checkpoint(run_dir, {**state, "stop_reason": None,
                               "resumed_after_iter": state["last_iter"]})
    layout.stop(run_dir).unlink(missing_ok=True)
    line = (f"- {datetime.now(UTC).isoformat(timespec='seconds')} 续命：清掉 stop_reason={cleared}"
            f"；{'；'.join(changes) or '预算未改'}；原因：{reason or '未说明'}\n")
    with layout.journal(run_dir).open("a", encoding="utf-8") as fh:
        fh.write(line)
    LOGGER.info("run_extend run_dir=%s cleared=%s changes=%s", run_dir, cleared, changes)
    return {"cleared": cleared, "changes": changes}


def rotate_capability_dir(run_dir: Path, name: str) -> Path | None:
    """重跑一个能力前把旧产物目录改名成 `<name>_v{n}`，不覆盖（纲领 workflow.md §1）。

    返回改名后的路径；没有旧目录返回 None。n 从 1 起、取还没用过的最小值，
    这样第三次重跑不会把 _v1 盖掉。
    """
    current = layout.capability_dir(run_dir, name)
    if not current.is_dir():
        return None
    n = 1
    while (archived := current.with_name(f"{name}_v{n}")).exists():
        n += 1
    current.rename(archived)
    LOGGER.info("capability_dir_rotated run_dir=%s name=%s archived=%s",
                run_dir, name, archived.name)
    return archived
