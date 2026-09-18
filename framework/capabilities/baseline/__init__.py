"""跑基线能力：起 `harness/make_run0.sh` 出 run_0/，跑完机器预检"值不值得跑"。

task 级。为什么不让人直接 `bash harness/make_run0.sh`：launcher 从 AI4SCI_BUDGET_S /
AI4SCI_INNER_K 读这两个数，人手工起就得自己想着导出，忘了就是一次"看着像跑了"的基线。
按钮把两处的环境收成一处（`contracts.env.harness_env`），基线和内环跑的是同一份约定。

跑完不停下来等人看基线：原来那个人工停点看的三四个数（基线、σ、门、尽头）机器能算
（`contracts.headroom`），判无解就退非零并说清，否则把数字写在结论行里。
"""

from __future__ import annotations

import os
import subprocess

import yaml

from framework.contracts import env, headroom, packs, publish
from framework.contracts.capability import Artifact, Capability, CapabilityFailed, Ports
from framework.run.workspace import Workspace

NAME = "baseline"
DESCRIPTOR = Capability(
    name=NAME,
    level="task",
    summary="跑基线：起 make_run0.sh 出 run_0/（基线 + 重复 + σ），环境与内环同一组，跑完机器预检",
    stage="设计",
    title="跑基线",
    what="把最朴素的代码重复跑几次，得到起点成绩和它的晃动幅度。顺手算一遍从起点到尽头有没有改进的空间，没有就停下来告诉你。",
    inputs=(
        Artifact("manifest", packs.MANIFEST_NAME, "预算、inner_k、统计门、可选的尽头值 attainable"),
        Artifact("publish", publish.PUBLISH_NAME, "发布记录：没有不跑"),
        Artifact("harness", "harness/", "make_run0.sh 与它调的 launcher.sh、evaluate.py"),
        Artifact("code", "code/", "基线代码"),
        Artifact("env", "env/", "任务环境的依据：.venv 不在就按它建"),
    ),
    outputs=(
        Artifact("run_0", "run_0/",
                 "results.json、repeats/、sigma.json：改进率的分母与统计门的基线"),
    ),
    criteria=(
        "make_run0.sh 退 0",
        "预检：统计门 > 0；给了尽头值则基线到尽头的距离 > 门",
    ),
)


def run(workspace: Workspace, ports: Ports) -> str:
    task_dir = workspace.task
    publish.require_published(task_dir)
    script = task_dir / "harness" / "make_run0.sh"
    if not script.is_file():
        raise CapabilityFailed(
            "缺 task/harness/make_run0.sh：先 ai4sci cap design 写出 harness")
    python = env.venv_python(task_dir / env.VENV_DIRNAME)
    if not python.is_file():
        # 环境是基线的一部分，不是人要记得先按的另一颗键；建不出来就是基线跑不了
        try:
            python = env.build_venv(task_dir, task_dir / env.VENV_DIRNAME)
        except env.EnvBuildError as exc:
            raise CapabilityFailed(str(exc)) from exc
    manifest = yaml.safe_load((task_dir / packs.MANIFEST_NAME).read_text(encoding="utf-8"))
    budget = manifest.get("budget") if isinstance(manifest, dict) else None
    if not isinstance(budget, dict) or not isinstance(budget.get("wall_clock_s"), (int, float)):
        raise CapabilityFailed(
            f"{packs.MANIFEST_NAME} 缺 budget.wall_clock_s，先 ai4sci show task")
    inner_k = budget.get("inner_k", 1)
    if not isinstance(inner_k, int) or inner_k < 1:
        raise CapabilityFailed(
            f"{packs.MANIFEST_NAME} 的 budget.inner_k 要是正整数，实际 {inner_k!r}")
    harness_env = env.harness_env(python, float(budget["wall_clock_s"]), inner_k)
    # stdout / stderr 直通：σ 那一行要让协调层当场看到
    proc = subprocess.run(["bash", str(script)], cwd=task_dir,
                          env={**os.environ, **harness_env}, check=False)
    if proc.returncode != 0:
        raise CapabilityFailed(f"make_run0.sh 退出码 {proc.returncode}，run_0 不可信")
    try:
        room = headroom.assess(task_dir)
    except FileNotFoundError as exc:
        raise CapabilityFailed(str(exc)) from exc
    problems = room.problems()
    if problems:
        raise CapabilityFailed("基线跑完了，预检没过：\n" + "\n".join(problems)
                               + f"\n{room.summary()}")
    return (f"ok {workspace.id}\tinner_k={inner_k}\t{room.summary()}"
            "\tnext=ai4sci show task")
