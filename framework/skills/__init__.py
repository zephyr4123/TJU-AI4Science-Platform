"""skill：给 agent 用的工具包（纲领 P-22）。一个目录一个 skill，格式照 agentskills.io 开放规范：
`<name>/SKILL.md`（frontmatter + 正文）+ `scripts/`（PEP 723 自带依赖）+ `references/` + `assets/`。

框架自己注入、自己起脚本，不靠任何 agent 的原生机制：

- `library`：扫两处库（平台通用的 `skills/`、领域包的 `domains/<包>/skills/`），校验、按名字找。
- `catalog`：拼 `<available_skills>` 清单进 prompt——协调层拿通用的，执行层拿通用 + 所选领域包的。
- `run`：`uv run --locked --offline` 起脚本，参数原样递过去，stdout 与退出码原样透出。

在 `contracts` 之上、`workspace` 之下的一层：它只认 SKILL.md 与脚本，不认工作区。
执行层会话要能跑 `ai4sci skill …`，Bash 白名单只放行这一组（`EXECUTOR_BASH_RULES`）——
`ai4sci cap` 那些是协调层的，执行层不该碰。
"""

from __future__ import annotations

from framework.skills.catalog import catalog_text
from framework.skills.library import (
    Skill,
    SkillInvalid,
    SkillNotFound,
    all_skills,
    find,
    for_coordinator,
    for_executor,
    load_skill,
    scan,
)
from framework.skills.run import run_script

__all__ = ["Skill", "SkillInvalid", "SkillNotFound", "all_skills", "find", "for_coordinator",
           "for_executor", "load_skill", "scan", "catalog_text", "run_script",
           "EXECUTOR_BASH_RULES"]

# 执行层会话的 Bash 白名单：只有 skill 的三个子命令。与协调层的 `Bash(ai4sci *)`（chat/guide.py）
# 不同：执行层不许调能力、不许签字，它面前只有工具包
EXECUTOR_BASH_RULES = ("Bash(ai4sci skill *)",)
