"""开一次实验：从任务包建 run。task 级，`run/lifecycle.new_run` 的薄壳。

它是任务段到 run 段的桥：跑基线之后、实验内环之前。做成能力而不是一条单独的 `run new` 命令，
是为了让能力清单完整：协调 agent 看到的按钮就是全部按钮，工作流文件里每一步都能指到清单上的名字，
`flow check` 也不用把桥写成常数（`contracts.flow` 认 `start` 这个名字）。

产物不在任务包里而在 runs 根下（`AI4SCI_RUNS_ROOT`，缺省仓根 `runs/`）：描述符里的 outputs
路径写的是那里的位置，`contracts.flow` 过桥后可用的文件按 run 的种子算。
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from framework.contracts import packs, publish
from framework.contracts.capability import Artifact, Capability, CapabilityFailed, Param, Ports
from framework.run import flow_state
from framework.run.context import default_runs_root, default_workflows_root
from framework.run.lifecycle import EnvBuildError, NotPublished, TaskInvalid, new_run

NAME = "start"
DESCRIPTOR = Capability(
    name=NAME,
    level="task",
    summary="开一次实验：把任务包搬进 runs/<run_id>/ 的独立工作区，快照领域包、建环境、记下基线",
    stage="实验",
    title="开一次实验",
    what="把任务包搬进一个独立的工作区，记下起点。之后每一轮都在这个工作区里改。",
    inputs=(
        Artifact("manifest", packs.MANIFEST_NAME, "预算与统计门"),
        Artifact("publish", publish.PUBLISH_NAME, "发布记录：没有不开"),
        Artifact("harness", "harness/", "封好的裁判脚本"),
        Artifact("code", "code/", "基线代码"),
        Artifact("run_0", "run_0/", "基线成绩与 σ：预检要看"),
        Artifact("env", "env/", "任务环境的依据"),
    ),
    outputs=(
        Artifact("run", "runs/<run_id>/",
                 "独立工作区：manifest 快照、work/（任务包的副本，起 git）、checkpoint.json；"
                 "给了 --workflow 就多 flow.json 与 workflow/ 里那条流的快照"),
    ),
    params=(
        Param("run_id", "str", "", "run 的名字；缺省 <任务名>-<UTC 时间戳>"),
        Param("runs_root", "str", "",
              "runs 根目录；缺省环境变量 AI4SCI_RUNS_ROOT，再缺省 <仓根>/runs"),
        Param("workflow", "str", "",
              "照哪条预装的流（show workflows 里的名字）：快照进 run，之后每按一颗按钮记它落在第几步"),
    ),
    criteria=(
        "任务包已发布、合契约、预检有改进空间",
        "runs/<run_id>/work/ 起了 git，基线成绩写进 checkpoint.json",
    ),
)


def run(task_dir: Path, ports: Ports, *, run_id: str = "", runs_root: str = "",
        workflow: str = "") -> str:
    task_dir = Path(task_dir).resolve()
    run_id = run_id or f"{task_dir.name}-{datetime.now(UTC):%Y%m%dT%H%M%SZ}"
    root = Path(runs_root).resolve() if runs_root else default_runs_root()
    workflow_path = _workflow_file(workflow) if workflow else None  # 名字不对在开 run 之前就拒
    try:
        run_dir = new_run(task_dir, root, run_id)
    except (NotPublished, TaskInvalid, EnvBuildError) as exc:
        # 没发布、不合约、预检没过、环境建不出来：都停在门口，不留半截 run（P-7）
        raise CapabilityFailed(str(exc)) from exc
    except FileExistsError as exc:
        raise CapabilityFailed(str(exc)) from exc
    tail = ""
    if workflow_path is not None:
        state = flow_state.attach(run_dir, workflow_path)
        tail = f"\tworkflow={workflow}\tstep={state['step']}"
    return f"ok {run_id}\t{run_dir}{tail}\tnext=ai4sci cap experiment {run_id}"


def _workflow_file(name: str) -> Path:
    root = default_workflows_root()
    path = root / f"{name}.yaml"
    if not path.is_file():
        available = ", ".join(sorted(p.stem for p in root.glob("*.yaml"))) or "-"
        raise CapabilityFailed(f"没有叫 {name!r} 的工作流（{root} 下有：{available}）")
    return path
