"""写裁判、跑基线：设计间里的那颗能力——起执行层照 design.md 写 harness 与基线代码，框架封、lint、
校验，接着起 `make_run0.sh` 跑基线、算预检。

task 级（动的是任务包，还没有 run）。前半段的干活代码在 `executor/design.py`（组提示、起会话、
判越界、封 harness、ruff、validate），后半段在同包的 `baseline.py`。原来是两条命令，从来
没有人只调一条：裁判写完不跑基线没意义，基线又只能跑封好的裁判——2026-09-18 并成一颗
（外层 #96）。

门：需求没发布不起会话（`publish.require_published`）——裁判脚本必须在人看过「怎么算好」之后才写。
草稿有问题就停在前半段（草稿留在盘上，问题一行一条），协调层喂 `--feedback` 重跑整颗。
"""

from __future__ import annotations

from pathlib import Path

from framework import paths
from framework.capabilities.design.baseline import run_baseline
from framework.contracts import packs, publish
from framework.contracts.capability import Capability, CapabilityFailed, Param, Ports
from framework.executor.design import DesignFailed, design_task
from framework.run.workspace import Workspace

NAME = "design"
DESCRIPTOR = Capability(
    name=NAME,
    level="task",
    stage="设计",
    title="写裁判、跑基线",
    does=(
        "起一个执行层会话，照 design.md 的「怎么算好」写裁判脚本（harness/：launcher.sh、"
        "evaluate.py、make_run0.sh）和一版最朴素的基线代码（code/）。会话结束后框架接手："
        "给脚本加执行位、写 SHA256SUMS 封住 harness，跑 ruff 与任务包契约校验；"
        "都过了就按 env/ 建 .venv、起 make_run0.sh 跑基线——重复 inner_k 次得到起点成绩与 σ，"
        "写进 run_0/；最后做预检：统计门 max(accept_sigma × σ, min_delta) 要大于零，"
        "给了尽头值 attainable 则基线到尽头的距离要大于门。"
    ),
    does_not=(
        "不定指标、不改需求：manifest.yaml 与 design.md 是它的输入，人发布过才动手。不跑内环、"
        "不开 run。封好的 harness 之后任何能力都不许再改（hash 守着），"
        "要改裁判就带意见重跑这颗能力。"
    ),
    brings=(
        "发布过的任务包：manifest.yaml（指标、方向、预算、统计门）、"
        "design.md（产物契约与「怎么算好」）、data/（裁判重算指标要用的数据）、"
        "env/（python-version 与 requirements.lock）；可选 --feedback 带上一版的修改意见。"
    ),
    leaves=(
        "harness/（封好的裁判脚本与 SHA256SUMS）、code/（基线代码）、run_0/（results.json、"
        "repeats/、sigma.json：改进率的分母与统计门的基线）、.venv/（按 lock 建的环境）；"
        "执行层会话的日志在 runs/design/。"
    ),
    stops=(
        "执行层越界改了别的目录、ruff 或契约校验没过：草稿留在盘上、问题一行一条，"
        "等 --feedback 重跑。make_run0.sh 退非零或预检没过（门为零、离尽头不够一个门）："
        "停下来说清，这道题不值得跑。都过了就一次成活，结论行里是基线、σ、门与离尽头几个门。"
    ),
    params=(
        Param("feedback", "str", "",
              "喂回执行层的修改意见（改第二版）；写 @<文件> 就读那个文件；空串是第一版"),
    ),
    needs_executor=True,
)


def run(workspace: Workspace, ports: Ports, *, feedback: str = "") -> str:
    task_dir = workspace.task
    assert ports.runner is not None, "design 需要执行层端口"
    publish.require_published(task_dir)
    if feedback.startswith("@"):
        path = Path(feedback[1:])
        if not path.is_file():
            raise CapabilityFailed(f"--feedback 指的文件不存在：{path}")
        feedback = path.read_text(encoding="utf-8")
    try:
        # 执行层的日志落在工作区的 runs/design/ 下：和 run 一样是这份需求的产物
        outcome = design_task(task_dir, paths.domains_root(), ports.runner, workspace.runs,
                              feedback=feedback)
    except DesignFailed as exc:
        raise CapabilityFailed(str(exc)) from exc
    head = (f"session={outcome.session}\tchanged={len(outcome.changed_files)}"
            f"\tsealed={','.join(outcome.sealed) or '-'}\tlint={len(outcome.lint_problems)}"
            f"\tvalidate={len(outcome.validate_problems)}\tcost_usd={outcome.cost_usd:.4f}"
            f"\tlog={outcome.log_dir}")
    if outcome.problems:
        # 草稿已经封在盘上，问题一行一条：协调层决定喂回执行层改第二版还是找人
        raise CapabilityFailed(
            f"design draft\t{head}\n" + "\n".join(outcome.problems)
            + "\nnext=把上面的问题喂回：ai4sci cap design --feedback @<文件>")
    baseline = run_baseline(workspace)
    return (f"design ok\t{head}\t{baseline}"
            f"\tnext=对照 {packs.BRIEF_NAME}「怎么算好」核对 harness/evaluate.py，报给人；"
            "人点头了就 ai4sci cap auto-research")
