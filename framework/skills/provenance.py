"""收录库的台账 `skills-curated/provenance.yaml`：每个收录的 skill 从哪来、改了什么（纲领 P-22）。

台账是收录这件事的唯一记录：目录里的每个 skill 在 `skills` 里有且只有一行，架对得上；上游写明仓库、
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
        shelf: literature                # 架：七个阶段的 slug 或 general
        upstream: k-dense
        path: skills/paper-lookup        # 上游仓里的原路径
        changes: [命令改成 ai4sci skill run, …]
    rejected:
      - upstream: k-dense
        path: skills/research-lookup
        reason: 缺省路径要 Parallel 账号（P-27）

许可证只收能随开源平台再分发、不加使用限制的那几种（`LICENSES`）。对账只读台账与目录，不碰上游仓：
上游的克隆不在仓里，换机器照样能查。
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

from framework import paths
from framework.skills.library import CURATED_SHELVES, SKILL_FILE

LEDGER_FILE = "provenance.yaml"
# 能随开源平台再分发、不附加使用限制的许可证（SPDX 名）。NC、专有、没有许可证的一律不收
LICENSES = ("MIT", "Apache-2.0", "BSD-2-Clause", "BSD-3-Clause", "ISC")


class LedgerInvalid(ValueError):
    """台账形状不对、或与目录对不上：问题一行一条。"""


@dataclass(frozen=True)
class Entry:
    name: str
    shelf: str
    upstream: str
    path: str
    changes: tuple[str, ...]


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
        if not isinstance(row, dict) or not all(row.get(k) for k in
                                                 ("name", "shelf", "upstream", "path")):
            problems.append(f"skills 第 {i + 1} 行要有 name / shelf / upstream / path")
            continue
        if row["upstream"] not in upstreams:
            problems.append(f"{row['name']}: upstream {row['upstream']!r} 不在 upstreams 里")
        if row["shelf"] not in CURATED_SHELVES:
            problems.append(f"{row['name']}: 架 {row['shelf']!r} 不是 {CURATED_SHELVES} 之一")
        changes = row.get("changes") or []
        entries.append(Entry(str(row["name"]), str(row["shelf"]), str(row["upstream"]),
                             str(row["path"]), tuple(str(c) for c in changes)))
    for i, row in enumerate(raw.get("rejected") or []):
        if not isinstance(row, dict) or not all(row.get(k) for k in ("upstream", "path", "reason")):
            problems.append(f"rejected 第 {i + 1} 行要有 upstream / path / reason")
    listed: dict[str, Entry] = {}
    for entry in entries:
        if entry.name in listed:
            problems.append(f"{entry.name}: 台账里出现了两次")
        listed[entry.name] = entry
    on_disk = {d.name: shelf for shelf in CURATED_SHELVES if (root / shelf).is_dir()
               for d in (root / shelf).iterdir() if (d / SKILL_FILE).is_file()}
    for name in sorted(set(on_disk) - set(listed)):
        problems.append(f"{on_disk[name]}/{name}: 在收录库里但台账里没有")
    for name in sorted(set(listed) - set(on_disk)):
        problems.append(f"{name}: 台账里有但收录库里没有")
    for name in sorted(set(listed) & set(on_disk)):
        if listed[name].shelf != on_disk[name]:
            problems.append(f"{name}: 台账写架 {listed[name].shelf}，目录在 {on_disk[name]}")
    if problems:
        raise LedgerInvalid("\n".join(f"{path}: {p}" for p in problems))
    return entries
