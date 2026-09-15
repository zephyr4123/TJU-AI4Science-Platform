"""run 目录的布局：路径常量与拼接，一处定义、各处引用。

为什么单独一个模块：`runs/<run_id>/` 下的每个文件名（checkpoint、账本、笔记、in-flight
标记、停止标记、每轮的快照与执行层日志）都被三四个模块各自用到，字符串散在各处时改一个
名字要靠 grep，漏一处就变成"写在 A 读在 B"的静默失配。纲领 workflow.md §1 的磁盘布局在
这里落成代码：

    runs/<run_id>/ manifest.yaml checkpoint.json journal.md prompts/
                   work/（任务包拷贝，自己的 git 仓）
                   experiment/{ledger.tsv, notebook.md, inflight.json, stop.json,
                               runs/run_N/, executor/iter-N/}
                   analysis/{analysis.md, executor/}   verify/report.json
                   <能力>_v{n}/  重跑时旧目录改名留档，不覆盖

本模块在四层的最底下一档（run 层），只依赖 contracts 里的 manifest 文件名，不读盘、
不建目录——它只回答"东西该在哪儿"。
"""

from __future__ import annotations

from pathlib import Path

from framework.contracts.packs import MANIFEST_NAME

CHECKPOINT_NAME = "checkpoint.json"
JOURNAL_NAME = "journal.md"
WORK_DIRNAME = "work"
EXPERIMENT_DIRNAME = "experiment"
LEDGER_NAME = "ledger.tsv"
NOTEBOOK_NAME = "notebook.md"
INFLIGHT_NAME = "inflight.json"
STOP_NAME = "stop.json"
CODE_DIRNAME = "code"
# 执行层适配器把事件流写在 work/<这个目录>/ 下；它同时是拷任务包时要跳过的目录之一，
# 也是每轮跑完要搬走的取证日志的来源，两处引用同一个常数。
EXECUTOR_SCRATCH = ".ai4sci"


def manifest(run_dir: Path) -> Path:
    """跑起来后只认这份快照，不回头看任务包。"""
    return Path(run_dir) / MANIFEST_NAME


def checkpoint(run_dir: Path) -> Path:
    return Path(run_dir) / CHECKPOINT_NAME


def journal(run_dir: Path) -> Path:
    """协调层自己的本子：框架只建空文件、续命时追一行。"""
    return Path(run_dir) / JOURNAL_NAME


def work(run_dir: Path) -> Path:
    return Path(run_dir) / WORK_DIRNAME


def code(work_dir: Path) -> Path:
    """执行层唯一能改的地方（注意入参是 work/ 而不是 run 目录）。"""
    return Path(work_dir) / CODE_DIRNAME


def experiment(run_dir: Path) -> Path:
    return Path(run_dir) / EXPERIMENT_DIRNAME


def ledger(run_dir: Path) -> Path:
    return experiment(run_dir) / LEDGER_NAME


def notebook(run_dir: Path) -> Path:
    return experiment(run_dir) / NOTEBOOK_NAME


def inflight(run_dir: Path) -> Path:
    return experiment(run_dir) / INFLIGHT_NAME


def stop(run_dir: Path) -> Path:
    return experiment(run_dir) / STOP_NAME


def iter_run(run_dir: Path, iter_n: int) -> Path:
    """第 N 轮跑 harness 的快照目录 `experiment/runs/run_N/`。"""
    return experiment(run_dir) / "runs" / f"run_{iter_n}"


def executor_logs(run_dir: Path, iter_n: int) -> Path:
    """第 N 轮执行层日志的留档目录 `experiment/executor/iter-N/`。"""
    return experiment(run_dir) / "executor" / f"iter-{iter_n}"


def executor_scratch(work_dir: Path) -> Path:
    """执行层适配器在 work/ 下写事件流的地方（下一轮开头会被 git clean 清掉）。"""
    return Path(work_dir) / EXECUTOR_SCRATCH


def domain_prompt(run_dir: Path) -> Path:
    """领域包实验追加段的 run 内快照；不存在就是"这个领域没有追加段"。"""
    return Path(run_dir) / "prompts" / "experiment-domain.md"


def capability_dir(run_dir: Path, name: str) -> Path:
    """一个能力的产物目录 `runs/<run_id>/<name>/`；实验能力的是 `experiment/`（见上）。"""
    return Path(run_dir) / name


def analysis_doc(run_dir: Path) -> Path:
    return capability_dir(run_dir, "analysis") / "analysis.md"


def verify_report(run_dir: Path) -> Path:
    return capability_dir(run_dir, "verify") / "report.json"
