"""文献检索：文献阶段的第一个步骤——按需求找论文、顺着引用扩几跳、筛过的下原文，
写 sources.md（外层 #212）。

一个能力一个子包，互不 import。对外只露描述符与统一入口；主流程在 `loop.py`，OpenAlex 客户端在
`openalex.py`，与执行层交换的两份文件在 `exchange.py`，候选池在 `pool.py`，原文在 `fulltext.py`，
清单在 `report.py`。
"""

from __future__ import annotations

from pathlib import Path

from framework.capabilities.literature_search.loop import Limits, search
from framework.contracts.capability import Capability, CapabilityFailed, Inputs, Param, Ports

__all__ = ["DESCRIPTOR", "run"]

DESCRIPTOR = Capability(
    name="literature-search",
    stage="文献",
    title="文献检索",
    brief="按需求查论文，顺着引用扩几跳，筛过的下原文",
    does=(
        "先起一个执行层会话：按需求写检索词与纳入标准，用它自带的联网搜索找种子论文"
        "（DOI 或 arXiv 链接），写进 seeds.md。框架把检索词逐条过 Crossref、arXiv、"
        "Europe PMC，前 5 条也过 OpenAlex，每家每条取前 10 篇；命中的编号与种子一起回 OpenAlex "
        "取元数据，按被几路查到、题目与摘要命中检索词的程度排序，"
        "取每跳筛选数的两倍加种子作第 0 跳。"
        "每一跳起一个执行层会话，只给它候选的题目、年份、出处、被引数、摘要与来源，"
        "让它按纳入标准逐篇写收或不收和一句理由。之后只从新收录的论文往外扩："
        "向后取它的参考文献，向前取引用它们的（合起来按被引数前 400 篇）；"
        "新线索按关联到几篇已收录的、乘上题目与摘要命中检索词的程度排序，同分看被引数，"
        "前若干篇交下一跳筛。"
        "给了起始年份就只查、只收那一年及以后发表的：四家检索与「谁引用了它」都按年份查，"
        "更早的种子与参考文献不交给模型筛。"
        "最后把收录的、有开放获取 PDF 的交给 pdf skill 下载并解析，写 sources.md。"
    ),
    does_not=(
        "不写综述、不核对引用、不判断论文的结论对不对。四家学术接口都不要 key 也能跑，"
        "元数据与引用关系统一取 OpenAlex（设置里填了它的 key 额度大十倍）；"
        "中文库（知网、万方）与付费全文拿不到，"
        "没拿到原文的列在 sources.md 里请研究者自己下。"
        "执行层只许写 seeds.md 与每一跳的结论文件，写了别的判失败。"
    ),
    brings="已确认的需求 requirement.md：检索词与纳入标准都从它来。不要上游产出。",
    leaves=(
        "sources.md（文献阶段的主文件：检索词、纳入标准，收录的每篇论文的题目、作者、链接、"
        "怎么找到的、为什么收、原文在不在）；candidates.jsonl（看过的每篇与筛选结论）；"
        "seeds.md；rounds/ 下每一跳的候选与结论；papers/ 下解析好的原文；"
        "progress.jsonl（边跑边记走到哪一步，页面画检索进度）；执行层会话的日志在 executor/。"
    ),
    stops=(
        "第 0 跳一篇都没收、某一跳新收录的少于停止下限、到了最多跳数、没有可筛的候选，"
        "先到哪个停在哪个，写出 sources.md 后退出；Crossref、arXiv、Europe PMC 某条没查成"
        "只记下、不停。结论文件漏写、抄错号的几篇单独补筛一次。执行层会话超时或没走完、"
        "补筛之后还缺结论、OpenAlex 重试用完仍失败或当天额度用完：判失败，"
        "看过的候选留在 candidates.jsonl。"
    ),
    params=(
        Param("max_hops", "int", 2, "从收录的论文顺着引用往外扩几跳；0 是只看检索词与种子",
              "最多跳数"),
        Param("per_hop", "int", 30, "每一跳交给模型看摘要筛的篇数", "每跳筛选数"),
        Param("min_new", "int", 3, "某一跳新收录的少于这个数就停：再扩也扩不出新东西了",
              "停止下限"),
        Param("since", "int", 0,
              "只查、只收这一年及以后发表的，写四位年份（近三年就写今年减二）；0 是不限",
              "起始年份"),
        Param("abstracts_only", "bool", False,
              "只看摘要筛，收录的不下载原文；缺省是有开放获取的 PDF 就下载并解析", "只看摘要"),
    ),
    needs_executor=True,
)


def run(output_dir: Path, inputs: Inputs, ports: Ports, *, max_hops: int = 2, per_hop: int = 30,
        min_new: int = 3, since: int = 0, abstracts_only: bool = False) -> str:
    if ports.runner is None:
        raise CapabilityFailed("文献检索要执行层：写检索词、找种子、看摘要筛都靠它")
    return search(output_dir, inputs, ports.runner, Limits(max_hops, per_hop, min_new),
                  fulltext=not abstracts_only, since=since)
