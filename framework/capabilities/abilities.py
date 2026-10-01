"""能力库：一个词「能力」，两个 tag（主人 2026-09-22 定，改 P-22）。住在 capabilities 这一层：
它要同时认识描述符（本层）与 skill（下层），framework 顶层模块不许 import 分层包
（tests/test_layering.py）。

- **步骤**：`framework/capabilities/` 里的描述符。走到流程的那一格，框架起执行层、开带编号的产出、
  能签（`ai4sci cap <name>`）。
- **skill**：三处库（平台自带 `skills/`、收录 `skills-curated/<架>/`、领域包
  `domains/<包>/skills/`）里的 SKILL.md。教 agent 怎么做一件事的指南 + 脚本，agent 随手调、不开编号
  产出（`ai4sci skill run <name>`），任何阶段都能挂；在项目里只有装载了的才能用（P-26，
  `workspace/loadout.py`）。

两种都能挂到流程的格子上、都进编辑台的库、都出现在看板的卡上；tag 只说明它是哪一类，不改它怎么跑。
库里两种不许重名——流程文件里挂的只是一个名字，靠名字分辨是哪种。
"""

from __future__ import annotations

from typing import Any

from framework import skills
from framework.capabilities import discover
from framework.contracts.capability import Capability
from framework.contracts.workflows import KIND_SKILL, KIND_STEP
from framework.skills import library
from framework.skills.library import Skill

__all__ = ["KIND_SKILL", "KIND_STEP", "AbilityNameClash", "check_disjoint", "skill_detail",
           "skill_entries", "skill_entry", "skill_names", "steps"]


class AbilityNameClash(ValueError):
    """一个名字同时是步骤和 skill：流程文件里分辨不出，两边改一个。"""


def steps() -> dict[str, Capability]:
    return {name: module.DESCRIPTOR for name, module in discover().items()}


def skill_names() -> frozenset[str]:
    """三处库里所有 skill 的名字（不合格的也算：流程里挂的名字是不是 skill 看目录在不在）；
    流程校验认这一份。"""
    return library.names()


def check_disjoint(step_names: set[str] | frozenset[str], names: frozenset[str]) -> None:
    clash = sorted(set(step_names) & names)
    if clash:
        raise AbilityNameClash(f"能力名同时是步骤和 skill：{clash}；两边改一个")


def skill_entry(skill: Skill) -> dict[str, Any]:
    """清单里的一行（`GET /skills`、`show caps --json`）：与步骤描述符同一层的字段（name / title /
    brief / kind），另带出处（库、收录库的架、给人看的一句「收录·文献」）与脚本名。不带正文：库有
    几百个，整库带正文一次 2.5 MB；正文按名字单取（`skill_detail`），agent 在项目里读要过装载
    （`ai4sci skill show`）。title 就是名字：skill 的名字是 agent 叫它的词，页面照显示。"""
    return {"name": skill.name, "kind": KIND_SKILL, "title": skill.name, "brief": skill.description,
            "library": skill.library, "shelf": skill.shelf, "where": skill.where,
            "scripts": [script.name for script in skill.scripts]}


def skill_entries() -> list[dict[str, Any]]:
    return [skill_entry(skill) for skill in skills.everything().skills]


def skill_detail(name: str) -> dict[str, Any]:
    """一个 skill 的清单那一行加 SKILL.md 正文（`GET /skills/<name>`，编辑台翻库用）。
    没有这个 skill 是 SkillNotFound，不合格是 SkillInvalid。"""
    skill = skills.find(name)
    return {**skill_entry(skill), "body": skill.body}
