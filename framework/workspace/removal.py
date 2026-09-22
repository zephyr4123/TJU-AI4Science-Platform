"""删：项目、工作区、产出、流程实例（主人 2026-09-22：人产生的都能删，删就从根级联删干净，
没有软删除；外层 #134 #136）。

规矩一句话：一个东西拥有的全在它目录底下，删它 = 删目录；目录外的（对话在 CLI 那边的会话、
工作区在每台机器上的镜像）由上层用回调递进来——这一层不认识 chat 与 compute（分层单向）。
什么时候拒：

- 项目：任何一个工作区有作业在跑、有对话正在一轮里（回调抛）；
- 工作区：有作业在跑、兄弟工作区 `from` 过它的产出（删了兄弟的 hash 对账立刻断）；
- 产出：被别的产出 `from` 引用（自己的或兄弟的）、正在跑；签过的叶子能删——签字是人的决定，删也是；
- 流程实例：有产出挂在它上面、正在照它跑。

级联里外面那部分（会话、镜像）删不掉不吞：本机照删，没清干净的每条记在 `Removed.leftovers` 里，
调用方打给人、退出码非零。
"""

from __future__ import annotations

import logging
import shutil
from collections.abc import Callable
from dataclasses import dataclass, field

from framework.contracts.output import Meta
from framework.workspace import jobs, outputs
from framework.workspace.project import Project
from framework.workspace.root import Workspace

LOGGER = logging.getLogger("ai4sci.removal")


class RemovalRefused(ValueError):
    """还不能删；`str(exc)` 说清为什么、先做什么。"""


@dataclass
class Removed:
    what: str
    # 目录外没清干净的：会话、镜像。空就是全干净
    leftovers: list[str] = field(default_factory=list)

    @property
    def clean(self) -> bool:
        return not self.leftovers


def referencing(workspace: Workspace, oid: str) -> list[str]:
    """哪些产出 `from` 了它，写成从这个工作区看过去的 id（兄弟的带前缀）。"""
    return [outputs.qualified(workspace, owner, meta)
            for owner, meta in outputs.referencing(workspace, oid)]


def remove_output(workspace: Workspace, oid: str) -> Removed:
    """删一次产出：只能删叶子。目录整个删掉；作业记录里指向它的那几条结论行标「产出已删」——
    记录是历史，留着。"""
    directory, meta = outputs.find_output(workspace, oid)
    users = referencing(workspace, meta.id)
    if users:
        raise RemovalRefused(f"{meta.id} 被 {', '.join(users)} 读过，删了下游对不上账："
                             "先删下游，从末端往回删")
    if jobs.running_for(workspace.jobs, meta.id) is not None:
        raise RemovalRefused(f"{meta.id} 正有作业在跑：先 ai4sci job stop")
    shutil.rmtree(directory)
    for job in jobs.jobs_for(workspace.jobs, meta.id):
        jobs.note(workspace.jobs, job.job_id, "产出已删")
    LOGGER.info("output_removed workspace=%s id=%s", workspace.id, meta.id)
    return Removed(meta.id)


def remove_flow(workspace: Workspace, name: str) -> Removed:
    """删工作区里的一条流程实例：有产出挂在它上面就拒（看板那张表是按它画的）。"""
    path = workspace.flows / f"{name}.yaml"
    if not path.is_file():
        raise FileNotFoundError(f"工作区里没有叫 {name!r} 的流程")
    hung = [meta.id for _, meta in outputs.list_outputs(workspace) if meta.flow == name]
    if hung:
        raise RemovalRefused(f"流程 {name} 上挂着 {', '.join(hung)}：先删这些产出")
    if jobs.running_flow(workspace.jobs, name) is not None:
        raise RemovalRefused(f"正有作业照流程 {name} 在跑：先 ai4sci job stop")
    path.unlink()
    LOGGER.info("flow_removed workspace=%s flow=%s", workspace.id, name)
    return Removed(name)


def _refuse_running(workspace: Workspace) -> None:
    running = jobs.running_jobs(workspace.jobs)
    if running:
        names = ", ".join(j.job_id for j in running)
        raise RemovalRefused(f"工作区 {workspace.id} 有作业在跑（{names}）：先 ai4sci job stop")


def remove_workspace(workspace: Workspace, *,
                     remove_mirrors: Callable[[Workspace, list[Meta]], list[str]]) -> Removed:
    """删整个工作区：先拒（作业在跑、兄弟读过它的产出），再清每台机器上的镜像，最后删目录。
    对话不在这儿——对话归项目，删工作区不动它。回调返回没清干净的那几句。"""
    _refuse_running(workspace)
    metas = [meta for _, meta in outputs.list_outputs(workspace)]
    for meta in metas:
        outsiders = [ref for ref in referencing(workspace, meta.id) if ":" in ref]
        if outsiders:
            who = ", ".join(outsiders)
            raise RemovalRefused(f"兄弟工作区读过它的产出（{who} 读了 {meta.id}）："
                                 "先删下游，从末端往回删")
    leftovers = remove_mirrors(workspace, metas)
    shutil.rmtree(workspace.root)
    LOGGER.info("workspace_removed id=%s leftovers=%s", workspace.id, leftovers)
    return Removed(workspace.id, leftovers)


def remove_project(project: Project, *, forget_chats: Callable[[Project], list[str]],
                   remove_mirrors: Callable[[Workspace, list[Meta]], list[str]]) -> Removed:
    """删整个项目：先拒（任何一个工作区有作业在跑、任何一段对话在跑——后者由回调抛），再清目录外的
    （每段对话在 CLI 那边的会话、每个工作区在每台机器上的镜像），最后删目录。"""
    spaces = project.workspaces()
    for workspace in spaces:
        _refuse_running(workspace)
    leftovers = forget_chats(project)
    for workspace in spaces:
        metas = [meta for _, meta in outputs.list_outputs(workspace)]
        leftovers += remove_mirrors(workspace, metas)
    shutil.rmtree(project.root)
    LOGGER.info("project_removed id=%s workspaces=%d leftovers=%s", project.id, len(spaces),
                leftovers)
    return Removed(project.id, leftovers)


def mirrors_of(metas: list[Meta]) -> list[str]:
    """这个工作区的产出在哪几台 ssh 机器上跑过（meta.compute 记的名字），按名字去重。"""
    names: list[str] = []
    for meta in metas:
        compute = meta.compute or {}
        if compute.get("kind") == "ssh" and compute.get("name") and compute["name"] not in names:
            names.append(compute["name"])
    return names


__all__ = ["Removed", "RemovalRefused", "mirrors_of", "referencing", "remove_flow",
           "remove_output", "remove_project", "remove_workspace"]
