"""产出目录的建、找、列，以及冻结的核对（纲领 P-19）。

一个阶段一个目录，每次产出一个子目录 `<stage>/<n>/`，n 从 1 起、接着已有的编号、永远不复用。
`open_output` 建目录并写一份 status=running 的 meta；能力跑完由调用方 `close_output` 记成
ok / failed。
半截的产出留在盘上、记成 failed 而不是删掉：草稿与日志是证据，协调层要看它到底做到哪儿。

冻结：`resolve_inputs` 把 `--from` 点名的 id 换成目录，同时核对每一个——不存在、没成、
被引用或被签之后改过（`check_frozen`）都拒，信息说清怎么办。

跨工作区（外层 #136）：同一项目里兄弟工作区的产出写成 `<工作区>:<stage>/<n>`，`find_output` 到兄弟
目录下找；`from` 原样记这个写法；「被谁引用」扫整个项目——兄弟读过的也冻住。项目外读不到。
"""

from __future__ import annotations

import logging
from pathlib import Path

from framework.contracts import output
from framework.contracts.capability import Inputs
from framework.contracts.output import Meta, OutputId, parse_id
from framework.contracts.stages import STAGE_SLUGS
from framework.workspace import jobs, project, root
from framework.workspace.root import Workspace

LOGGER = logging.getLogger("ai4sci.outputs")


def next_id(workspace: Workspace, slug: str) -> OutputId:
    """下一个编号：盘上有的与作业记录里出现过的都跳过——删掉的产出编号不复用，不然作业记录里的
    「design/1」会指向一个后来的陌生人（删产出是 removal.remove_output）。"""
    stage_dir = workspace.stage_dir(slug)
    taken = [int(p.name) for p in stage_dir.iterdir() if p.is_dir() and p.name.isdigit()] \
        if stage_dir.is_dir() else []
    prefix = f"{slug}/"
    for job in jobs.list_jobs(workspace.jobs):
        number = job.output[len(prefix):] if job.output and job.output.startswith(prefix) else ""
        if number.isdigit():
            taken.append(int(number))
    return OutputId(slug, max(taken, default=0) + 1)


def open_output(workspace: Workspace, slug: str, *, title: str, by: str, inputs: list[str],
                params: dict, flow: str | None, step: int | None, requirement: int | None,
                chat_id: str | None, compute: dict | None = None,
                agent: dict | None = None) -> tuple[Path, Meta]:
    """新开一次产出：建目录、记输入此刻的 hash、写 running 的 meta（在哪台机器上跑、执行层用的哪家
    也记上）。"""
    oid = next_id(workspace, slug)
    directory = oid.path(workspace.root)
    directory.mkdir(parents=True)
    recorded = [output.Input(i, output.tree_hash(find_output(workspace, i)[0])) for i in inputs]
    meta = Meta(id=str(oid), stage=slug, title=title, by=by, created_at=output.now(),
                inputs=recorded, params=dict(params), flow=flow, step=step,
                requirement=requirement, chat_id=chat_id, compute=compute, agent=agent)
    output.write_meta(directory, meta)
    LOGGER.info("output_open id=%s by=%s from=%s flow=%s step=%s", oid, by, inputs, flow, step)
    return directory, meta


def close_output(directory: Path, meta: Meta, *, ok: bool, line: str) -> Meta:
    """能力跑完：成了记结论行，没成记那一句错。两种都留在盘上。"""
    meta.status = "ok" if ok else "failed"
    meta.finished_at = output.now()
    if ok:
        meta.result = line
    else:
        meta.error = line
    output.write_meta(directory, meta)
    LOGGER.info("output_close id=%s status=%s", meta.id, meta.status)
    return meta


def reopen_output(directory: Path, meta: Meta, *, compute: dict | None,
                  agent: dict | None = None) -> Meta:
    """`--continue` 接着干：上一次的结论、错误、结束时间都作废，机器与执行层按这次的记，
    看板与 show output 才不会在跑着的时候还挂着上一次的错和上一次的机器。"""
    meta.status = "running"
    meta.finished_at = None
    meta.result = ""
    meta.error = ""
    meta.compute = compute
    meta.agent = agent
    output.write_meta(directory, meta)
    return meta


def owner_of(workspace: Workspace, text: str) -> tuple[Workspace, OutputId]:
    """一个 id 指的是哪个工作区里的哪次产出：没前缀或前缀就是自己 → 自己；兄弟 → 同一项目里按名字取
    （不在项目里、项目里没有这个工作区都照抛）。返回的 OutputId 去掉了指向自己的前缀。"""
    oid = parse_id(text)
    if oid.workspace is None or oid.workspace == workspace.id:
        return workspace, OutputId(oid.stage, oid.n)
    try:
        return project.of(workspace).workspace(oid.workspace), oid
    except (project.ProjectNotFound, root.WorkspaceNotFound, root.WorkspaceInvalid) as exc:
        # 兄弟不在（名字打错、项目里没有）：对调用方就是「没有这个产出」，和自己的产出不在同一种错
        raise output.OutputNotFound(f"没有产出 {oid}：{exc}") from None


def find_output(workspace: Workspace, text: str) -> tuple[Path, Meta]:
    """按 id 找产出目录与 meta（兄弟工作区的到兄弟目录下找）；形状不对 ValueError，
    不存在 OutputNotFound。"""
    owner, oid = owner_of(workspace, text)
    directory = oid.path(owner.root)
    if not directory.is_dir():
        raise output.OutputNotFound(f"没有产出 {oid}：{directory} 不存在")
    return directory, output.read_meta(directory)


def list_outputs(workspace: Workspace, slug: str | None = None) -> list[tuple[Path, Meta]]:
    """全部产出（或某个阶段的），按阶段固定序、序号升序。坏掉的 meta 照抛：
    盘上有东西不合约不是"没有"。"""
    found: list[tuple[Path, Meta]] = []
    for stage in ([slug] if slug else STAGE_SLUGS):
        stage_dir = workspace.root / stage
        if not stage_dir.is_dir():
            continue
        for child in sorted((p for p in stage_dir.iterdir() if p.is_dir() and p.name.isdigit()),
                            key=lambda p: int(p.name)):
            found.append((child, output.read_meta(child)))
    return found


def referencing(workspace: Workspace, oid: str) -> list[tuple[Workspace, Meta]]:
    """哪些产出 `from` 了它——扫整个项目：自己工作区里的，和兄弟工作区里用 `<工作区>:` 前缀读过它的。
    工作区不在任何项目里（老布局）就只扫自己。"""
    owner, target = owner_of(workspace, oid)
    try:
        siblings = project.of(owner).workspaces()
    except project.ProjectNotFound:
        siblings = [owner]
    users: list[tuple[Workspace, Meta]] = []
    for sibling in siblings:
        for _, meta in list_outputs(sibling):
            for item in meta.inputs:
                got = parse_id(item.id)
                if (got.workspace or sibling.id) == owner.id and got.local == target.local:
                    users.append((sibling, meta))
                    break
    return users


def qualified(seen_from: Workspace, owner: Workspace, meta: Meta) -> str:
    """一次产出从某个工作区看过去的写法：自己的就是 `stage/n`，兄弟的带前缀。"""
    return meta.id if owner.id == seen_from.id else f"{owner.id}:{meta.id}"


def referenced_hash(workspace: Workspace, oid: str) -> str | None:
    """这个产出被冻住时的 hash：第一个 `from` 它的产出记的（项目里任何一个工作区）、或它自己的签字
    记的
    （先者为准）；没人引用没人签就是 None——还没冻。"""
    owner, target = owner_of(workspace, oid)
    signed = output.read_signed(target.path(owner.root))
    candidates: list[tuple[str, str]] = []
    if signed is not None:
        candidates.append((signed["signed_at"], signed["sha256"]))
    for sibling, meta in referencing(workspace, oid):
        for item in meta.inputs:
            got = parse_id(item.id)
            if (got.workspace or sibling.id) == owner.id and got.local == target.local:
                candidates.append((meta.created_at, item.sha256))
    if not candidates:
        return None
    return min(candidates)[1]


def check_frozen(workspace: Workspace, oid: str) -> None:
    """被引用或被签过的产出，现在的内容必须还是那时的内容；不是就拒读并说清怎么办。"""
    frozen = referenced_hash(workspace, oid)
    if frozen is None:
        return
    owner, target = owner_of(workspace, oid)
    current = output.tree_hash(target.path(owner.root))
    if current != frozen:
        raise output.OutputChanged(
            f"{oid} 被引用或签字之后改过了（内容 hash 对不上）：冻住的产出不能改，"
            f"要改就在它的阶段下新开一次产出，再让下游 --from 新的那个")


def resolve_inputs(workspace: Workspace, ids: list[str]) -> Inputs:
    """`--from` 的 id 清单 → Inputs。每一个都得存在、成了、没被改过；重复的去掉。
    记进 meta 的 id 是规范写法：自己的不带前缀，兄弟的带。"""
    seen: list[str] = []
    dirs: list[Path] = []
    for raw in ids:
        directory, meta = find_output(workspace, raw)
        owner, target = owner_of(workspace, raw)
        oid = str(target)
        if oid in seen:
            continue
        if meta.status != "ok":
            raise output.OutputChanged(
                f"{oid} 没成（{meta.status}{'：' + meta.error if meta.error else ''}），不能当输入")
        check_frozen(workspace, oid)
        seen.append(oid)
        dirs.append(directory)
    return Inputs(workspace=workspace.root, outputs=tuple(dirs), ids=tuple(seen))
