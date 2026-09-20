"""拼进 prompt 的 skill 清单：名字 + 一句话，agent 匹配到再 `show` 读全文（渐进披露）。

形状照 agentskills.io 的接入指南：一个 `<available_skills>` 块，一个 skill 一行。协调层的
system prompt（chat/guide.py）与执行层的 prompt（executor/prompting.py）用的是同一个函数，
两边只差喂进来的清单（通用 / 通用 + 领域）。没有 skill 就返回空串，不输出空块。
"""

from __future__ import annotations

from xml.sax.saxutils import escape

from framework.skills.library import Skill

HEADING = "## 工具包"
HOW_TO = ("上面是你随时能用的 skill，一个一句话说什么时候用。用到哪个就先 "
          "`ai4sci skill show <name>` 读它的全文（怎么运行、留下什么文件、常见失败），"
          "照它写的命令 `ai4sci skill run <name> …` 跑；`ai4sci skill list` 看清单。")


def catalog_text(skills: list[Skill]) -> str:
    """`## 工具包` + `<available_skills>` 块 + 一句怎么用；清单为空返回空串。"""
    if not skills:
        return ""
    lines = ["<available_skills>"]
    for skill in skills:
        lines.append(f"  <skill><name>{escape(skill.name)}</name>"
                     f"<description>{escape(skill.description)}</description></skill>")
    lines.append("</available_skills>")
    return f"{HEADING}\n\n" + "\n".join(lines) + "\n\n" + HOW_TO + "\n"
