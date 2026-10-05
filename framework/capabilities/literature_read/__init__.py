"""文献精读：文献阶段的第二个步骤——检索下来的论文，有原文的逐篇读，每篇一份带原句的笔记
（外层 #233）。

一个能力一个子包，互不 import。对外只露描述符与统一入口；主流程在 `read.py`，上游清单怎么读、
自己的清单怎么写在 `sources.py`，原句核对在 `quotes.py`。主人 2026-10-05 定：精读与检索分开做，
边界清楚，各自单独优化、测试。
"""

from __future__ import annotations

from pathlib import Path

from framework.capabilities.literature_read.read import read_all
from framework.contracts.capability import Capability, CapabilityFailed, Inputs, Param, Ports

__all__ = ["DESCRIPTOR", "run"]

DESCRIPTOR = Capability(
    name="literature-read",
    stage="文献",
    title="文献精读",
    brief="逐篇读原文，每篇写一份带原句的笔记",
    does=(
        "读上游文献产出的 sources.md，认出每篇论文与它的原文。有原文的一篇起一个执行层会话"
        "（同时 4 个），把原文放进提示（超过 10 万字符的只放前 10 万字符并注明），按已确认的需求"
        "写一份笔记：一句话、问题、方法、数据与实验、主要结果（带数字）、局限、和本需求的关系；"
        "主要结果每条抄一句原文的原句。框架逐条在原文里核这些原句（大小写、空白、排版记号归一后比），"
        "把读了哪些、每篇一句话、笔记在哪、原句对上几条写进 sources.md。"
    ),
    does_not=(
        "不检索、不下载原文，那是文献检索的事；不写综述、不比较论文之间的结论，综合由研究助理读笔记"
        "来做。没有原文的论文不读，列出来请研究者自己下。执行层只许写自己那篇的笔记。"
    ),
    brings="已确认的需求 requirement.md；文献阶段的一次产出：读它的 sources.md 与里面写到的原文。",
    leaves=(
        "sources.md（文献阶段的主文件：读了哪些、每篇一句话、笔记在哪、原句对上几条；"
        "没读成的、没有原文的列在文末，检索过程指回上游）；notes/ 下每篇一份笔记；"
        "progress.jsonl（边读边记每篇读到哪，页面画精读进度）；执行层会话的日志在 executor/。"
    ),
    stops=(
        "有原文的读完就停。某篇会话超时、没写笔记、写了笔记之外的文件，只记这篇没读成，别的照收；"
        "一篇都没读成、上游没有 sources.md 或里面没有一篇有原文，判失败。"
    ),
    params=(
        Param("max_papers", "int", 0, "最多读几篇，按上游清单的顺序取有原文的；0 是全读",
              "最多读几篇"),
    ),
    needs_executor=True,
)


def run(output_dir: Path, inputs: Inputs, ports: Ports, *, max_papers: int = 0) -> str:
    if ports.runner is None:
        raise CapabilityFailed("文献精读要执行层：读原文、写笔记靠它")
    return read_all(output_dir, inputs, ports.runner, max_papers=max_papers)
