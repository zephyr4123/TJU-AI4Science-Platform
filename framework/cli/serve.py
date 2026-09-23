"""`ai4sci serve`：起网页的后端（HTTP + SSE）并把页面端出去，常驻直到 Ctrl-C。

cli 层里唯一常驻的命令：它不是"跑一个能力"，是给页面一个门。能力清单、流程库、拼流程检查与描述符表
从 `capabilities.discover` 与 `contracts.workflows` 拿，以函数传给 server
（chat 层不认识 capabilities）。数据根是 `AI4SCI_HOME`（缺省仓根）：工作区、编辑台的对话与人存的流程
都在它下面；流程库 = 出厂的 + 人存的（`_common.library`），页面存流程只写后者。

页面是 `ui/web` 构建出来的静态文件（`ui/README.md`）：缺省端 `ui/web/dist`，没构建就只开接口。
TUI 不走这里——它是终端进程，直接当这些接口的客户端。
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from framework import paths
from framework.capabilities import abilities, discover, stage_table
from framework.chat import guide, settings
from framework.chat.server import ChatServer
from framework.cli import compute as compute_cli
from framework.cli._common import EXIT_INVALID, EXIT_OK, EXIT_USAGE, library, setup_logging
from framework.contracts import workflows

DEFAULT_UI_DIR = paths.ui_dir()


def _add_compute(body: dict) -> dict:
    """页面「设置 → 算力 → 添加」：与 `ai4sci compute add` 同一段代码（写清单、就地探测、记回），
    回新的一整份设置。"""
    for key in ("name", "ssh", "key"):
        if not isinstance(body.get(key), str) or not body[key].strip():
            raise ValueError(f"body 要有非空的 {key}")
    compute_cli.add_and_check(body["name"].strip(), body["ssh"].strip(), body["key"].strip(),
                              str(body.get("root") or compute_cli.DEFAULT_ROOT),
                              bool(body.get("default")))
    return settings.snapshot()


def _descriptors() -> dict[str, object]:
    return abilities.steps()


def _skill_names() -> frozenset[str]:
    """两处库里 skill 的名字；与步骤重名当场报，不让页面拿到分辨不出的清单。"""
    names = abilities.skill_names()
    abilities.check_disjoint(set(discover()), names)
    return names


def _catalog() -> list[dict]:
    """与 `ai4sci show caps --json` 同一个形状：步骤描述符加 tag 与反查出来的 used_by。"""
    uses = workflows.used_by(library().load_valid())
    return [{**module.DESCRIPTOR.to_dict(), "kind": abilities.KIND_STEP,
             "used_by": uses.get(name, [])} for name, module in discover().items()]


def _skills() -> list[dict]:
    """能力库里 tag 为 skill 的那些：名字、一行、SKILL.md 正文、脚本名，加反查出来的 used_by。"""
    uses = workflows.used_by(library().load_valid())
    return [{**entry, "used_by": uses.get(entry["name"], [])}
            for entry in abilities.skill_entries()]


def _workflows() -> list[dict]:
    return library().describe(_descriptors(), _skill_names())


def _descriptor_map() -> dict[str, object]:
    return _descriptors()


def _save_workflow(doc: dict) -> dict:
    """编辑台存流程：核对形状与通不通，写进用户库（出厂的名字拒），回它在清单里的样子。"""
    catalog, skills = _descriptors(), _skill_names()
    overwrite = bool(doc.pop("overwrite", False))
    saved = library().save(doc, catalog, skills=skills, overwrite=overwrite)
    [described] = workflows.describe([saved], catalog, skills)
    return described


def _check_workflow(doc: dict) -> dict:
    """编辑台拼着的那条流程有没有问题：与存流程同一套检查，只查不写；形状不对也当问题报，页面不该为此
    拿 500。名字、标题、说明还没填是常态（人先排阶段），这里只查阶段那部分，三样空着的补个占位。"""
    catalog = _descriptors()
    name = str(doc.get("name") or "").strip() or "draft"
    doc = {k: v for k, v in doc.items() if k != "overwrite"}
    doc = {**doc, "name": name, "title": str(doc.get("title") or "").strip() or "-",
           "summary": str(doc.get("summary") or "").strip() or "-"}
    try:
        workflow = workflows.parse_workflow(f"{name}.yaml", doc)
    except workflows.WorkflowInvalid as exc:
        # 文件名前缀是给终端看的；页面上这条流程还没有文件
        return {"covers": [], "remarks": [], "problems": [str(exc).removeprefix(f"{name}.yaml: ")]}
    return {"covers": workflow.covered, "remarks": workflows.remarks(workflow),
            "problems": workflows.workflow_problems(workflow, catalog, _skill_names())}


def cmd_serve(args: argparse.Namespace) -> int:
    if args.ui:
        ui_dir = Path(args.ui)
        if not (ui_dir / "index.html").is_file():
            print(f"页面目录里没有 index.html：{ui_dir}", file=sys.stderr)
            return EXIT_USAGE
    else:
        ui_dir = DEFAULT_UI_DIR if (DEFAULT_UI_DIR / "index.html").is_file() else None
    setup_logging()
    try:
        server = ChatServer((args.host, args.port), home=paths.home(), catalog=_catalog,
                            skills=_skills, skill_names=_skill_names,
                            workflows=_workflows, check_workflow=_check_workflow,
                            save_workflow=_save_workflow, descriptors=_descriptor_map,
                            stage_table=stage_table, add_compute=_add_compute, ui_dir=ui_dir)
    except guide.GuideMissing as exc:
        print(str(exc), file=sys.stderr)
        return EXIT_INVALID
    host, port = server.server_address[:2]
    print(f"ok http://{host}:{port}\thome={server.home}\tui={ui_dir or '-'}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return EXIT_OK


def add_parser(groups: argparse._SubParsersAction) -> None:
    serving = groups.add_parser("serve", help="起网页后端：HTTP + SSE，端出页面，常驻")
    serving.add_argument("--host", default="127.0.0.1")
    serving.add_argument("--port", type=int, default=8765)
    serving.add_argument("--ui", default=None,
                         help=f"页面构建目录，缺省 {DEFAULT_UI_DIR}（没构建就只开接口）")
    serving.set_defaults(func=cmd_serve)
