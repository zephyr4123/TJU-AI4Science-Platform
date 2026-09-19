"""看板读盘：工作区（需求、七个阶段的产出、每条流程走到哪、作业）与一次产出的细节。纯读盘、零模型。

页面是 `ai4sci serve` 的客户端（`ui/README.md`）：这里每个函数就是一个端点的响应体，
server 只做路由；换一种 UI（TUI）读的也是同一份东西。每个响应体都是能直接 `json.dumps`
的字典——NaN 在这里就换成 None，浏览器的 JSON.parse 不认 NaN。

按纲领 P-19 只读框架认的东西：需求、meta.yaml、signed.json、流程文件、作业。产出目录里其它文件
只列名字
（页面按文件种类通用渲染），不解释内容。

文件镜头（外层 #111）：工作区的目录一层一层懒加载、一个文件的正文、一个文件原样端出。只读；路径出了
工作区一律拒。阶段名、产出状态这些语义页面自己从 `workspace_detail` 拼，这里不重复。
"""

from __future__ import annotations

import math
import mimetypes
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
# 文件镜头：目录树里整段跳过的（环境、git 对象库、缓存——几千个文件，对人没意义）；
# 正文最多给这么多字节，再大截断；原样端出的文件上限（数据集不该从这儿下）
TREE_SKIPPED = frozenset({".venv", ".git", "__pycache__", "node_modules"})
RAW_LIMIT = 50_000_000


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
    """主页面要的一整份：需求 + 七个阶段各自的产出 + 每条流程实例的进度 + 作业。"""
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


# ── 文件镜头 ─────────────────────────────────────────────────────────────
def resolve_path(workspace: Workspace, rel: str) -> Path:
    """工作区里的相对路径 → 绝对路径。绝对路径、`..`、符号链接指到工作区外的都拒（ValueError）。"""
    parts = [p for p in rel.split("/") if p]
    if rel.startswith("/") or any(p == ".." for p in parts):
        raise ValueError(f"路径要在工作区里：{rel}")
    base = workspace.root.resolve()
    target = base.joinpath(*parts).resolve()
    if target != base and base not in target.parents:
        raise ValueError(f"路径要在工作区里：{rel}")
    return target


def list_dir(workspace: Workspace, rel: str) -> dict[str, Any]:
    """目录的一层：目录在前、名字排序；`TREE_SKIPPED` 里的不列。"""
    directory = resolve_path(workspace, rel)
    if not directory.is_dir():
        raise FileNotFoundError(f"没有这个目录：{rel}")
    entries: list[dict[str, Any]] = []
    for path in sorted(directory.iterdir(), key=lambda p: (not p.is_dir(), p.name)):
        if path.name in TREE_SKIPPED:
            continue
        entries.append({"name": path.name, "kind": "dir" if path.is_dir() else "file",
                        "size": None if path.is_dir() else path.stat().st_size})
    return {"path": "/".join(p for p in rel.split("/") if p), "entries": entries}


def read_file(workspace: Workspace, rel: str) -> dict[str, Any]:
    """一个文件：文本带正文（超过 TEXT_LIMIT 截断、`truncated` 为真），二进制（解不出 utf-8 或
    含 NUL）`text` 是 None、页面走 raw 端点。不按后缀猜，按内容判。"""
    path = resolve_path(workspace, rel)
    if not path.is_file():
        raise FileNotFoundError(f"没有这个文件：{rel}")
    size = path.stat().st_size
    with path.open("rb") as handle:
        head = handle.read(TEXT_LIMIT)
    truncated = size > TEXT_LIMIT
    text: str | None
    if b"\x00" in head:
        text = None
    else:
        try:
            # 截断处可能切在一个多字节字符中间，截断时丢掉那半个；没截断就严格判
            text = head.decode("utf-8", errors="ignore" if truncated else "strict")
        except UnicodeDecodeError:
            text = None
    return {"path": "/".join(p for p in rel.split("/") if p), "size": size, "text": text,
            "truncated": truncated and text is not None}


def raw_file(workspace: Workspace, rel: str) -> tuple[bytes, str]:
    """文件原样与 MIME 类型（图片让浏览器自己显示）；超过 RAW_LIMIT 拒。"""
    path = resolve_path(workspace, rel)
    if not path.is_file():
        raise FileNotFoundError(f"没有这个文件：{rel}")
    size = path.stat().st_size
    if size > RAW_LIMIT:
        raise ValueError(f"文件太大，不从页面端出：{rel}（{size} 字节）")
    kind, _ = mimetypes.guess_type(path.name)
    return path.read_bytes(), kind or "application/octet-stream"


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
