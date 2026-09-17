"""接任务能力：发布之后按的第一格——起执行层给任务包写 harness 与基线草稿，框架封、lint、校验。

task 级（动的是任务包，还没有 run）。干活的代码在 `executor/design.py`（组提示、起会话、
判越界、封 harness、ruff、validate），这里只是让它有一张描述符、进 `cap list`，好让编排
看板把它画成节点、`ai4sci cap design` 从描述符生成。

门：需求没发布不起会话（`publish.require_published`）——裁判脚本必须在人看过「怎么算好」
之后才写，顺序反了就是原来那个鸡肋停点。
"""

from __future__ import annotations

from pathlib import Path

from framework.contracts import packs, publish
from framework.contracts.capability import Artifact, Capability, CapabilityFailed, Param, Ports
from framework.executor.design import DesignFailed, design_task
from framework.run.context import default_runs_root

NAME = "design"
DESCRIPTOR = Capability(
    name=NAME,
    level="task",
    summary="接任务：执行层照 design.md 写 harness/ 与 code/ 草稿，框架封 harness、ruff、校验",
    stage="设计",
    title="接任务",
    what="按设计说明写裁判脚本和一版最朴素的代码。裁判脚本封起来之后不再改，后面每一轮都用它打分。",
    inputs=(
        Artifact("manifest", packs.MANIFEST_NAME, "任务声明：指标、方向、预算、统计门"),
        Artifact("brief", packs.BRIEF_NAME, "协调层写的产物契约与「怎么算好」"),
        Artifact("publish", publish.PUBLISH_NAME, "发布记录：人看过需求才有，没有不起会话"),
        Artifact("data", "data/", "问题定义与输入数据，裁判用它重算指标"),
        Artifact("env", "env/", "python-version + requirements.lock"),
    ),
    outputs=(
        Artifact("harness", "harness/",
                 "launcher.sh、evaluate.py、make_run0.sh、SHA256SUMS（框架封）"),
        Artifact("code", "code/", "基线代码，之后由内环逐轮改"),
    ),
    params=(
        Param("feedback", "str", "",
              "喂回执行层的修改意见（改第二版）；写 @<文件> 就读那个文件；空串是第一版"),
    ),
    needs_executor=True,
    criteria=(
        "执行层只改了 harness/ 与 code/",
        "harness/ 已封（执行位、SHA256SUMS）且 ruff 与 validate（不查 run_0）都没有问题",
    ),
)


def run(task_dir: Path, ports: Ports, *, feedback: str = "") -> str:
    task_dir = Path(task_dir).resolve()
    assert ports.runner is not None, "design 需要执行层端口"
    publish.require_published(task_dir)
    if feedback.startswith("@"):
        path = Path(feedback[1:])
        if not path.is_file():
            raise CapabilityFailed(f"--feedback 指的文件不存在：{path}")
        feedback = path.read_text(encoding="utf-8")
    try:
        outcome = design_task(task_dir, packs.default_domains_root(task_dir), ports.runner,
                              default_runs_root(), feedback=feedback)
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
            + f"\nnext=把上面的问题喂回：ai4sci cap design {task_dir} --feedback @<文件>")
    return (f"design ok\t{head}\tnext=对照 {packs.BRIEF_NAME}「怎么算好」核对 harness/evaluate.py"
            f"（一致 / 有出入报给人）→ ai4sci cap baseline {task_dir}")
