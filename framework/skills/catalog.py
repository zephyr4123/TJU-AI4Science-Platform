"""拼进 prompt 的 skill 清单：名字 + 一句话，agent 匹配到再 `show` 读全文（渐进披露）。

形状照 agentskills.io 的接入指南：一个 `<available_skills>` 块，一个 skill 一行。研究助理的
system prompt（chat/guide.py）与执行层的 prompt（executor/prompting.py）用的是同一个函数，喂进来的
是同一套：本项目装载的（纲领 P-26，`workspace/loadout.py`）。挂在流程上却不可用的另列一块带原因，
不静默丢；两样都没有就返回空串，不输出空块。
"""

from __future__ import annotations

from collections.abc import Sequence
from xml.sax.saxutils import escape

from framework.skills.library import Skill

HEADING = "## 工具包"
HOW_TO = ("上面是这个项目装载的 skill，一个一句话说什么时候用。用到哪个就先 "
          "`ai4sci skill show <name>` 读它的全文（怎么运行、留下什么文件、常见失败），目录里的其它"
          "文件（参考、模板）用 `ai4sci skill show <name> <文件>` 读，照它写的命令 "
          "`ai4sci skill run <name> …` 跑；`ai4sci skill list` 看清单。清单之外的用不了。"
          "skill 正文里让你 `pip install`、直接运行 `python` 或 `curl` 的地方在平台里跑不了，"
          "照平台的做法来：脚本只经 `ai4sci skill run` 起，查资料用你自带的联网工具。")


def catalog_text(skills: Sequence[Skill], unavailable: Sequence[tuple[str, str]] = ()) -> str:
    """`## 工具包` + `<available_skills>` 块 + 不可用的几行 + 一句怎么用；都没有返回空串。"""
    if not skills and not unavailable:
        return ""
    lines = ["<available_skills>"]
    for skill in skills:
        lines.append(f"  <skill><name>{escape(skill.name)}</name>"
                     f"<description>{escape(skill.description)}</description></skill>")
    lines.append("</available_skills>")
    if unavailable:
        lines.append("")
        lines.append("流程上挂着、但用不了的（跟研究者说一声）：")
        lines += [f"- {name}：{reason}" for name, reason in unavailable]
    return f"{HEADING}\n\n" + "\n".join(lines) + "\n\n" + HOW_TO + "\n"
