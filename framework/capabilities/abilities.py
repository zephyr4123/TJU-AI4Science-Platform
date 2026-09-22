"""能力库：一个词「能力」，两个 tag（主人 2026-09-22 定，改 P-22）。住在 capabilities 这一层：
它要同时认识描述符（本层）与 skill（下层），framework 顶层模块不许 import 分层包
（tests/test_layering.py）。

- **步骤**：`framework/capabilities/` 里的描述符。走到流程的那一格，框架起执行层、开带编号的产出、
  能签（`ai4sci cap <name>`）。
- **skill**：`skills/` 与领域包里的 SKILL.md。教 agent 怎么做一件事的指南 + 脚本，agent 随手调、不开
  编号产出（`ai4sci skill run <name>`），任何阶段都能用。

两种都能挂到流程的格子上、都进编辑台的库、都出现在看板的卡上；tag 只说明它是哪一类，不改它怎么跑。
库里两种不许重名——流程文件里挂的只是一个名字，靠名字分辨是哪种。
"""

from __future__ import annotations

from typing import Any

from framework import skills
from framework.capabilities import discover
from framework.contracts.capability import Capability
from framework.contracts.workflows import KIND_SKILL, KIND_STEP
from framework.skills.library import Skill

__all__ = ["KIND_SKILL", "KIND_STEP", "AbilityNameClash", "check_disjoint", "skill_entries",
           "skill_entry", "skill_names", "steps"]


class AbilityNameClash(ValueError):
    """一个名字同时是步骤和 skill：流程文件里分辨不出，两边改一个。"""


def steps() -> dict[str, Capability]:
    return {name: module.DESCRIPTOR for name, module in discover().items()}


def skill_names() -> frozenset[str]:
    """两处库里所有 skill 的名字（通用 + 每个领域包的）；流程校验认这一份。"""
    return frozenset(skill.name for skill in skills.all_skills())


def check_disjoint(step_names: set[str] | frozenset[str], names: frozenset[str]) -> None:
    clash = sorted(set(step_names) & names)
    if clash:
        raise AbilityNameClash(f"能力名同时是步骤和 skill：{clash}；两边改一个")


def skill_entry(skill: Skill) -> dict[str, Any]:
    """给 `GET /skills` 与页面：与步骤描述符同一层的字段（name / title / brief / kind），
    另带 SKILL.md 正文与脚本名。title 就是它的名字：skill 的名字是 agent 叫它的词，页面照显示。"""
    return {"name": skill.name, "kind": KIND_SKILL, "title": skill.name, "brief": skill.description,
            "library": skill.library, "body": skill.body,
            "scripts": [script.name for script in skill.scripts]}


def skill_entries() -> list[dict[str, Any]]:
    return [skill_entry(skill) for skill in skills.all_skills()]
