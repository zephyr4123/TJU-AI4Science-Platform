"""`ai4sci show workspaces | workspace | outputs [<stage>] | output <stage>/<n> | jobs | job <id>
| flows | caps | workflows | templates | template <name> | computes`

在 cli 层。这一组只看不做：不产出文件、不起会话、不改任何东西。与 `ai4sci serve` 的 GET
端点读的是同一批函数（`chat.boards`）——页面和终端是同一份数据的两张脸。workspace / outputs /
output / jobs / flows 看的是当前工作区（P-15）；caps / workflows / templates 看的是库。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from framework import computes, paths
from framework.capabilities import discover
from framework.chat import boards
from framework.cli._common import EXIT_INVALID, EXIT_OK, EXIT_USAGE, current_workspace
from framework.cli.workspace import read_template
from framework.contracts import output, workflows
from framework.contracts.capability import COLUMNS
from framework.contracts.stages import STAGE_SLUGS, STAGES
from framework.workspace import jobs, outputs, root


def cmd_workspaces(args: argparse.Namespace) -> int:
    """全部工作区：id、标题、需求确认了没、在哪。"""
    for ws in root.list_workspaces(root.workspaces_root(paths.home())):
        state = ws.to_dict()["requirement"]
        confirmed = f"v{state['version']}" + ("（有改动未确认）" if state["dirty"] else "") \
            if state["confirmed"] else "未确认"
        print(f"{ws.id}\t{ws.title()}\t需求 {confirmed}\t{ws.root}")
    return EXIT_OK


def cmd_workspace(args: argparse.Namespace) -> int:
    """当前工作区的全貌：需求状态、每个阶段有几次产出、每条流程走到哪、在等谁、跑着的作业。"""
    ws = current_workspace()
    if isinstance(ws, int):
        return ws
    detail = boards.workspace_detail(ws, _catalog())
    if args.json:
        print(json.dumps(boards.jsonable(detail), ensure_ascii=False, indent=2))
        return EXIT_OK
    req = detail["requirement"]
    dirty = "（有改动未确认）" if req["dirty"] else ""
    state = (f"v{req['version']} by {req['by']} {req['at']}{dirty}"
             if req["confirmed"] else "未确认")
    print(f"workspace\t{ws.id}\t{detail['title']}")
    print(f"requirement\t{state}")
    for stage in detail["stages"]:
        outs = stage["outputs"]
        if not outs:
            continue
        print(f"{stage['slug']}\t{len(outs)} 次")
        for o in outs:
            print(f"  {o['id']}\t{o['status']}\t{o['by']}\tfrom={','.join(o['from']) or '-'}"
                  f"\tsigned={_signed_word(o['signed'])}\t{o['title']}")
    for flow in detail["flows"]:
        if flow.get("problems"):
            print(f"flow\t{flow['name']}\t坏了：{flow['problems'][0]}", file=sys.stderr)
            continue
        print(f"flow\t{flow['name']}\tstep={flow['step'] + 1}/{flow['total']}"
              f"\twaiting={flow['waiting']}")
    for job in detail["jobs"]:
        print(f"job\t{job['job_id']}\t{job['effective_status']}\t{job['cap']}"
              f"\t{job['output'] or '-'}")
    return EXIT_OK


def cmd_outputs(args: argparse.Namespace) -> int:
    """当前工作区的产出清单，可按阶段筛。"""
    ws = current_workspace()
    if isinstance(ws, int):
        return ws
    if args.stage and args.stage not in STAGE_SLUGS:
        print(f"阶段目录只认 {STAGE_SLUGS}，得到 {args.stage!r}", file=sys.stderr)
        return EXIT_USAGE
    for directory, meta in outputs.list_outputs(ws, args.stage or None):
        signed = output.signature_state(directory)
        print(f"{meta.id}\t{meta.status}\t{meta.by}\tfrom={','.join(meta.input_ids) or '-'}"
              f"\tflow={meta.flow or '-'}\tsigned={_signed_word(signed)}\t{meta.title}")
    return EXIT_OK


def cmd_output(args: argparse.Namespace) -> int:
    """一次产出：meta、签字、目录里有什么。"""
    ws = current_workspace()
    if isinstance(ws, int):
        return ws
    try:
        detail = boards.output_detail(ws, args.output)
    except (ValueError, output.OutputNotFound) as exc:
        print(str(exc), file=sys.stderr)
        return EXIT_USAGE
    if args.json:
        print(json.dumps(boards.jsonable(detail), ensure_ascii=False, indent=2))
        return EXIT_OK
    for key in ("id", "title", "status", "by", "created_at", "finished_at", "flow", "step",
                "requirement", "result", "error"):
        value = detail[key]
        if value not in (None, ""):
            print(f"{key}\t{value}")
    print(f"from\t{','.join(detail['from']) or '-'}")
    signed = detail["signed"]
    who = f"\t{signed['by']} {signed['signed_at']} {signed['note']}" if signed else ""
    print(f"signed\t{_signed_word(signed)}{who}")
    for entry in detail["files"]:
        print(f"file\t{entry['path']}\t{entry['size']}")
    return EXIT_OK if detail["status"] != "failed" else EXIT_INVALID


def cmd_computes(args: argparse.Namespace) -> int:
    """按人的算力清单（P-23）：名字、种类、去向、GPU、上次探测过没过；缺省那台标出来。"""
    try:
        registry = computes.load()
    except computes.ComputesInvalid as exc:
        print(str(exc), file=sys.stderr)
        return EXIT_INVALID
    for entry in registry.entries.values():
        print(entry.summary() + ("\t(缺省)" if entry.name == registry.default else ""))
    return EXIT_OK


def _signed_word(signed) -> str:
    if not signed:
        return "-"
    if isinstance(signed, dict):
        return "stale" if signed.get("stale") else "yes"
    return "yes"


def cmd_jobs(args: argparse.Namespace) -> int:
    """作业清单：每个 `--detach` 起的进程一条；状态探过 pid（running / done / failed / lost）。"""
    ws = current_workspace()
    if isinstance(ws, int):
        return ws
    for job in jobs.list_jobs(ws.jobs):
        print(_job_line(job))
    return EXIT_OK


def cmd_job(args: argparse.Namespace) -> int:
    ws = current_workspace()
    if isinstance(ws, int):
        return ws
    try:
        job = jobs.load(ws.jobs, args.job_id)
    except jobs.JobNotFound as exc:
        print(str(exc), file=sys.stderr)
        return EXIT_USAGE
    print(_job_line(job))
    print(f"argv\tai4sci {' '.join(job.argv)}")
    print(f"log\t{job.log}")
    return EXIT_OK if jobs.effective_status(job) != "failed" else EXIT_INVALID


def _job_line(job: jobs.Job) -> str:
    return (f"{job.job_id}\t{jobs.effective_status(job)}\t{job.cap}\t{job.output or '-'}"
            f"\tstarted={job.started_at}\tfinished={job.finished_at or '-'}"
            f"\texit={'-' if job.exit_code is None else job.exit_code}\t{job.result}")


def cmd_caps(args: argparse.Namespace) -> int:
    """能力清单：七个研究阶段、每个阶段里的能力，空着的阶段也列出来。每个带五栏（干什么 / 不干什么 /
    要带什么进来 / 留下什么 / 什么时候停）与"用在哪几条流程"——后者是从库里的流程文件反查的，
    能力自己不知道。"""
    descriptors = [module.DESCRIPTOR for module in discover().values()]
    # 坏掉的流程文件不算进反查；坏在哪由 show workflows 报
    uses = workflows.used_by(workflows.load_valid(paths.workflows_root()))
    if args.json:
        print(json.dumps([{**d.to_dict(), "used_by": uses.get(d.name, [])} for d in descriptors],
                         ensure_ascii=False, indent=2))
        return EXIT_OK
    for stage in STAGES:
        caps = [d for d in descriptors if d.stage == stage.name]
        if not caps:
            print(f"{stage.name}\t-\t这个阶段还没有能力"
                  f"（助理可以 ai4sci output new {stage.slug} 自己写）")
        for d in caps:
            params = " ".join(f"--{p.name.replace('_', '-')}" for p in d.params) or "-"
            print(f"{stage.name}\t{d.name}\t{d.title}\t{d.brief}\t参数 {params}"
                  f"\tused_by={','.join(uses.get(d.name, [])) or '-'}")
            for key, label in COLUMNS:
                print(f"  {label}：{getattr(d, key)}")
    return EXIT_OK


def _catalog():
    return {name: module.DESCRIPTOR for name, module in discover().items()}


def cmd_workflows(args: argparse.Namespace) -> int:
    """库里的流程：每条一行带走过的阶段，点名的能力不在那个阶段、参数不对的退 1；提醒只打不退。"""
    return _print_flows(paths.workflows_root(), args.json)


def cmd_flows(args: argparse.Namespace) -> int:
    """当前工作区里的流程实例：从库里取来、改过参数的那几条，同一套形状检查。"""
    ws = current_workspace()
    if isinstance(ws, int):
        return ws
    return _print_flows(ws.flows, args.json)


def _print_flows(root_dir: Path, as_json: bool) -> int:
    found = workflows.describe_dir(root_dir, _catalog())  # 坏文件也是一条，problems 里说原因
    if as_json:
        print(json.dumps(found, ensure_ascii=False, indent=2))
    else:
        for wf in found:
            stages = " → ".join(_stage_word(item) for item in wf["stages"])
            print(f"{wf['name']}\t{wf['title']}\t{stages or '-'}")
            for remark in wf["remarks"]:
                print(f"  · {remark}")
            for problem in wf["problems"]:
                print(f"  ! {problem}", file=sys.stderr)
    return EXIT_INVALID if any(wf["problems"] for wf in found) else EXIT_OK


def _stage_word(item: dict) -> str:
    """一项一个词：阶段名（点了名带能力），断点画成 ◆（带一句话就写）。"""
    if item["kind"] == "stop":
        return f"◆{item['note'] or ''}"
    picks = ",".join(c["cap"] for c in item["caps"])
    return f"{item['stage']}({picks})" if picks else item["stage"]


def cmd_templates(args: argparse.Namespace) -> int:
    """库里的需求模板：名字与第一行说明。"""
    for item in boards.list_templates(paths.templates_root()):
        print(f"{item['name']}\t{item['title']}\t{item['summary']}")
    return EXIT_OK


def cmd_template(args: argparse.Namespace) -> int:
    try:
        print(read_template(args.name), end="")
    except FileNotFoundError as exc:
        print(str(exc), file=sys.stderr)
        return EXIT_USAGE
    return EXIT_OK


def add_parser(groups: argparse._SubParsersAction) -> None:
    show = groups.add_parser("show", help="只读查询：工作区、产出、作业、流程、能力清单、需求模板")
    what = show.add_subparsers(dest="what", required=True)
    spaces = what.add_parser("workspaces", help="列出全部工作区：id、标题、需求状态、在哪")
    spaces.set_defaults(func=cmd_workspaces)
    space = what.add_parser("workspace",
                            help="当前工作区的全貌：需求、每个阶段的产出、每条流程走到哪、作业")
    space.add_argument("--json", action="store_true", help="打 JSON（给页面与脚本）")
    space.set_defaults(func=cmd_workspace)
    outs = what.add_parser("outputs", help="当前工作区的产出清单，可按阶段筛")
    outs.add_argument("stage", nargs="?", default="", help=f"阶段目录：{' / '.join(STAGE_SLUGS)}")
    outs.set_defaults(func=cmd_outputs)
    one = what.add_parser("output", help="一次产出：记录、签字、目录里有什么")
    one.add_argument("output", metavar="STAGE/N")
    one.add_argument("--json", action="store_true", help="打 JSON")
    one.set_defaults(func=cmd_output)
    listing = what.add_parser("jobs", help="当前工作区的作业清单：每个后台作业的状态与结论")
    listing.set_defaults(func=cmd_jobs)
    job = what.add_parser("job", help="一个作业：状态、命令、结论行、日志在哪")
    job.add_argument("job_id")
    job.set_defaults(func=cmd_job)
    flows = what.add_parser("flows",
                            help="当前工作区的流程实例（flows/*.yaml）：经过哪些阶段、有无问题")
    flows.add_argument("--json", action="store_true", help="打 JSON（给页面）")
    flows.set_defaults(func=cmd_flows)
    caps = what.add_parser("caps",
                           help="能力清单：七个研究阶段各有什么能力、每个五栏说明，带用在哪几条流程")
    caps.add_argument("--json", action="store_true", help="打 JSON（给页面与脚本）")
    caps.set_defaults(func=cmd_caps)
    wfs = what.add_parser("workflows",
                          help="库里的流程（workflows/*.yaml）：经过哪些阶段、有无问题")
    wfs.add_argument("--json", action="store_true", help="打 JSON（给页面）")
    wfs.set_defaults(func=cmd_workflows)
    tpls = what.add_parser("templates", help="库里的需求模板：通用一份、按学科加")
    tpls.set_defaults(func=cmd_templates)
    tpl = what.add_parser("template", help="一份需求模板的原文")
    tpl.add_argument("name")
    tpl.set_defaults(func=cmd_template)
    comps = what.add_parser("computes", help="按人的算力清单：名字、种类、去向、GPU、状态（P-23）")
    comps.set_defaults(func=cmd_computes)
