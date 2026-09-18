"""`ai4sci show workspaces | task | run <id> | jobs | job <id> | flows | caps | workflows`

在 cli 层。这一组只看不做：不产出文件、不起会话、不改任何东西。与 `ai4sci serve` 的 GET
端点读的是同一批函数——页面和终端是同一份数据的两张脸。task / run / jobs / flows 看的是
当前工作区（P-15）；caps / workflows 看的是库。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from framework import paths
from framework.capabilities import discover
from framework.cli._common import (
    EXIT_INVALID,
    EXIT_OK,
    EXIT_USAGE,
    current_workspace,
    open_run_dir,
)
from framework.contracts import packs, workflows
from framework.contracts.capability import COLUMNS, STAGES
from framework.contracts.report import read_report
from framework.memory import ledger
from framework.run import flow_state, jobs, layout, workspace
from framework.run.checkpoint import read_checkpoint
from framework.run.context import load_manifest


def cmd_workspaces(args: argparse.Namespace) -> int:
    """全部工作区：id、标题、在哪。"""
    for ws in workspace.list_workspaces(workspace.workspaces_root(paths.home())):
        meta = ws.meta()
        print(f"{ws.id}\t{meta.get('title') or ws.id}\t{ws.root}")
    return EXIT_OK


def cmd_task(args: argparse.Namespace) -> int:
    """当前工作区的任务包合不合契约：问题一行一条到 stderr，通就打 ok。"""
    ws = current_workspace()
    if isinstance(ws, int):
        return ws
    if not ws.task.is_dir():
        print(f"这个工作区还没有任务包：先 ai4sci cap init（{ws.task}）", file=sys.stderr)
        return EXIT_INVALID
    problems = packs.validate_task(ws.task, paths.domains_root())
    if problems:
        for problem in problems:
            print(problem, file=sys.stderr)
        return EXIT_INVALID
    print(f"ok {ws.id}")
    return EXIT_OK


def cmd_run(args: argparse.Namespace) -> int:
    """一个 run 的状态：best、账本尾部、停止原因、分析与验证有没有；末尾账本 × git 对账。"""
    ws = current_workspace()
    if isinstance(ws, int):
        return ws
    run_dir = open_run_dir(ws, args.run_id)
    if isinstance(run_dir, int):
        return run_dir
    state = read_checkpoint(run_dir)
    print(f"run_id\t{state['run_id']}")
    print(f"source\t{load_manifest(run_dir).get('source') or '-'}")  # manifest.source 的读取点
    print(f"last_iter\t{state['last_iter']}")
    print(f"best_iter\t{state['best_iter']}")
    print(f"best_metric\t{state['best_metric']}")
    print(f"best_commit\t{state['best_commit']}")
    print(f"stop_reason\t{state.get('stop_reason') or '-'}")
    ledger_path = layout.ledger(run_dir)
    rows = ledger.read(ledger_path)
    print(f"ledger_rows\t{len(rows)}")
    for row in rows[-args.tail:]:
        metric = "-" if row.metric is None else f"{row.metric:.6g}"
        print(f"{row.iter}\t{row.status}\t{metric}\t{row.commit[:12]}\t{row.note}")
    analysis = layout.analysis_doc(run_dir)
    print(f"analysis\t{analysis.relative_to(run_dir) if analysis.is_file() else '-'}")
    report = layout.verify_report(run_dir)
    try:
        print(f"verify\t{read_report(report)['status'] if report.is_file() else '-'}")
    except ValueError as exc:
        # 报告不合约就当没有报告：打出来退 1，别把坏报告的 status 当结论
        print(str(exc), file=sys.stderr)
        return EXIT_INVALID
    for job in jobs.jobs_for(ws.jobs, state["run_id"]):
        print(f"job\t{job.job_id}\t{jobs.effective_status(job)}\t{job.cap}\t{job.result}")
    flow = flow_state.status(run_dir, ws.jobs)
    if flow is not None:
        following = flow["next"]
        print(f"workflow\t{flow['workflow']}\tstep={flow['step']}/{flow['total']}"
              f"\twaiting={flow['waiting']}"
              f"\tnext={'-' if following is None else _next_word(following)}")
    # 账本 × git 的对账放在这里跑：不对账的状态只是"它自己说它没事"（P-3）
    problems = ledger.reconcile(ledger_path, layout.work(run_dir))
    if problems:
        for problem in problems:
            print(problem, file=sys.stderr)
        return EXIT_INVALID
    return EXIT_OK


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
    return (f"{job.job_id}\t{jobs.effective_status(job)}\t{job.cap}\t{job.target}"
            f"\tstarted={job.started_at}\tfinished={job.finished_at or '-'}"
            f"\texit={'-' if job.exit_code is None else job.exit_code}\t{job.result}")


def cmd_caps(args: argparse.Namespace) -> int:
    """能力清单：七间房、每间里的能力，空着的房间也列出来。每颗带五栏（干什么 / 不干什么 /
    要带什么进来 / 留下什么 / 什么时候停）与"用在哪几条流"——后者是从库里的工作流文件反查的，
    能力自己不知道。"""
    descriptors = [module.DESCRIPTOR for module in discover().values()]
    # 坏掉的工作流文件不算进反查；坏在哪由 show workflows 报
    uses = workflows.used_by(workflows.load_valid(paths.workflows_root()))
    if args.json:
        print(json.dumps([{**d.to_dict(), "used_by": uses.get(d.name, [])} for d in descriptors],
                         ensure_ascii=False, indent=2))
        return EXIT_OK
    for stage in STAGES:
        caps = [d for d in descriptors if d.stage == stage]
        if not caps:
            print(f"{stage}\t-\t这一间还没有能力")
        for d in caps:
            who = "助理" if d.needs_executor else "机器"
            params = " ".join(f"--{p.name.replace('_', '-')}" for p in d.params) or "-"
            print(f"{stage}\t{d.name}\t{d.title}\t{who}\t{d.level}\t参数 {params}"
                  f"\tused_by={','.join(uses.get(d.name, [])) or '-'}")
            for key, label in COLUMNS:
                print(f"  {label}：{getattr(d, key)}")
    return EXIT_OK


def _catalog():
    return {name: module.DESCRIPTOR for name, module in discover().items()}


def cmd_workflows(args: argparse.Namespace) -> int:
    """库里的工作流：每条一行带走过的房间，点名的能力不在那一间、参数不对的退 1；提醒只打不退。"""
    return _print_flows(paths.workflows_root(), args.json)


def cmd_flows(args: argparse.Namespace) -> int:
    """当前工作区里的流实例：从库里取来、改过参数的那几条，同一套形状检查。"""
    ws = current_workspace()
    if isinstance(ws, int):
        return ws
    return _print_flows(ws.flows, args.json)


def _print_flows(root: Path, as_json: bool) -> int:
    found = workflows.describe_dir(root, _catalog())  # 坏文件也是一条，problems 里说原因
    if as_json:
        print(json.dumps(found, ensure_ascii=False, indent=2))
    else:
        for wf in found:
            rooms = " → ".join(_room_word(item) for item in wf["rooms"])
            print(f"{wf['name']}\t{wf['title']}\t{rooms or '-'}")
            for remark in wf["remarks"]:
                print(f"  · {remark}")
            for problem in wf["problems"]:
                print(f"  ! {problem}", file=sys.stderr)
    return EXIT_INVALID if any(wf["problems"] for wf in found) else EXIT_OK


def _next_word(item: dict) -> str:
    """便条上的下一项，给人念的一句：进哪一间（点了名带能力），或停在哪个断点等谁。"""
    if item["kind"] == "stop":
        return f"断点：{item['note'] or '等你确认'}"
    picks = "、".join(c["cap"] for c in item["caps"])
    return f"{item['stage']}间" + (f"（{picks}）" if picks else "")


def _room_word(item: dict) -> str:
    """一项一个词：房间名（点了名带能力），断点画成 ◆（带键的写键名）。"""
    if item["kind"] == "stop":
        return f"◆{item['key'] or ''}"
    picks = ",".join(c["cap"] for c in item["caps"])
    return f"{item['stage']}({picks})" if picks else item["stage"]


def add_parser(groups: argparse._SubParsersAction) -> None:
    show = groups.add_parser("show", help="只读查询：工作区、任务包、run、作业、流、能力清单")
    what = show.add_subparsers(dest="what", required=True)

    spaces = what.add_parser("workspaces", help="列出全部工作区：id、标题、在哪")
    spaces.set_defaults(func=cmd_workspaces)

    task = what.add_parser("task", help="校验当前工作区的任务包合不合契约")
    task.set_defaults(func=cmd_task)

    run = what.add_parser("run", help="一个 run 的 best、账本尾部与停止原因；顺带账本 × git 对账")
    run.add_argument("run_id")
    run.add_argument("--tail", type=int, default=5, help="账本尾部行数，缺省 5")
    run.set_defaults(func=cmd_run)

    listing = what.add_parser("jobs", help="当前工作区的作业清单：每个后台作业的状态与结论")
    listing.set_defaults(func=cmd_jobs)

    one = what.add_parser("job", help="一个作业：状态、命令、结论行、日志在哪")
    one.add_argument("job_id")
    one.set_defaults(func=cmd_job)

    flows = what.add_parser("flows", help="当前工作区的流实例（flows/*.yaml）：走哪几间、有无问题")
    flows.add_argument("--json", action="store_true", help="打 JSON（给页面）")
    flows.set_defaults(func=cmd_flows)

    caps = what.add_parser("caps", help="能力清单：七间房、每间里的能力与五栏说明，带用在哪几条流")
    caps.add_argument("--json", action="store_true", help="打 JSON（给页面与脚本）")
    caps.set_defaults(func=cmd_caps)

    wfs = what.add_parser("workflows", help="库里的工作流（workflows/*.yaml）：走哪几间、有无问题")
    wfs.add_argument("--json", action="store_true", help="打 JSON（给页面）")
    wfs.set_defaults(func=cmd_workflows)
