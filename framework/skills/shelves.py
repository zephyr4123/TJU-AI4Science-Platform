"""skill 的分类表：架（七个研究阶段加「通用」）→ tag，全平台只此一处（外层 #205）。

三处库同一种摆法：一个 skill 放在 `<库>/<架>/<tag>/<name>/`（`library.py`）。架回答「主要在哪个
研究阶段用」，「通用」是哪个阶段都用的（下载、读 PDF、画图）；tag 回答「干哪一行」。编辑台的能力
镜头一架一行、一个 tag 一组，照这张表的顺序画；`make skills` 拦下不在表里的目录。新收一个 skill
先在表里找它的 tag，没有合适的再加一行：slug 英文（目录名），名字是页面上的词、不超过八个字的名词。

步骤（`framework/capabilities/`）不进这张表：它属于哪个阶段写在描述符里，一共几个，用不着再分。
"""

from __future__ import annotations

from dataclasses import dataclass

from framework.contracts.stages import STAGE_SLUGS, name_of


@dataclass(frozen=True)
class Tag:
    slug: str
    name: str


GENERAL = "general"
GENERAL_NAME = "通用"
SHELVES: tuple[str, ...] = (*STAGE_SLUGS, GENERAL)
TAGS: dict[str, tuple[Tag, ...]] = {
    "literature": (Tag("search", "检索"), Tag("reading", "精读")),
    "hypothesis": (Tag("ideation", "构思"), Tag("reasoning", "论证")),
    "design": (Tag("planning", "方案"), Tag("benchmarks", "模型评测")),
    # 先各学科的工具库（研究者带着学科来找），再机器学习与大模型那一串
    "experiment": (
        Tag("biology", "生物"), Tag("chemistry", "化学与药物"), Tag("medicine", "医学与神经"),
        Tag("physics", "物理与材料"), Tag("quantum", "量子"), Tag("earth", "天文与地理"),
        Tag("computing", "科学计算"), Tag("data", "数据处理"), Tag("lab", "实验室"),
        Tag("ml", "机器学习"), Tag("training", "模型训练"), Tag("finetuning", "微调与对齐"),
        Tag("inference", "压缩与推理"), Tag("multimodal", "多模态"),
        Tag("rl", "强化学习与机器人"), Tag("interpretability", "可解释性"),
        Tag("retrieval", "向量检索"), Tag("tracking", "实验追踪"),
    ),
    "analysis": (Tag("statistics", "统计"), Tag("exploration", "探索与解释"),
                 Tag("biomedical", "生物医学"), Tag("social", "社会科学")),
    "writing": (Tag("manuscript", "论文"), Tag("review", "审稿与回复"),
                Tag("proposal", "申请与专利"), Tag("presentation", "汇报"),
                Tag("clinical", "临床文书")),
    "verification": (Tag("rigor", "审查"), Tag("references", "引用核对")),
    GENERAL: (Tag("materials", "资料"), Tag("plotting", "绘图")),
}
_TAG_NAMES = {(shelf, tag.slug): tag.name for shelf, tags in TAGS.items() for tag in tags}


def shelf_name(shelf: str) -> str:
    """架 → 页面上的词：阶段名，或「通用」。"""
    return GENERAL_NAME if shelf == GENERAL else name_of(shelf)


def tag_name(shelf: str, tag: str) -> str:
    """(架, tag) → 页面上的词；不在表里就炸（目录不在表里的 skill 扫库时就隔离了，到不了这里）。"""
    assert (shelf, tag) in _TAG_NAMES, f"分类表里没有 {shelf}/{tag}"
    return _TAG_NAMES[(shelf, tag)]


def place(shelf: str, tag: str) -> str:
    """给人看的位置：实验·生物、通用·资料。"""
    return f"{shelf_name(shelf)}·{tag_name(shelf, tag)}"


def shelf_of(text: str) -> str:
    """阶段名、slug 或「通用」→ 架；认不出就炸（调用方先给用户说清有哪些）。"""
    if text in SHELVES:
        return text
    for shelf in SHELVES:
        if shelf_name(shelf) == text:
            return shelf
    raise ValueError(f"不是阶段：{text!r}（七个阶段的名字，或「{GENERAL_NAME}」）")
