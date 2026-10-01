"""`make skills` 的入口（`python -m framework.skills`）：三处库的门禁，平台自带的预热。

顺序：扫三处库，一个不合格都不行（出厂的我们自己负责，宽进只给研究者自己放进来的）→ 零 key
（纲领 P-27）：哪个文件提到第三方凭据就不过 → 收录库的台账与目录对账（`provenance.py`）→ 平台自带的
每个脚本 `uv lock --check` + `uv sync`，声明的系统命令 `which` 一遍。收录的与领域包的不预热：几百个
skill 一个项目只用到几个，第一次 `ai4sci skill run` 时按锁建环境（`run.py`）。任何一步不过就退 1、
问题一行一条；过了每处库打一行计数。摆错地方的目录（不在分类表的
`<架>/<tag>/` 下面）在扫库时就隔离成不合格的了，第一步拦下。
"""

from __future__ import annotations

import shutil
import sys
from collections import Counter

from framework.skills import everything, run
from framework.skills.library import RESIDENT, SkillInvalid, key_mentions, roots
from framework.skills.provenance import LedgerInvalid, check


def main() -> int:
    found = everything()
    problems = [f"{bad.dir}: {p}" for bad in found.invalid for p in bad.problems]
    for skill in found.skills:
        problems += [f"{skill.dir}/{hit}（零 key，纲领 P-27）" for hit in key_mentions(skill)]
        if skill.library == RESIDENT:
            problems += [f"{skill.dir}: {note}（平台自带的要干净）" for note in skill.notes]
    try:
        check()
    except LedgerInvalid as exc:
        problems.append(str(exc))
    for skill in found.skills:
        if skill.library != RESIDENT:
            continue
        for script in skill.scripts:
            try:
                run.warm_script(script)
            except (SkillInvalid, run.UvMissing) as exc:
                problems.append(str(exc))
        for tool in skill.system_tools:
            if shutil.which(tool) is None:
                problems.append(f"{skill.dir}: 系统命令 {tool!r} 不在 PATH 上"
                                f"（SKILL.md 的 compatibility 写了怎么装）")
    if problems:
        print("\n".join(problems), file=sys.stderr)
        return 1
    counts = Counter(skill.library for skill in found.skills)
    scripts = Counter(skill.library for skill in found.skills for _ in skill.scripts)
    notes = Counter(skill.library for skill in found.skills for _ in skill.notes)
    for name in (root.library for root in roots()):
        if counts[name]:
            print(f"{name}\t{counts[name]} 个 skill\t{scripts[name]} 个脚本\t{notes[name]} 条提醒")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
