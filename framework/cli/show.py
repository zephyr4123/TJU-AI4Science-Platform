"""`ai4sci show tasks | task <dir> | run <id> | caps | workflows | flow <能力>...`：只读查询。

在 cli 层。这一组只看不做：不产出文件、不起会话、不改任何东西。与 `ai4sci serve` 的 GET
端点读的是同一批函数——页面和终端是同一份数据的两张脸。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from framework.capabilities import discover
from framework.chat.guide import REPO_ROOT
from framework.cli._common import (
    EXIT_INVALID,
    EXIT_OK,
    EXIT_USAGE,
    add_runs_root,
    open_run_dir,
    runs_root,
)
from framework.contracts import packs, workflows
from framework.contracts.capability import STAGES
from framework.contracts.flow import check_flow, stage_remarks, stages_of
from framework.contracts.report import read_report
from framework.memory import ledger
from framework.run import flow_state, jobs, layout
from framework.run.checkpoint import read_checkpoint
from framework.run.context import load_manifest


def cmd_tasks(args: argparse.Namespace) -> int:
    """列出搜索路径下的任务包：id 与目录。"""
    root = Path(args.root) if args.root else REPO_ROOT
    if not root.is_dir():
        print(f"搜索路径不存在：{root}", file=sys.stderr)
        return EXIT_USAGE
    try:
        found = packs.discover_tasks(root)
    except (ValueError, NotADirectoryError) as exc:
        # 发现阶段的冲突是拓扑错误：报清楚并退非零，不静默跳过坏包（P-7）
        print(str(exc), file=sys.stderr)
        return EXIT_USAGE
    for task_id in sorted(found):
        print(f"{task_id}\t{found[task_id]}")
    return EXIT_OK


def cmd_task(args: argparse.Namespace) -> int:
    """校验一个任务包合不合契约：问题一行一条到 stderr，通就打 ok。"""
    task_dir = Path(args.task_dir)
    if not task_dir.is_dir():
        print(f"任务目录不存在：{task_dir}", file=sys.stderr)
        return EXIT_USAGE
    domains_root = Path(args.domains) if args.domains else packs.default_domains_root(task_dir)
    problems = packs.validate_task(task_dir, domains_root)
    if problems:
        for problem in problems:
            print(problem, file=sys.stderr)
        return EXIT_INVALID
    # 校验通过意味着 manifest.id 已经和目录名对上，这里可以直接拿目录名当 id
    print(f"ok {task_dir.resolve().name}")
    return EXIT_OK


def cmd_run(args: argparse.Namespace) -> int:
    """一个 run 的状态：best、账本尾部、停止原因、分析与验证有没有；末尾账本 × git 对账。"""
    run_dir = open_run_dir(args)
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
    for job in jobs.jobs_for(runs_root(args), state["run_id"]):
        print(f"job\t{job.job_id}\t{jobs.effective_status(job)}\t{job.cap}\t{job.result}")
    flow = flow_state.status(run_dir, runs_root(args))
    if flow is not None:
        following = flow["next"]
        print(f"workflow\t{flow['workflow']}\tstep={flow['step']}/{flow['total']}"
              f"\twaiting={flow['waiting']}"
              f"\tnext={'-' if following is None else following['by'] + '：' + following['does']}")
    # 账本 × git 的对账放在这里跑：不对账的状态只是"它自己说它没事"（P-3）
    problems = ledger.reconcile(ledger_path, layout.work(run_dir))
    if problems:
        for problem in problems:
            print(problem, file=sys.stderr)
        return EXIT_INVALID
    return EXIT_OK


def cmd_jobs(args: argparse.Namespace) -> int:
    """作业清单：每个 `--detach` 起的进程一条；状态探过 pid（running / done / failed / lost）。"""
    for job in jobs.list_jobs(runs_root(args)):
        print(_job_line(job))
    return EXIT_OK


def cmd_job(args: argparse.Namespace) -> int:
    try:
        job = jobs.load(runs_root(args), args.job_id)
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
    """能力清单：平台的全部按钮，按七个科研阶段列，空着的阶段也列出来。每颗带"用在哪几条流"，
    那是从工作流文件反查的，能力自己不知道。"""
    descriptors = [module.DESCRIPTOR for module in discover().values()]
    try:
        uses = workflows.used_by(workflows.load_workflows(workflows.workflows_root(REPO_ROOT)))
    except workflows.WorkflowInvalid as exc:
        # 坏掉的工作流文件不静默跳过：清单里"用在哪"会是错的
        print(str(exc), file=sys.stderr)
        return EXIT_INVALID
    if args.json:
        print(json.dumps([{**d.to_dict(), "used_by": uses.get(d.name, [])} for d in descriptors],
                         ensure_ascii=False, indent=2))
        return EXIT_OK
    for stage in STAGES:
        caps = [d for d in descriptors if d.stage == stage]
        if not caps:
            print(f"{stage}\t-\t还没有这一步的能力")
        for d in caps:
            print(f"{stage}\t{d.name}\t{d.title}\t{d.level}"
                  f"\texecutor={'yes' if d.needs_executor else 'no'}"
                  f"\tcompute={'yes' if d.needs_compute else 'no'}"
                  f"\tused_by={','.join(uses.get(d.name, [])) or '-'}\t{d.summary}")
    return EXIT_OK


def _catalog():
    return {name: module.DESCRIPTOR for name, module in discover().items()}


def cmd_workflows(args: argparse.Namespace) -> int:
    """预装的工作流：每条一行带覆盖的阶段，能力步骤对不上吃吐文件的退 1；提醒只打不退。"""
    try:
        found = workflows.describe(
            workflows.load_workflows(workflows.workflows_root(REPO_ROOT)), _catalog())
    except workflows.WorkflowInvalid as exc:
        print(str(exc), file=sys.stderr)
        return EXIT_INVALID
    if args.json:
        print(json.dumps(found, ensure_ascii=False, indent=2))
    else:
        for wf in found:
            steps = " → ".join(s["cap"] or f"[{s['key']}]" if (s["cap"] or s["key"]) else s["by"]
                               for s in wf["steps"])
            covers = " → ".join(wf["covers"]) or "-"
            print(f"{wf['name']}\t{wf['title']}\t覆盖 {covers}\t{steps}")
            for remark in wf["remarks"]:
                print(f"  · {remark}")
            for problem in wf["problems"]:
                print(f"  ! {problem}", file=sys.stderr)
    return EXIT_INVALID if any(wf["problems"] for wf in found) else EXIT_OK


def cmd_flow(args: argparse.Namespace) -> int:
    """一串能力按顺序通不通：只对吃吐文件，不跑。名字对不上退 2，不通退 1。"""
    catalog = _catalog()
    unknown = [name for name in args.steps if name not in catalog]
    if unknown:
        print(f"没有这些能力：{unknown}（有的：{sorted(catalog)}）", file=sys.stderr)
        return EXIT_USAGE
    steps = [catalog[name] for name in args.steps]
    covers = stages_of(steps)
    remarks = stage_remarks(covers)
    problems = check_flow(steps)
    if args.json:
        print(json.dumps({"steps": list(args.steps), "covers": covers, "remarks": remarks,
                          "problems": problems}, ensure_ascii=False, indent=2))
        return EXIT_INVALID if problems else EXIT_OK
    if problems:
        for problem in problems:
            print(problem, file=sys.stderr)
        return EXIT_INVALID
    print(f"ok {len(args.steps)} 步：{' → '.join(args.steps)}\t覆盖 {' → '.join(covers)}")
    for remark in remarks:
        print(f"  · {remark}")
    return EXIT_OK


def add_parser(groups: argparse._SubParsersAction) -> None:
    show = groups.add_parser("show", help="只读查询：任务包、run、能力清单、工作流、流通不通")
    what = show.add_subparsers(dest="what", required=True)

    tasks = what.add_parser("tasks", help="列出搜索路径下的任务包")
    tasks.add_argument("--root", default=None, help="仓根或 tasks/ 目录，缺省为本仓根")
    tasks.set_defaults(func=cmd_tasks)

    task = what.add_parser("task", help="校验一个任务包合不合契约")
    task.add_argument("task_dir", help="任务包目录")
    task.add_argument(
        "--domains", default=None,
        help=f"领域包根目录，缺省 ${packs.DOMAINS_ROOT_ENV} 或 <task_dir>/../../domains")
    task.set_defaults(func=cmd_task)

    run = what.add_parser("run", help="一个 run 的 best、账本尾部与停止原因；顺带账本 × git 对账")
    run.add_argument("run_id")
    run.add_argument("--tail", type=int, default=5, help="账本尾部行数，缺省 5")
    add_runs_root(run)
    run.set_defaults(func=cmd_run)

    listing = what.add_parser("jobs", help="作业清单：--detach 起的每个进程的状态与结论")
    add_runs_root(listing)
    listing.set_defaults(func=cmd_jobs)

    one = what.add_parser("job", help="一个作业：状态、命令、结论行、日志在哪")
    one.add_argument("job_id")
    add_runs_root(one)
    one.set_defaults(func=cmd_job)

    caps = what.add_parser("caps", help="能力清单：按七个科研阶段列全部按钮，带用在哪几条流")
    caps.add_argument("--json", action="store_true", help="打 JSON（给页面与脚本）")
    caps.set_defaults(func=cmd_caps)

    wfs = what.add_parser("workflows", help="预装的工作流（workflows/*.yaml）：覆盖的阶段、通不通")
    wfs.add_argument("--json", action="store_true", help="打 JSON（给页面）")
    wfs.set_defaults(func=cmd_workflows)

    flow = what.add_parser("flow", help="一串能力按顺序通不通：只对吃吐文件，不跑")
    flow.add_argument("steps", nargs="+", help="能力名，按顺序")
    flow.add_argument("--json", action="store_true", help="打 JSON")
    flow.set_defaults(func=cmd_flow)
