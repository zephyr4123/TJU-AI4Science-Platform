"""开一次实验：从工作区的任务包建 run。task 级，`run/lifecycle.new_run` 的薄壳。

它是任务段到 run 段的桥：跑基线之后、实验内环之前。做成能力而不是一条单独的 `run new` 命令，
是为了让能力清单完整：协调 agent 看到的按钮就是全部按钮，工作流文件里每一步都能指到清单上的名字，
`flow check` 也不用把桥写成常数（`contracts.flow` 认 `start` 这个名字）。

run 落在工作区的 `runs/` 下；`--workflow` 只认工作区 `flows/` 里的实例（纲领 P-15：库里的流要先
`ai4sci flow take` 取到工作区才能跑），快照进 run 之后实例再改不影响这个 run。
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from framework.contracts import packs, publish
from framework.contracts.capability import Artifact, Capability, CapabilityFailed, Param, Ports
from framework.run import flow_state
from framework.run.lifecycle import EnvBuildError, NotPublished, TaskInvalid, new_run
from framework.run.workspace import Workspace

NAME = "start"
DESCRIPTOR = Capability(
    name=NAME,
    level="task",
    summary="开一次实验：把任务包搬进 runs/<run_id>/ 的独立工作目录，快照领域包、建环境、记下基线",
    stage="实验",
    title="开一次实验",
    what="把任务包搬进一个独立的工作目录，记下起点。之后每一轮都在这个目录里改。",
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
                 "独立工作目录：manifest 快照、work/（任务包的副本，起 git）、checkpoint.json；"
                 "给了 --workflow 就多 flow.json 与 workflow/ 里那条流的快照"),
    ),
    params=(
        Param("run_id", "str", "", "run 的名字；缺省 <工作区名>-<UTC 时间戳>"),
        Param("workflow", "str", "",
              "照工作区里的哪条流（show flows 里的名字）：快照进 run，之后每按一颗按钮记步序"),
    ),
    criteria=(
        "任务包已发布、合契约、预检有改进空间",
        "runs/<run_id>/work/ 起了 git，基线成绩写进 checkpoint.json",
    ),
)


def run(workspace: Workspace, ports: Ports, *, run_id: str = "", workflow: str = "") -> str:
    run_id = run_id or f"{workspace.id}-{datetime.now(UTC):%Y%m%dT%H%M%SZ}"
    # 名字不对在开 run 之前就拒
    workflow_path = _flow_file(workspace, workflow) if workflow else None
    try:
        run_dir = new_run(workspace.task, workspace.runs, run_id)
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


def _flow_file(workspace: Workspace, name: str) -> Path:
    path = workspace.flows / f"{name}.yaml"
    if not path.is_file():
        available = ", ".join(sorted(p.stem for p in workspace.flows.glob("*.yaml"))) or "-"
        raise CapabilityFailed(
            f"工作区里没有叫 {name!r} 的流（flows/ 下有：{available}）；"
            f"库里有的先取过来：ai4sci flow take {name}")
    return path
