"""看板读盘：工作区（需求、七个阶段的产出、每条流走到哪、作业）与一次产出的细节。纯读盘、零模型。

页面是 `ai4sci serve` 的客户端（`ui/README.md`）：这里每个函数就是一个端点的响应体，
server 只做路由；换一种 UI（TUI）读的也是同一份东西。每个响应体都是能直接 `json.dumps`
的字典——NaN 在这里就换成 None，浏览器的 JSON.parse 不认 NaN。

按纲领 P-19 只读框架认的东西：需求、meta.yaml、signed.json、流文件、作业。产出目录里其它文件只列名字
（页面按文件种类通用渲染），不解释内容。
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any

from framework.contracts import output, requirement, workflows
from framework.contracts.capability import Capability
from framework.contracts.stages import STAGES
from framework.workspace import jobs, outputs, progress
from framework.workspace.root import Workspace

# 产出目录里给页面列文件时跳过的：框架的两份文件、环境、git、日志、缓存
LISTING_IGNORED = frozenset({output.META_NAME, output.SIGNED_NAME, ".venv", ".git", "__pycache__",
                             ".ai4sci", "executor"})
LISTING_LIMIT = 200
# 小文本文件的正文直接带上，页面照渲染；大的与二进制只给名字。
# 没有后缀的（python-version、SHA256SUMS）也当文本试着读，读不出来就只给名字
TEXT_SUFFIXES = (".md", ".txt", ".yaml", ".yml", ".json", ".tsv", ".csv", ".py", ".sh", ".lock",
                 ".toml", ".cfg", ".ini", ".log", "")
TEXT_LIMIT = 200_000


# ── 工作区 ───────────────────────────────────────────────────────────────
def workspace_summary(workspace: Workspace) -> dict[str, Any]:
    """地方栏用的一行：标题、需求状态、每个阶段有几次产出、有没有作业在跑。"""
    found = outputs.list_outputs(workspace)
    counts = {s.slug: 0 for s in STAGES}
    for _, meta in found:
        counts[meta.stage] += 1
    return {**workspace.to_dict(), "counts": counts,
            "running": len(jobs.running_jobs(workspace.jobs))}


def workspace_detail(workspace: Workspace, catalog: dict[str, Capability]) -> dict[str, Any]:
    """主页面要的一整份：需求 + 七个阶段各自的产出 + 每条流实例的进度 + 作业。"""
    found = outputs.list_outputs(workspace)
    briefs = {meta.id: output_brief(directory, meta) for directory, meta in found}
    stages = [{"name": s.name, "slug": s.slug,
               "outputs": [b for b in briefs.values() if b["stage"] == s.slug]}
              for s in STAGES]
    flows = []
    for described in workflows.describe_dir(workspace.flows, catalog):
        if described["problems"]:
            flows.append(described)
            continue
        wf = workflows.load_workflow(workspace.flows / f"{described['name']}.yaml")
        flows.append({**described, **progress.flow_progress(workspace, wf, found)})
    return {**workspace_summary(workspace), "requirement": requirement_detail(workspace),
            "stages": stages, "flows": flows,
            "jobs": [job.to_dict() for job in jobs.list_jobs(workspace.jobs)]}


# ── 需求 ─────────────────────────────────────────────────────────────────
def requirement_detail(workspace: Workspace) -> dict[str, Any]:
    """需求文档与确认状态：原文、按二级标题切的格、上一版确认的原文（页面做 diff）。"""
    text = requirement.read(workspace.root) if workspace.requirement.is_file() else ""
    state = requirement.status(workspace.root)
    return {**state, "title": requirement.title(text, workspace.id), "text": text,
            "sections": [s.to_dict() for s in requirement.sections(text)],
            "pending": requirement.PLACEHOLDER in text,
            "confirmed_text": (requirement.confirmed_text(workspace.root)
                               if state["confirmed"] else None)}


# ── 产出 ─────────────────────────────────────────────────────────────────
def output_brief(directory: Path, meta: output.Meta) -> dict[str, Any]:
    signed = output.signature_state(directory)
    return {"id": meta.id, "stage": meta.stage, "title": meta.title, "status": meta.status,
            "by": meta.by, "from": meta.input_ids, "params": meta.params, "flow": meta.flow,
            "step": meta.step, "requirement": meta.requirement, "chat_id": meta.chat_id,
            "created_at": meta.created_at, "finished_at": meta.finished_at,
            "result": meta.result, "error": meta.error, "signed": signed}


def output_detail(workspace: Workspace, oid: str) -> dict[str, Any]:
    """一次产出：记录 + 目录里的文件清单（小文本带正文）+ 它的作业。"""
    directory, meta = outputs.find_output(workspace, oid)
    files: list[dict[str, Any]] = []
    for path in sorted(p for p in directory.rglob("*") if p.is_file()):
        rel = path.relative_to(directory)
        if any(part in LISTING_IGNORED for part in rel.parts):
            continue
        entry: dict[str, Any] = {"path": rel.as_posix(), "size": path.stat().st_size}
        if path.suffix in TEXT_SUFFIXES and entry["size"] <= TEXT_LIMIT:
            try:
                entry["text"] = path.read_bytes().decode("utf-8")
            except UnicodeDecodeError:
                pass  # 没后缀的二进制：只给名字

        files.append(entry)
        if len(files) >= LISTING_LIMIT:
            break
    return {**output_brief(directory, meta), "files": files,
            "jobs": [job.to_dict() for job in jobs.jobs_for(workspace.jobs, meta.id)]}


# ── 模板 ─────────────────────────────────────────────────────────────────
def list_templates(root: Path) -> list[dict[str, str]]:
    """库里的需求模板：名字、一级标题、第一段说明（模板开头 `>` 引用块或第一段正文）。"""
    found = []
    for path in sorted(Path(root).glob("*.md")):
        text = path.read_text(encoding="utf-8")
        found.append({"name": path.stem, "title": requirement.title(text, path.stem),
                      "summary": _first_paragraph(text), "text": text})
    return found


def _first_paragraph(text: str) -> str:
    for block in text.split("\n\n"):
        line = block.strip()
        if line and not line.startswith("#"):
            return " ".join(line.lstrip("> ").split())
    return ""


def jsonable(value: Any) -> Any:
    """递归把 NaN / ±inf 换成 None：账本里「未知」的耗时与成本就是 NaN（不是 0），
    但 JSON 标准没有 NaN，浏览器解析会直接炸。"""
    if isinstance(value, float):
        return None if math.isnan(value) or math.isinf(value) else value
    if isinstance(value, dict):
        return {k: jsonable(v) for k, v in value.items()}
    if isinstance(value, list | tuple):
        return [jsonable(v) for v in value]
    return value
