"""`ai4sci cap <name> --from <stage>/<n>... [--flow <name>] [--continue <stage>/<n>]`：
按名字跑一个能力的通用驱动（纲领 P-10、P-12、P-19）。

在 cli 层。每个能力的子命令是从它的描述符**生成**的：`--from` 每个都有（读哪几个产出）、`--flow`
每个都有（照哪条流程跑，记进产出）、`--continue` 只有 continuable 的有（接着上一次的产出干，
不另开目录）、`--backend` 只在 needs_executor 时有、`--compute` 只在 needs_compute 时有、
每个 `Param` 变成一个选项——所以"CLI 参数与描述符一致"是构造保证，不靠人对。

驱动做的事，能力自己不知道：
  1. 需求没确认不开工（唯一内置的门，P-19）；
  2. `--from` 的每个产出都得在、成了、没被改过（冻结，`workspace.outputs.resolve_inputs`）；
  3. 照流程跑时查断点：流程说输入那个阶段完了要人签，签字不在或过期就拒；
  4. 在自己的阶段下开一个产出目录、写 running 的 meta，跑完记 ok / failed；
  5. `--detach` 把去掉它的同一条命令起成独立进程当作业，跑完回写记录、属于某段对话的去叫醒；
     返回之前等它过门、开了产出（都是本地几次读写），作业号旁边就有产出 id——起了又当场
     没开起来的（门没过、包不合约）直接报回来，不让协调层拿着作业号说「实验开了」。

跑完即退，用退出码表态；能力之间怎么串是协调层的事，这里没有顺序。
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

from framework import agents
from framework.capabilities import discover
from framework.chat import notify
from framework.cli._common import (
    EXIT_INVALID,
    EXIT_OK,
    EXIT_USAGE,
    current_workspace,
    resolve_ports,
    setup_logging,
)
from framework.contracts import output, requirement, workflows
from framework.contracts.capability import (
    PARAM_TYPES,
    Capability,
    CapabilityFailed,
    Inputs,
    Ports,
)
from framework.contracts.output import Meta
from framework.workspace import jobs, outputs
from framework.workspace.root import Workspace

FROM_HELP = "读哪几个产出（<阶段目录>/<序号>，比如 design/1），可以给几个"
FLOW_HELP = ("照当前工作区里哪条流程跑（show flows 里的名字）：记进产出，断点按它查；"
             "只有一条流程时可省")
CONTINUE_HELP = "接着上一次的产出干（<阶段目录>/<序号>），不另开目录"
# --detach 等子进程过门、开产出的上限（正常几百毫秒），与开了产出之后再看一眼的时长：
# 能力开工第一步就拒的（设计那包不合约）在这一眼里结束，当场报回来；再慢的交给叫醒
DETACH_SETTLE_S = 20.0
DETACH_GRACE_S = 3.0
_DETACH_POLL_S = 0.1


def cmd_cap(args: argparse.Namespace) -> int:
    ws = current_workspace()
    if isinstance(ws, int):
        return ws
    descriptor: Capability = args.module.DESCRIPTOR
    backend = getattr(args, "backend", None)
    if descriptor.needs_executor and backend is None:
        backend = agents.role_backend("executor")  # 按人的设置（P-25），不在代码里写死哪家
    ports = resolve_ports(backend, getattr(args, "compute", None))
    if isinstance(ports, int):
        return ports
    job_id = os.environ.get(jobs.JOB_ID_ENV)
    if args.detach:
        if job_id:
            print(f"已经在作业 {job_id} 里了，作业里不能再 --detach", file=sys.stderr)
            return EXIT_USAGE
        return _detach(args, ws, descriptor)
    setup_logging()
    try:
        code, line = _run(args, ws, descriptor, ports, job_id)
    except Exception as exc:
        # 平台自己炸了（不是能力说的失败）：作业与产出都记上再抛，不让作业停在 running 变 lost、
        # 让人对着「丢了」猜（真跑时 Popen 吃到 NUL 字节就是这样丢的）；栈照样打到日志
        if job_id:
            job = jobs.finish(ws.jobs, job_id, exit_code=EXIT_INVALID,
                              result=f"平台内部错误：{exc!r}（栈在作业日志里，这是平台的 bug）")
            _fail_open_output(ws, job.output, job.result)
            os.environ.pop(jobs.JOB_ID_ENV, None)
            if job.chat_id:
                jobs.mark_wake(ws.jobs, job_id, notify.wake(ws, job))
        raise
    print(line, file=sys.stdout if code == EXIT_OK else sys.stderr)
    if job_id:
        job = jobs.finish(ws.jobs, job_id, exit_code=code, result=line)
        # 作业到此为止：叫醒起的 agent 会继承这个进程的环境，带着作业号它调用的 --detach 全被拒
        os.environ.pop(jobs.JOB_ID_ENV, None)
        if job.chat_id:
            # 作业是某段对话里起的：跑完以框架的身份叫醒那段对话，结果记回作业
            jobs.mark_wake(ws.jobs, job_id, notify.wake(ws, job))
    return code


def _fail_open_output(ws: Workspace, oid: str | None, line: str) -> None:
    """作业开了产出又炸在半路：产出还是 running 就替它记 failed。"""
    if not oid:
        return
    directory, meta = outputs.find_output(ws, oid)
    if meta.status == "running":
        outputs.close_output(directory, meta, ok=False, line=line)


def _run(args: argparse.Namespace, ws: Workspace, descriptor: Capability, ports: Ports,
         job_id: str | None) -> tuple[int, str]:
    """门 → 输入 → 断点 → 开产出 → 跑 → 记账。返回退出码与那一行话（成功是结论行，
    失败是能力自己说的那一句）。"""
    try:
        version = requirement.require_confirmed(ws.root)
    except requirement.NotConfirmed as exc:
        return EXIT_INVALID, str(exc)
    try:
        inputs = outputs.resolve_inputs(ws, list(args.inputs or []))
    except (ValueError, output.OutputNotFound) as exc:  # OutputChanged 是 ValueError
        return EXIT_INVALID, str(exc)
    try:
        flow, step = _place_in_flow(ws, descriptor.name, descriptor.stage, inputs,
                                    getattr(args, "flow", ""))
    except workflows.WorkflowInvalid as exc:
        return EXIT_INVALID, str(exc)
    params = {p.name: getattr(args, p.name) for p in descriptor.params}
    continuing = getattr(args, "continuing", None)
    try:
        if continuing:
            directory, meta = _reopen(ws, descriptor, continuing, inputs)
        else:
            directory, meta = outputs.open_output(
                ws, descriptor.stage_slug, title=descriptor.title, by=descriptor.name,
                inputs=list(inputs.ids),
                params={k: v for k, v in params.items() if v not in (None, "", False)},
                flow=flow, step=step, requirement=version,
                chat_id=os.environ.get(jobs.CHAT_ID_ENV), compute=ports.compute_label)
    except (ValueError, output.OutputNotFound) as exc:
        return EXIT_INVALID, str(exc)
    if job_id:
        jobs.attach_output(ws.jobs, job_id, meta.id)
    try:
        line = args.module.run(directory, inputs, ports, **params)
    except CapabilityFailed as exc:
        outputs.close_output(directory, meta, ok=False, line=str(exc))
        return EXIT_INVALID, f"{exc}\noutput={meta.id}（没成，留在盘上）"
    outputs.close_output(directory, meta, ok=True, line=line)
    return EXIT_OK, f"{line}\toutput={meta.id}"


def _reopen(ws: Workspace, descriptor: Capability, oid: str, inputs: Inputs) -> tuple[Path, Meta]:
    """`--continue`：产出得是这个能力自己产的、这个阶段的；成了没成都能接着干（草稿改第二版）。"""
    directory, meta = outputs.find_output(ws, oid)
    if meta.stage != descriptor.stage_slug or meta.by != descriptor.name:
        raise ValueError(f"{oid} 是 {meta.by} 在「{meta.stage}」阶段产的，{descriptor.name} 接不了")
    if outputs.referenced_hash(ws, oid) is not None:
        raise ValueError(f"{oid} 已经被引用或签过，冻住了：要改就新开一次产出（去掉 --continue）")
    if inputs.ids and list(inputs.ids) != meta.input_ids:
        raise ValueError(f"{oid} 当初读的是 {meta.input_ids}，接着干不能换输入 {list(inputs.ids)}")
    meta.status = "running"
    output.write_meta(directory, meta)
    return directory, meta


def _place_in_flow(ws: Workspace, by: str, stage: str, inputs: Inputs,
                   flow_name: str) -> tuple[str | None, int | None]:
    """照哪条流程、第几项：`--flow` 给了用它；没给而工作区只有一条流程就用那条；几条就得说清；
    一条没有就不照流程。
    照流程时查断点：输入那一项后面紧跟断点的，那个产出得签过且没过期。"""
    flow_name = (flow_name or "").strip()
    instances = sorted(p.stem for p in ws.flows.glob("*.yaml")) if ws.flows.is_dir() else []
    if not flow_name:
        if len(instances) > 1:
            raise workflows.WorkflowInvalid(
                f"工作区有几条流程（{', '.join(instances)}），说清照哪条：--flow <name>")
        if not instances:
            return None, None
        flow_name = instances[0]
    path = ws.flows / f"{flow_name}.yaml"
    if not path.is_file():
        raise workflows.WorkflowInvalid(
            f"工作区里没有叫 {flow_name!r} 的流程（flows/ 下有：{', '.join(instances) or '-'}）；"
            f"库里有的先取过来：ai4sci flow take {flow_name}")
    workflow = workflows.load_workflow(path)
    after = -1
    for directory, oid in zip(inputs.outputs, inputs.ids, strict=True):
        meta = output.read_meta(directory)
        if meta.flow != workflow.name or meta.step is None:
            continue
        after = max(after, meta.step)
        stop = workflows.stop_after(workflow, meta.step)
        if stop is None:
            continue
        signed = output.signature_state(directory)
        if signed is None or signed["stale"]:
            what = f"「{stop.note}」" if stop.note else "签字"
            raise workflows.WorkflowInvalid(
                f"流程 {workflow.name} 在 {oid} 之后有断点{what}：这次产出要人签了下游才能读"
                + ("（签过但之后改了，签字过期）" if signed else "")
                + f"；研究者在页面上签，或终端 ai4sci sign {oid}")
    step = workflows.matching_step(workflow, by, stage, after)
    return workflow.name, step


def _detach(args: argparse.Namespace, ws: Workspace, descriptor: Capability) -> int:
    argv = [a for a in args.argv if a != "--detach"]
    job = jobs.spawn(ws.jobs, argv, cap=descriptor.name, stage=descriptor.stage_slug,
                     chat_id=os.environ.get(jobs.CHAT_ID_ENV),
                     flow=getattr(args, "flow", "") or None,
                     output=getattr(args, "continuing", None))
    job = _settle(ws, job)
    if job.status != "running":
        # 起了就结束：短的能力干完了、或门没过 / 包不合约。记录与产出都已经记好，这里只把话带回来
        ok = job.status == "done"
        print(f"job {job.job_id}\tcap={descriptor.name}\t{job.status}\n{job.result}",
              file=sys.stdout if ok else sys.stderr)
        return EXIT_OK if ok else EXIT_INVALID
    print(f"job {job.job_id}\tcap={descriptor.name}\tpid={job.pid}\toutput={job.output or '-'}"
          f"\tnext=ai4sci show job {job.job_id}")
    return EXIT_OK


def _settle(ws: Workspace, job: jobs.Job) -> jobs.Job:
    """等子进程开了产出或结束（上限 DETACH_SETTLE_S）；开了产出再看 DETACH_GRACE_S 有没有当场
    结束。"""
    deadline = time.monotonic() + DETACH_SETTLE_S
    while time.monotonic() < deadline:
        job = jobs.load(ws.jobs, job.job_id)
        if job.status != "running" or job.output:
            break
        time.sleep(_DETACH_POLL_S)
    if job.status != "running":
        return job
    deadline = time.monotonic() + DETACH_GRACE_S
    while time.monotonic() < deadline:
        job = jobs.load(ws.jobs, job.job_id)
        if job.status != "running":
            break
        time.sleep(_DETACH_POLL_S)
    return job


def add_parser(groups: argparse._SubParsersAction) -> None:
    cap = groups.add_parser("cap", help="按名字跑一个能力，跑完即退（清单：ai4sci show caps）")
    actions = cap.add_subparsers(dest="name", required=True)
    for name, module in discover().items():
        descriptor = module.DESCRIPTOR
        sub = actions.add_parser(name, help=descriptor.title)
        sub.add_argument("--from", dest="inputs", action="append", metavar="STAGE/N",
                         help=FROM_HELP)
        sub.add_argument("--flow", default="", help=FLOW_HELP)
        if descriptor.continuable:
            sub.add_argument("--continue", dest="continuing", default=None, metavar="STAGE/N",
                             help=CONTINUE_HELP)
        if descriptor.needs_executor:
            sub.add_argument("--backend", default=None,
                             help="执行层用哪家 agent；缺省照设置里「执行用」的那家"
                                  "（ai4sci agent list）")
        if descriptor.needs_compute:
            sub.add_argument("--compute", default="",
                             help="在哪台机器上跑（ai4sci show computes 里的名字）；缺省照清单")
        for param in descriptor.params:
            # argparse 把 help 当 % 格式串：描述符里写"1%"是给人看的，这里得转义
            flag, help_text = f"--{param.name.replace('_', '-')}", param.help.replace("%", "%%")
            if param.type == "bool":
                sub.add_argument(flag, dest=param.name, action="store_true", help=help_text)
            else:
                sub.add_argument(flag, dest=param.name, type=PARAM_TYPES[param.type],
                                 default=param.default, help=help_text)
        sub.add_argument("--detach", action="store_true",
                         help="起成后台作业：它开了产出就打印作业号与产出 id，当场没开起来的"
                              "直接报；进度看 ai4sci show job <作业号>")
        sub.set_defaults(func=cmd_cap, module=module)
