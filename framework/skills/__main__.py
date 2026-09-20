"""`make skills` 的入口（`python -m framework.skills`）：承接时把两处库过一遍门禁、预热脚本环境。

顺序：扫库（SKILL.md 合规范、脚本有 PEP 723 头与锁）→ 每个脚本 `uv lock --check` + `uv sync`
（唯一允许联网的一步）→ 每个 skill 声明的系统命令 `which` 一遍。任何一步不过就退 1、问题一行一条；
过了打一行清单。之后 `ai4sci skill run` 全部 `--locked --offline`。
"""

from __future__ import annotations

import shutil
import sys

from framework.skills import all_skills, run
from framework.skills.library import SkillInvalid


def main() -> int:
    try:
        skills = all_skills()
    except SkillInvalid as exc:
        print(str(exc), file=sys.stderr)
        return 1
    problems: list[str] = []
    for skill in skills:
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
    for skill in skills:
        print(f"{skill.name}\t{skill.library}\t{len(skill.scripts)} 个脚本\t{skill.dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
