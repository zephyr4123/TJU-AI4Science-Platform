"""产出：一个阶段目录下的一次产出 `<stage>/<n>/`，框架只认它里面的两份文件（纲领 P-19）。

    meta.yaml     谁产的、读了谁、在哪条流程第几项下产的、按哪版需求、成没成——框架写，能力不碰
    signed.json   人的签字：流程里这一项后面有断点才需要；签的是这个目录里全部文件的 hash

其余文件全归产它的那个能力，框架不看、不定、不校验。

id 就是路径（`experiment/2`）：读出来就知道是什么，不用查表；`title` 是给人看的标签。
多对多靠 `from`：meta 记读了哪几个产出、当时它们的内容 hash。冻结规则——一个产出被别的产出
`from` 过、或被签过，就冻住：hash 对不上就是有人事后改了它，下游拒读（`frozen_hash`）。
没被引用没被签之前随便改。

在契约层：只读写这两份文件与算目录 hash，不认识流程、能力、对话。
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

from framework.contracts.stages import STAGE_SLUGS, is_slug

META_NAME = "meta.yaml"
SIGNED_NAME = "signed.json"
# 算目录 hash 时跳过的：框架自己的两份文件、环境、git 仓、缓存——它们不是产物
HASH_IGNORED = frozenset({META_NAME, SIGNED_NAME, ".venv", ".git", "__pycache__", ".ai4sci"})
STATUSES = ("running", "ok", "failed")
# `<stage>/<n>`，读兄弟工作区的产出时前面加 `<工作区>:`（同一项目里，外层 #136）
_ID_RE = re.compile(r"^(?:([a-z][a-z0-9-]*):)?([a-z]+)/(\d+)$")


class OutputNotFound(FileNotFoundError):
    """没有这个产出。"""


class OutputChanged(ValueError):
    """产出被引用或被签之后改过了：hash 对不上，下游拒读。信息里说清怎么办。"""


class SignRefused(ValueError):
    """这次产出现在不能签：没成、或已经签过且没变。"""


@dataclass(frozen=True)
class OutputId:
    stage: str  # slug
    n: int
    # 兄弟工作区的名字（同一项目里）；None 就是自己的
    workspace: str | None = None

    @property
    def local(self) -> str:
        """在它自己工作区里的 id：目录名就是它。"""
        return f"{self.stage}/{self.n}"

    def __str__(self) -> str:
        return f"{self.workspace}:{self.local}" if self.workspace else self.local

    def path(self, root: Path) -> Path:
        """`root` 是它所在那个工作区的根（兄弟的就是兄弟的根）。"""
        return Path(root) / self.stage / str(self.n)


def parse_id(text: str) -> OutputId:
    """`[<工作区>:]<stage>/<n>` → OutputId；形状不对就 ValueError（信息给人看）。"""
    match = _ID_RE.match(text.strip())
    if not match or not is_slug(match.group(2)):
        raise ValueError(f"产出的 id 要写成 <阶段目录>/<序号>，比如 experiment/2；"
                         f"同一项目里兄弟工作区的"
                         f"写 <工作区>:<阶段目录>/<序号>，比如 gua:analysis/3；"
                         f"阶段目录：{STAGE_SLUGS}。得到 {text!r}")
    return OutputId(match.group(2), int(match.group(3)), match.group(1))


@dataclass
class Input:
    id: str
    sha256: str


@dataclass
class Meta:
    id: str
    stage: str
    title: str
    by: str
    created_at: str
    status: str = "running"
    inputs: list[Input] = field(default_factory=list)
    params: dict[str, Any] = field(default_factory=dict)
    flow: str | None = None
    step: int | None = None
    requirement: int | None = None
    chat_id: str | None = None
    finished_at: str | None = None
    result: str = ""
    error: str = ""
    # 在哪台机器上跑的（名字、种类、主机名、GPU；P-23 的出处）；不用算力的能力是 None
    compute: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        doc = asdict(self)
        doc["from"] = doc.pop("inputs")  # 文件里叫 from：读它的人看到的是「读了谁」
        return doc

    @property
    def input_ids(self) -> list[str]:
        return [i.id for i in self.inputs]


def meta_path(output_dir: Path) -> Path:
    return Path(output_dir) / META_NAME


def signed_path(output_dir: Path) -> Path:
    return Path(output_dir) / SIGNED_NAME


def now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def write_meta(output_dir: Path, meta: Meta) -> None:
    assert meta.status in STATUSES, f"产出状态只认 {STATUSES}，得到 {meta.status!r}"
    meta_path(output_dir).write_text(
        yaml.safe_dump(meta.to_dict(), allow_unicode=True, sort_keys=False), encoding="utf-8")


def read_meta(output_dir: Path) -> Meta:
    path = meta_path(output_dir)
    if not path.is_file():
        raise OutputNotFound(f"不是产出目录（没有 {META_NAME}）：{output_dir}")
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"{path} 顶层不是映射")
    inputs = [Input(**i) for i in raw.pop("from", []) or []]
    try:
        return Meta(inputs=inputs, **raw)
    except TypeError as exc:
        raise ValueError(f"{path} 不是一份产出记录：{exc}") from exc


def tree_hash(output_dir: Path) -> str:
    """目录里全部产物文件（相对路径 + 内容）的 sha256；框架自己的两份文件与环境、git 仓不算。"""
    root = Path(output_dir)
    digest = hashlib.sha256()
    for path in sorted(p for p in root.rglob("*") if p.is_file()):
        rel = path.relative_to(root)
        if any(part in HASH_IGNORED for part in rel.parts):
            continue
        digest.update(rel.as_posix().encode("utf-8") + b"\0")
        digest.update(path.read_bytes() + b"\0")
    return digest.hexdigest()


def sign(output_dir: Path, *, by: str, note: str = "") -> dict[str, Any]:
    """人给这次产出签字：记谁、何时、一句话、签的是哪份内容（hash）。"""
    by = by.strip()
    if not by:
        raise SignRefused("签字要署名：--by <谁>")
    meta = read_meta(output_dir)
    if meta.status != "ok":
        raise SignRefused(f"{meta.id} 没成（{meta.status}），没什么可签的")
    digest = tree_hash(output_dir)
    previous = read_signed(output_dir)
    if previous is not None and previous["sha256"] == digest:
        raise SignRefused(
            f"{meta.id} 已经签过了（{previous['by']} {previous['signed_at']}），内容没变")
    record = {"by": by, "signed_at": now(), "sha256": digest, "note": note.strip()}
    signed_path(output_dir).write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n",
                                       encoding="utf-8")
    return record


def read_signed(output_dir: Path) -> dict[str, Any] | None:
    path = signed_path(output_dir)
    if not path.is_file():
        return None
    doc = json.loads(path.read_text(encoding="utf-8"))
    for key in ("by", "signed_at", "sha256"):
        if key not in doc:
            raise ValueError(f"{path} 缺 {key}，不是一份签字记录")
    return doc


def signature_state(output_dir: Path) -> dict[str, Any] | None:
    """签字现在有没有效：签过之后目录又改了，签字就 stale——页面要亮出来，不让旧签名盖住新内容。"""
    record = read_signed(output_dir)
    if record is None:
        return None
    return {**record, "stale": record["sha256"] != tree_hash(output_dir)}
