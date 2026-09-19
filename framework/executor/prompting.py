"""给执行层的那段提示：模板 + 占位符。

模板用 `string.Template`：占位符缺一个就抛 KeyError，不会静默留下一个 `$xxx` 在提示里。
模板路径由调用方传进来，本模块不持有它：模板是**能力**的资产（实验内环的模板在
`capabilities/auto_research/prompt.md`），组装是执行层这一层的活。写死一个路径就等于把
executor 焊在某个能力上，别的能力再想用同一套组装就得复制一份。
"""

from __future__ import annotations

from pathlib import Path
from string import Template


def build_prompt(template_path: Path, values: dict[str, object], domain_extra: str = "") -> str:
    """套模板；领域包的追加段存在才追加，缺了不追加也不回退到别的模板。"""
    text = Template(Path(template_path).read_text(encoding="utf-8")).substitute(values)
    if domain_extra.strip():
        text += "\n\n## 领域约定\n\n" + domain_extra.strip() + "\n"
    return text
