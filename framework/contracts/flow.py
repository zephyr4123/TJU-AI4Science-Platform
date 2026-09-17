"""流通不通：一串能力按顺序摆好，每一步要的文件前面有没有人吐出来（纲领 P-12）。

块和块之间只认文件、不认对方：描述符声明"我吃哪些路径、吐哪些路径"，编排就是把吐的和吃的
对上。这里是那个对表的算术，零模型、纯函数，给协调 agent（拼单点之前先查一遍）和以后的
编排看板用；不读盘——它回答的是"这样摆通不通"，不是"盘上现在有没有"。

两段一座桥：task 级能力在任务包里干活，种子是需求看板发布时包里已有的东西；桥是能力 `start`
（把任务包搬进 run 的 work/），桥要的是 harness/ code/ run_0/ 都已产出，桥后能用的只有 run 里
一开始就有的两样。流里没写 `start` 而直接出现 run 级能力，也按过了桥算：桥的条件一样查。
"""

from __future__ import annotations

from collections.abc import Sequence

from framework.contracts import packs, publish
from framework.contracts.capability import Capability

# 需求看板发布那一刻任务包里已有的：人和 agent 聊出来的两个文件、发布记录、数据、环境依据
TASK_SEEDS = (packs.MANIFEST_NAME, packs.BRIEF_NAME, publish.PUBLISH_NAME, "data/", "env/")
# `start` 从任务包搬进 work/ 之前要看到的（run/lifecycle.new_run 走 validate_task 查全）
BRIDGE_NEEDS = ("harness/", "code/", "run_0/")
# `start` 建好的 run 里一开始就有的（run/lifecycle.new_run）：manifest 快照、work/ 副本、checkpoint
# （run 的状态：建它的是 start，experiment 只改它；一个文件一个生产者，所以它是种子，不是输出）
RUN_SEEDS = (packs.MANIFEST_NAME, "work/", "checkpoint.json")
BRIDGE_NAME = "start"


def check_flow(steps: Sequence[Capability], *, have: Sequence[str] = ()) -> list[str]:
    """返回问题清单，空清单表示通。每条问题带步骤名与缺的路径，能定位。

    `have`：任务包里除种子之外已经有的路径（一条从基线之后开始的流，前提是 harness/ code/ run_0/
    已在），由工作流文件声明。"""
    if not steps:
        return ["流是空的：至少摆一个能力"]
    problems: list[str] = []
    available = set(TASK_SEEDS) | set(have)
    stage = "task"
    seen: set[str] = set()
    for index, cap in enumerate(steps, start=1):
        label = f"第 {index} 步 {cap.name}"
        if stage == "run" and (cap.level == "task" or cap.name == BRIDGE_NAME):
            problems.append(f"{label} 是 task 级能力，run 段之后不能回到任务包")
            continue
        if cap.name in seen:
            problems.append(
                f"{label} 重复：同一个 run 里同一个能力只能出现一次（产物路径固定，会互相覆盖）")
        seen.add(cap.name)
        if cap.name == BRIDGE_NAME or (cap.level == "run" and stage == "task"):
            # 过桥：显式写了 start，或者流里直接出现 run 级能力（桥的条件一样查）
            missing = [path for path in BRIDGE_NEEDS if path not in available]
            if missing:
                problems.append(f"{label} 之前要过桥（{BRIDGE_NAME}），桥要 {missing} 前面没人产出")
            available = set(RUN_SEEDS)
            stage = "run"
            if cap.name == BRIDGE_NAME:
                continue
        for artifact in cap.inputs:
            if artifact.path not in available:
                problems.append(f"{label} 要 {artifact.path}，前面没人产出")
        available.update(artifact.path for artifact in cap.outputs)
    return problems


def stages_of(steps: Sequence[Capability]) -> list[str]:
    """一串能力覆盖了哪几个科研阶段：按出现顺序，去重。给工作流卡片与 `show flow` 说一句
    "从哪儿到哪儿"；不是校验，阶段之间没有该有的先后（P-10）。"""
    covered: list[str] = []
    for cap in steps:
        if cap.stage not in covered:
            covered.append(cap.stage)
    return covered


def stage_remarks(stages: Sequence[str]) -> list[str]:
    """给人看的提醒，不是问题、不拦流：有实验或分析却没有验证，数字没人回溯，结果不能算可信。
    自定义工坊里 agent 拼出一条流时机器就能说这一句。"""
    if ("实验" in stages or "分析" in stages) and "验证" not in stages:
        return ["有实验或分析、没有验证：数字没人回溯，结果不能算可信"]
    return []
