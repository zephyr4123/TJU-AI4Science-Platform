"""实验产出目录 `experiment/<n>/` 的布局：路径常量与拼接，一处定义、各处引用。

为什么单独一个模块：这个目录下的每个文件名（checkpoint、账本、笔记、in-flight 标记、停止标记、
每轮的快照与执行层日志）都被三四个模块各自用到，字符串散在各处时改一个名字要靠 grep，
漏一处就变成"写在 A 读在 B"的静默失配。纲领 workflow.md §2 的磁盘布局在这里落成代码：

    experiment/<n>/  meta.yaml（框架的）  scoring.yaml（设计那包的快照）  checkpoint.json
                     journal.md
                     prompts/{requirement.md, experiment-domain.md, skills/}
                     .venv/（按 work/env/ 建的任务环境）
                     work/（设计那包的拷贝，自己的 git 仓：分支 tip = best）
                     ledger.tsv  notebook.md  inflight.json  stop.json
                     iters/iter_N/（每轮跑 harness 的快照 + results.json）   executor/iter-N/
                     （执行层日志）

它只回答"东西该在哪儿"，不读盘、不建目录。这是实验这一族能力私下的约定：分析、验证按这里的名字找
实验的产出（P-13：消费者只准报生产者原样声明过的名字）。
"""

from __future__ import annotations

from pathlib import Path

from framework.experiment import env
from framework.experiment.pack import BASELINE_DIRNAME, SCORING_NAME

REQUIREMENT_NAME = "requirement.md"
CHECKPOINT_NAME = "checkpoint.json"
JOURNAL_NAME = "journal.md"
WORK_DIRNAME = "work"
LEDGER_NAME = "ledger.tsv"
NOTEBOOK_NAME = "notebook.md"
INFLIGHT_NAME = "inflight.json"
STOP_NAME = "stop.json"
CODE_DIRNAME = "code"
ITERS_DIRNAME = "iters"
BASELINE_KEY = "baseline"
# 执行层适配器把事件流写在 work/<这个目录>/ 下；它同时是拷包时要跳过的目录之一，
# 也是每轮跑完要搬走的取证日志的来源，两处引用同一个常数。
EXECUTOR_SCRATCH = ".ai4sci"


def scoring(run_dir: Path) -> Path:
    """跑起来后只认这份快照，不回头看设计那包。"""
    return Path(run_dir) / SCORING_NAME


def requirement(run_dir: Path) -> Path:
    """开实验时对工作区 requirement.md 的快照（放 prompts/ 下：它是提示的输入；不放根——根上的
    requirement.md 是工作区的标记，放这儿会让「往上找工作区」认错门）。"""
    return Path(run_dir) / "prompts" / REQUIREMENT_NAME


def checkpoint(run_dir: Path) -> Path:
    return Path(run_dir) / CHECKPOINT_NAME


def journal(run_dir: Path) -> Path:
    """协调层自己的本子：框架只建空文件、续命时追一行。"""
    return Path(run_dir) / JOURNAL_NAME


def work(run_dir: Path) -> Path:
    return Path(run_dir) / WORK_DIRNAME


def code(work_dir: Path) -> Path:
    """执行层唯一能改的地方（注意入参是 work/ 而不是产出目录）。"""
    return Path(work_dir) / CODE_DIRNAME


def baseline(work_dir: Path) -> Path:
    """设计那包带来的基线（在 work/ 里）：改进率的分母。"""
    return Path(work_dir) / BASELINE_DIRNAME


def ledger(run_dir: Path) -> Path:
    return Path(run_dir) / LEDGER_NAME


def notebook(run_dir: Path) -> Path:
    return Path(run_dir) / NOTEBOOK_NAME


def inflight(run_dir: Path) -> Path:
    return Path(run_dir) / INFLIGHT_NAME


def stop(run_dir: Path) -> Path:
    return Path(run_dir) / STOP_NAME


def iter_key(iter_n: int) -> str:
    """第 N 轮在结果索引、分析数据表里的名字：`iter_N`；基线是 `baseline`。"""
    return f"iter_{iter_n}"


def iter_run(run_dir: Path, iter_n: int) -> Path:
    """第 N 轮跑 harness 的快照目录 `iters/iter_N/`。"""
    return Path(run_dir) / ITERS_DIRNAME / iter_key(iter_n)


def executor_logs(run_dir: Path, iter_n: int) -> Path:
    """第 N 轮执行层日志的留档目录 `executor/iter-N/`。"""
    return Path(run_dir) / "executor" / f"iter-{iter_n}"


def executor_scratch(work_dir: Path) -> Path:
    """执行层适配器在 work/ 下写事件流的地方（下一轮开头会被 git clean 清掉）。"""
    return Path(work_dir) / EXECUTOR_SCRATCH


def domain_prompt(run_dir: Path) -> Path:
    """领域包实验追加段的快照；不存在就是"这个领域没有追加段"。"""
    return Path(run_dir) / "prompts" / "experiment-domain.md"


def domain_skills(run_dir: Path) -> Path:
    """领域包 skills/*/SKILL.md 的快照目录，一个 skill 一个 `<name>.md`。"""
    return Path(run_dir) / "prompts" / "skills"


def venv(run_dir: Path) -> Path:
    """这次实验自己的任务环境；开工时按 work/env/ 建，跑起来后不回头看设计那包的 .venv。"""
    return Path(run_dir) / env.VENV_DIRNAME


def venv_python(run_dir: Path) -> Path:
    return env.venv_python(venv(run_dir))
