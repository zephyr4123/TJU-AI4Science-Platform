"""给执行层的那段提示：模板 + 占位符 + 通用段（领域约定、工具包、联网）。

模板用 `string.Template`：占位符缺一个就抛 KeyError，不会静默留下一个 `$xxx` 在提示里。
模板路径由调用方传进来，本模块不持有它：模板是**能力**的资产（实验内环的模板在
`capabilities/auto_research/prompt.md`），组装是执行层这一层的活。写死一个路径就等于把
executor 焊在某个能力上，别的能力再想用同一套组装就得复制一份。

通用段每个执行层会话都带：领域包的追加段（有才追加）、skill 清单（有才追加，纲领 P-22）、
联网规矩（总是带）。
"""

from __future__ import annotations

from pathlib import Path
from string import Template

from framework.skills import Skill, catalog_text

# 主人 2026-09-20：agent 要知道什么时候该联网、并且只用自带的工具——实测过它拿本机 curl 硬凑，效果差
# 真跑时执行层拿 Bash 去 cd、mkdir、awk、串管道，dontAsk 下一条条被拒，每条白耗一轮（外层 #122）
TOOLS_RULE = """## 工具怎么用

- 读文件、找文件、搜内容用 Read / Glob / Grep 工具；不要用 Bash 去 cat、find、awk。
- Bash 只放行 `ai4sci skill …` 一类命令；cd、mkdir、管道、`&&` 串起来的命令都会被拒，
  拒一次白耗一轮。建目录不用 mkdir：Write 会自己建。
- 写完不用自己查行宽、跑 lint：框架会跑 ruff 与校验，问题喂回给你。
"""

WEB_RULE = """## 联网

库的 API、报错的含义、数据格式、论文里的做法拿不准时，用你自带的联网搜索与网页读取工具去查，
不要凭记忆猜版本号与 API。不要在 Bash 里用 curl / wget / pip 之类命令去凑（也没放行）。
查到的东西写进代码注释或收尾自述时带上来源链接，后面的人能回头核。
"""


def build_prompt(template_path: Path, values: dict[str, object], domain_extra: str = "",
                 skills: list[Skill] = ()) -> str:
    """套模板；领域包的追加段存在才追加，缺了不追加也不回退到别的模板；再接工具包与联网两段。"""
    text = Template(Path(template_path).read_text(encoding="utf-8")).substitute(values)
    if domain_extra.strip():
        text += "\n\n## 领域约定\n\n" + domain_extra.strip() + "\n"
    catalog = catalog_text(list(skills))
    if catalog:
        text += "\n\n" + catalog
    return text.rstrip() + "\n\n" + TOOLS_RULE + "\n" + WEB_RULE
