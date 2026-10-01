"""skill：给 agent 用的工具包（纲领 P-22）。一个目录一个 skill，格式照 agentskills.io 开放规范：
`<name>/SKILL.md`（frontmatter + 正文）+ `scripts/`（PEP 723 自带依赖）+ `references/` + `assets/`。

框架自己注入、自己起脚本，不靠任何 agent 的原生机制：

- `library`：扫三处库（平台自带 `skills/`、收录 `skills-curated/<架>/`、领域包
  `domains/<包>/skills/`），宽进地校验、不合格的隔离出去、按名字找。
- `provenance`：收录库的台账 `provenance.yaml`（来源、提交、许可证、改了什么）与目录对账。
- `catalog`：把一个项目装载的那套（`workspace/loadout.py`，纲领 P-26）拼成 `<available_skills>`
  进 prompt。
- `run`：`uv run --locked` 起脚本，参数原样递过去，stdout 与退出码原样透出。

在 `contracts` 之上、`workspace` 之下的一层：它只认 SKILL.md 与脚本，不认工作区与项目——一个项目
装哪些是工作区层的事。执行层会话要能跑 `ai4sci skill …`，放行的命令前缀只有这一组
（`EXECUTOR_BASH_RULES`）——`ai4sci cap` 那些是协调层的，执行层不该碰。
"""

from __future__ import annotations

from framework.skills.catalog import catalog_text
from framework.skills.library import SkillInvalid, SkillNotFound, everything, find, resident

# 包外经 `skills.X` 用到的只有这几个；别的从 `framework.skills.library` / `run` 直接取
__all__ = ["SkillInvalid", "SkillNotFound", "everything", "find", "resident", "catalog_text",
           "EXECUTOR_BASH_RULES"]

# 执行层会话的 Bash 白名单：只有 skill 的三个子命令。与协调层的 `Bash(ai4sci *)`（chat/guide.py）
# 不同：执行层不许调能力、不许签字，它面前只有工具包
EXECUTOR_BASH_RULES = ("ai4sci skill",)  # 命令前缀，与 CLI 无关；适配器翻成自己的白名单写法
