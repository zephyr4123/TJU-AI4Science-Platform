"""收录库的台账 `skills-curated/provenance.yaml`：每个收录的 skill 从哪来、改了什么（纲领 P-22）。

台账是收录这件事的唯一记录：目录里的每个 skill 在 `skills` 里有且只有一行；上游写明仓库、
提交与许可证，许可证原文拷在 `licenses/` 里（MIT、Apache 要求随代码带原文）；不收的写进 `rejected`
带原因，下次同步上游时不用再判一遍。形状：

    upstreams:
      k-dense:
        title: K-Dense Scientific Agent Skills
        url: https://github.com/K-Dense-AI/scientific-agent-skills
        commit: 49c6e97…                 # 收录时钉的提交
        license: MIT
        license_file: licenses/k-dense.txt
    skills:
      - name: paper-lookup               # 平台里的名字（= 目录名）
        upstream: k-dense
        path: skills/paper-lookup        # 上游仓里的原路径
        changes: [命令改成 ai4sci skill run, …]
        license_note: …                  # 只在 skill 自己写的许可证认不出时要（见下）
    rejected:
      - upstream: k-dense
        path: skills/research-lookup
        reason: 缺省路径要 Parallel 账号（P-27）

许可证只收能随开源平台再分发、不加使用限制的那几种（`LICENSES`）。上游仓的许可证不够：有的包里
每个 skill 在 frontmatter 的 `license` 里另写自己的（K-Dense 的 README 明说以它为准），所以逐个看——
认得出是可收的（`MIT license`、`3-clause BSD` 这类写法归一成 SPDX 名）或没写（随上游仓）就过；
认不出的（链接、库自己的协议名、一段话）台账那行要写 `license_note`，说清查过、为什么能收。

放在哪一架哪个 tag 不记在这里：目录就是它的位置（`<架>/<tag>/<name>/`，分类表 `shelves.py`），
一个事实只放一处。对账只读台账与目录，不碰上游仓：上游的克隆不在仓里，换机器照样能查。
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import yaml

from framework import paths
from framework.skills.library import (
    CURATED,
    SKILL_FILE,
    Root,
    SkillInvalid,
    cells,
    split_frontmatter,
)

LEDGER_FILE = "provenance.yaml"
# 能随开源平台再分发、不附加使用限制的许可证（SPDX 名）。NC、专有、没有许可证的一律不收；
# CC-BY 系列也不收（主人 2026-10-01 定，外层 #198）
LICENSES = ("MIT", "Apache-2.0", "BSD-2-Clause", "BSD-3-Clause", "ISC")
# skill frontmatter 里常见的写法 → SPDX 名（去掉结尾的 license、小写之后比）
ALIASES = {
    **{name.lower(): name for name in LICENSES},
    "apache license, version 2.0": "Apache-2.0",
    "3-clause bsd": "BSD-3-Clause", "3 clause bsd": "BSD-3-Clause",
}


class LedgerInvalid(ValueError):
    """台账形状不对、或与目录对不上：问题一行一条。"""


@dataclass(frozen=True)
class Entry:
    name: str
    upstream: str
    path: str
    changes: tuple[str, ...]
    license_note: str = ""


def spdx(text: str) -> str | None:
    """skill 自己写的许可证认得出是哪个可收的就给 SPDX 名，认不出是 None。"""
    key = re.sub(r"\s+licen[cs]e$", "", text.strip().lower())
    return ALIASES.get(key)


def ledger_path(root: Path | None = None) -> Path:
    return (paths.curated_skills_root() if root is None else Path(root)) / LEDGER_FILE


def check(root: Path | None = None) -> list[Entry]:
    """读台账、与收录库的目录对账；对不上就把问题一次列全抛出来。"""
    root = paths.curated_skills_root() if root is None else Path(root)
    path = ledger_path(root)
    if not path.is_file():
        raise LedgerInvalid(f"收录库没有台账 {path}")
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        raise LedgerInvalid(f"{path}: 不是合法 YAML：{exc}") from exc
    problems: list[str] = []
    upstreams = raw.get("upstreams") or {}
    for key, up in upstreams.items():
        for field in ("title", "url", "commit", "license", "license_file"):
            if not (isinstance(up, dict) and up.get(field)):
                problems.append(f"upstreams.{key} 缺 {field}")
        if isinstance(up, dict) and up.get("license") not in LICENSES:
            problems.append(f"upstreams.{key} 的许可证 {up.get('license')!r} 不在可收的里"
                            f"（{', '.join(LICENSES)}）")
        if isinstance(up, dict) and up.get("license_file") \
                and not (root / str(up["license_file"])).is_file():
            problems.append(f"upstreams.{key} 的许可证原文 {up['license_file']} 不在")
    entries: list[Entry] = []
    for i, row in enumerate(raw.get("skills") or []):
        if not isinstance(row, dict) or not all(row.get(k) for k in ("name", "upstream", "path")):
            problems.append(f"skills 第 {i + 1} 行要有 name / upstream / path")
            continue
        if row["upstream"] not in upstreams:
            problems.append(f"{row['name']}: upstream {row['upstream']!r} 不在 upstreams 里")
        changes = row.get("changes") or []
        entries.append(Entry(str(row["name"]), str(row["upstream"]),
                             str(row["path"]), tuple(str(c) for c in changes),
                             str(row.get("license_note") or "")))
    rejected = raw.get("rejected") or []
    for i, row in enumerate(rejected):
        if not isinstance(row, dict) or not all(row.get(k) for k in ("upstream", "path", "reason")):
            problems.append(f"rejected 第 {i + 1} 行要有 upstream / path / reason")
    used = {str(row.get("upstream")) for row in [*(raw.get("skills") or []), *rejected]
            if isinstance(row, dict)}
    for key in sorted(set(upstreams) - used):
        problems.append(f"upstreams.{key} 声明了却没有一行用到：来源记错了，或删掉这个上游")
    listed: dict[str, Entry] = {}
    for entry in entries:
        if entry.name in listed:
            problems.append(f"{entry.name}: 台账里出现了两次")
        listed[entry.name] = entry
    on_disk = {d.name: d for *_, cell in cells([Root(CURATED, root)])
               for d in cell.iterdir() if (d / SKILL_FILE).is_file()}
    for name in sorted(set(on_disk) - set(listed)):
        problems.append(f"{on_disk[name].relative_to(root)}: 在收录库里但台账里没有")
    for name in sorted(set(listed) - set(on_disk)):
        problems.append(f"{name}: 台账里有但收录库里没有")
    for name in sorted(set(listed) & set(on_disk)):
        own = _own_license(on_disk[name])
        if own and spdx(own) is None and not listed[name].license_note:
            problems.append(f"{name}: skill 自己写的许可证 {own[:80]!r} 认不出是可收的："
                            "查清后在台账那行写 license_note，说明为什么能收")
    if problems:
        raise LedgerInvalid("\n".join(f"{path}: {p}" for p in problems))
    return entries


def _own_license(directory: Path) -> str:
    """skill frontmatter 里的 license；没写、读不出来都是空（读不出来的门禁另报）。"""
    try:
        front, _ = split_frontmatter((directory / SKILL_FILE).read_text(encoding="utf-8"))
    except SkillInvalid:
        return ""
    value = front.get("license")
    return value.strip() if isinstance(value, str) else ""
