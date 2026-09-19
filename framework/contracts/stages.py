"""七个研究阶段：名字（给人看、流程文件里写的）与英文 slug（目录名、id、URL 里用的），一张表只此一处
（纲领 P-18、P-19）。

阶段不定先后、没有代码、没有运行时——顺序归流程与协调层（P-10），这里只回答"这个阶段叫什么、目录叫什么"。
表的顺序是页面与 `show caps` 列清单的顺序，也是磁盘上七个目录的固定序（工作区里只建流程走过的）。
目录一律英文（主人 2026-09-19：中文目录会出很多问题），中文名 ↔ slug 的换算只在这里。
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Stage:
    name: str
    slug: str


STAGES: tuple[Stage, ...] = (
    Stage("文献", "literature"),
    Stage("假设", "hypothesis"),
    Stage("设计", "design"),
    Stage("实验", "experiment"),
    Stage("分析", "analysis"),
    Stage("写作", "writing"),
    Stage("验证", "verification"),
)
STAGE_NAMES: tuple[str, ...] = tuple(s.name for s in STAGES)
STAGE_SLUGS: tuple[str, ...] = tuple(s.slug for s in STAGES)
_BY_NAME = {s.name: s for s in STAGES}
_BY_SLUG = {s.slug: s for s in STAGES}


def slug_of(name: str) -> str:
    """阶段名 → 目录名；不是阶段就炸（调用方先用 STAGE_NAMES 校验用户输入）。"""
    assert name in _BY_NAME, f"不是阶段：{name!r}（阶段：{STAGE_NAMES}）"
    return _BY_NAME[name].slug


def name_of(slug: str) -> str:
    """目录名 → 阶段名。"""
    assert slug in _BY_SLUG, f"不是阶段目录：{slug!r}（阶段目录：{STAGE_SLUGS}）"
    return _BY_SLUG[slug].name


def is_slug(text: str) -> bool:
    return text in _BY_SLUG


def to_dicts() -> list[dict[str, str]]:
    """给 `GET /stages`：页面照单画，不另抄一份表。"""
    return [{"name": s.name, "slug": s.slug} for s in STAGES]
