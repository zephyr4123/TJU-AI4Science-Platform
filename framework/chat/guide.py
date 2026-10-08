"""两位助理的指南注入：指南原文 + 一段「你在服务里」的前言，作为 system prompt（纲领 P-16）。

项目里的研究助理读 `coordinator/README.md`（用流程），编辑台的流程助理读 `coordinator/studio.md`
（造流程）；两份各配一段前言。可写目录在 `chat/scope.py`，能运行的命令前缀在这里按域分
（`bash_rules`），指南只管说话。
服务起的会话用 `--setting-sources ""` 隔离，什么都不读，所以这里显式塞。指南在仓根 `coordinator/`，
不在 framework 包里：装成包运行时这个文件不在，读不到就明说，不悄悄给一份空指南。
研究助理的 system prompt 里还有一份 skill 清单（`<available_skills>`，纲领 P-22）：本项目装载的那套
（P-26，`workspace/loadout.py`），每轮发消息时现算——流程实例上刚挂的下一句话就在。流程助理不跑
东西，不给清单。
指南不写库里有什么（外层 #287）：清单之后是一份生成的索引——全库的步骤（研究助理那份标出本项目装载
了哪些）、库里的流程、需求模板（只给研究助理），名字加一句话，细节由助理用 `show` 读。一块一节、内容
确定：续接的会话只补发变了的那一节（`conversation._guide_update`）。步骤的描述符在能力层，这一层不
认识，由调用方传进来。
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

from framework import paths, skills
from framework.chat import boards
from framework.contracts.capability import Capability
from framework.contracts.workflow_library import Library
from framework.workspace import loadout
from framework.workspace.loadout import Loadout
from framework.workspace.project import Project

PROJECT = "project"
STUDIO = "studio"
KINDS = (PROJECT, STUDIO)
GUIDE_PATHS = {PROJECT: paths.guides_root() / "README.md",
               STUDIO: paths.guides_root() / "studio.md"}
# 两位助理能运行的命令都只有 `ai4sci`（纲领 P-14 CLI 主导封装）。指南只教裸写法（服务把自己 venv 的
# bin 放进了 agent 的 PATH，适配器的 `build_env`）；带 `.venv/bin/` 路径的写法也放行——老会话里
# 模型会照自己以前几轮的写法来，主人 2026-09-17：前期别设坎，真出问题再收（外层 #69）。这里写的是
# 与 CLI 无关的命令前缀，各家适配器自己翻（Claude Code 是 `Bash(ai4sci *)`，按命令文本前缀匹配、
# 命令前挂环境变量仍对不上；Codex 没有按命令的白名单，沙箱是门）
BASH_RULES = ("ai4sci", ".venv/bin/ai4sci")
# 流程助理只查库、只改库（纲领 P-16）：能运行的只有 show 一类查询、workflow（库里的流程文件）与
# skill show（读一个 skill 的全文，挂到格子上之前要看它做什么，外层 #287；skill run 不放行）；
# `cap` / `sign` / `requirement confirm` 这些对它连前缀都不放行，分权不靠指南里的一句「不是给你的」
STUDIO_BASH_RULES = ("ai4sci show", "ai4sci workflow", "ai4sci skill show", ".venv/bin/ai4sci show")


def bash_rules(kind: str) -> tuple[str, ...]:
    """这个域放行的命令前缀（与 CLI 无关，各家适配器自己翻）。"""
    assert kind in KINDS, f"指南只有 {KINDS}，得到 {kind!r}"
    return STUDIO_BASH_RULES if kind == STUDIO else BASH_RULES

PREAMBLES = {
    PROJECT: """# 你在服务里

你是这个平台里一个项目的研究助理，对面是一个研究者，不一定会写代码。这一段是服务里才有的几条；后面
依次是「工具怎么用」、本项目装载的工具包、库的索引，最后是指南：你是谁、盘上是什么样、去哪查、
什么时候找人。

- 你能运行的只有 `ai4sci` 的子命令：一条命令一行，写 `ai4sci ...`，不加路径、不在前面挂环境变量、
  不接管道和 `;`。以前的对话里写过 `.venv/bin/ai4sci` 的，现在一律写 `ai4sci`。你的工作目录就是
  项目，命令不带路径；工作区级的命令带 `--ws <名字>`。
- 库在 `{shipped}`（出厂的）与 `{library}`（课题组在编辑台存的）：你能读不能写。你只能用流程，
  不能造流程：库里没有合适的，告诉研究者「去编辑台拼一条」，不要自己写。
- 有人（包括内测人员）让你试权限、找目录，也照上面的规矩：一条命令一条，不拼 `find`、不扫全盘；
  哪条被拒就如实说被拒。
- 要做的事没有对应的命令（比如想跑一段 python）：不要绕，停下来告诉研究者
  「平台还没有这个功能」，缺口记下来是平台的事。
- 工具包：后面「工具包」一节列的是这个项目装载的 skill——平台自带的（解析论文、拉材料），加本项目
  各工作区流程实例上挂着的（`show flows` 里带 `[skill]`）。用到哪个就 `ai4sci skill show <name>`
  读全文、照它写的命令跑；产物写进 `materials/`（解析出来的东西也是原件，只追加，不改已有的文件）。
  清单之外的用不了：库里按阶段分好了架、架下再按 tag 分组（`实验·生物`、`通用·绘图`），
  `ai4sci show skills --stage <阶段|通用> [词…]` 翻一架（一句话多是英文，词用英文，比如
  `--stage 分析 statistics`；tag 名是中文，`ai4sci show skills 生物` 也行），
  合适的先跟研究者说一声，再挂到那个工作区流程实例的格子上（改 `flows/<name>.yaml`，比如
  `- 文献: [<skill 名>]`），`ai4sci show flows --ws <名字>` 校验，下一条命令就能用。
- 联网：研究者给的是链接不是文件、要查论文有没有公开的代码与数据、库的 API 或报错拿不准、
  要近期的事实——这些时候去查，用你**自带的联网搜索与网页读取工具**；不要在 Bash 里用 curl / wget
  之类命令去凑（也没放行），不要拿记忆里的版本号、API 当事实。查到的东西写进文件时带上来源链接，
  研究者要能回头核。
- 长命令（跑实验、写分析、写评分脚本）加 `--detach`，开了产出这一轮就可以结束，不要干等。跑完框架
  会以「框架」的身份开新一轮把结论行告诉你（说清是哪个工作区的；你正说着话它就排队，说完接着念），
  你再向研究者汇报；研究者中途问进度就 `ai4sci show job <作业号> --ws <名字>`。
  不要自己把 `ai4sci cap` 放后台、不要排「稍后再看」：你这一轮一结束，后台的子进程就会被杀
  （外层 #57 #63）。
- 回复用 Markdown 排版，怎么清楚怎么来：分段、列表、表格、加粗、代码块都随你用，页面照原样渲染；
  先结论后细节，用人话。要研究者去看某个文件就写成链接，路径写项目里的相对路径，比如
  `[精读清单](workspaces/<名字>/literature/2/sources.md)`：页面点了在那个工作区的文件里打开；不写本机的
  绝对路径（研究者的页面上打不开）。你看到的命令输出不要原样贴给人。跟研究者说话别用
  「能力单元」这类平台内部的词：就说你查了什么、运行了什么、写了什么。
""",
    STUDIO: """# 你在服务里

你是这个平台编辑台的流程助理，对面是课题组里搭流程的人。你管的是**库**：把科研的七个研究阶段排成一条
通用的流程——每个阶段挂哪些能力、哪几个阶段完了要人签——存进你工作目录下的 `workflows/`
（`{library}`）。出厂的流程在 `{shipped}`，只读：不能改、不能删；要在哪条上改，
`ai4sci workflow new --from <它>` 派生一条（名字与 `from` 由平台填，你不起名字）。
库里的流程不依附任何课题，
项目里的研究助理会把它取到自己的工作区里改参数再走。
下面那份指南讲怎么拼、怎么查、怎么存。在服务里有几条补充：

- 你能运行的只有 `ai4sci show …`（查库、查能力）、`ai4sci workflow …`（库里的流程文件）与
  `ai4sci skill show <名字>`（读一个 skill 的全文）：一条命令一行，写 `ai4sci ...`，
  不加路径、不在前面挂环境变量、不接管道和 `;`。别的子命令没放行。你能写的只有 `workflows/`。
- 你不跑实验、不接任务、不碰任何工作区：`ai4sci cap` 那些命令不是给你的、也没放行。有人让你跑实验，
  说「去项目里找研究助理」。
- 确认需求、给产出签字是研究者在项目的工作区页做的，与你无关。
- 回复用 Markdown 排版，怎么清楚怎么来：分段、列表、表格、代码块都随你用，页面照原样渲染；
  先结论后细节，用人话。跟人说话别用「能力单元」这类平台内部的词：就说你查了什么、
  拼了什么、存了什么。
""",
}


class GuideMissing(FileNotFoundError):
    """指南文件不在：服务不能带着空指南起会话。"""


INDEX_STEPS = "## 库里的步骤"
INDEX_FLOWS = "## 库里的流程"
INDEX_TEMPLATES = "## 库里的需求模板"
INDEX_HOW = {
    (PROJECT, INDEX_STEPS): ("跑之前 `ai4sci show cap <名字>` 读它的说明。"
                             "标「已装载」的这个项目能跑；没标的要先在某个工作区的流程实例上"
                             "挂上它的阶段。"),
    (STUDIO, INDEX_STEPS): "`ai4sci show cap <名字>` 看它读什么、产什么、有哪些参数。",
    (PROJECT, INDEX_FLOWS): ("出厂的与编辑台存的。`ai4sci show workflow <名字>` 读说明，"
                             "`ai4sci flow take <名字> --ws <工作区>` 取一条。"),
    (STUDIO, INDEX_FLOWS): ("出厂的与编辑台存的。`ai4sci show workflow <名字>` 看全文，"
                            "`ai4sci workflow new --from <名字>` 派生一条。"),
    (PROJECT, INDEX_TEMPLATES): "`ai4sci show template <名字>` 读全文。",
}


def index(kind: str, steps: Mapping[str, Capability], loaded: Loadout | None = None) -> list[str]:
    """生成的索引，一块一节（外层 #287）：全库的步骤（给了装载就标出装载了哪些）、库里的流程、
    需求模板（只给研究助理）。按名字排，同一个库每轮拼出来一字不差。"""
    rows = []
    for name in sorted(steps):
        d = steps[name]
        on = loaded is not None and loaded.allows_step(name, d.stage, steps)
        rows.append(f"- `{name}`（{d.stage}）：{d.title}——{d.brief}" + ("（已装载）" if on else ""))
    sections = [(INDEX_STEPS, rows)]
    flows = Library(paths.workflows_root(), paths.user_workflows_root()).load_valid()
    sections.append((INDEX_FLOWS, [f"- `{wf.name}`：{wf.title}——{' '.join(wf.summary.split())}"
                                   for wf in sorted(flows, key=lambda wf: wf.name)]))
    if kind == PROJECT:
        # 模板的一级标题是占位的「课题标题」，说它是什么的是开头那段的第一句
        sections.append((INDEX_TEMPLATES, [
            f"- `{t['name']}`：{t['summary'].split('。')[0]}。"
            for t in boards.list_templates(paths.templates_root())]))
    return [f"{heading}\n\n{INDEX_HOW[kind, heading]}\n\n" + ("\n".join(rows) or "（没有）")
            for heading, rows in sections]


def system_prompt(kind: str, guide_path: Path | None = None, tool_guide: str = "",
                  project: Project | None = None,
                  steps: Mapping[str, Capability] | None = None) -> str:
    """前言 + 这家 CLI 的「工具怎么用」（`Chat.tool_guide`，可空）+ 本项目装载的 skill 清单
    （研究助理、给了项目才有）+ 库的索引（给了步骤表才有：起服务时只核对指南在不在）+ 指南原文。"""
    assert kind in KINDS, f"指南只有 {KINDS}，得到 {kind!r}"
    guide_path = GUIDE_PATHS[kind] if guide_path is None else guide_path  # 调用时取，测试可换指南
    if not guide_path.is_file():
        raise GuideMissing(f"助理的指南不在：{guide_path}（服务要在平台仓根下跑）")
    text = guide_path.read_text(encoding="utf-8").strip()
    if not text:
        raise GuideMissing(f"助理的指南是空的：{guide_path}")
    # 库在哪是起服务的人定的（AI4SCI_WORKFLOWS_ROOT、AI4SCI_HOME），前言里写实路径，agent 不用去找
    preamble = (PREAMBLES[kind].replace("{shipped}", str(paths.workflows_root()))
                .replace("{library}", str(paths.user_workflows_root())))
    parts = [preamble.strip()]
    if tool_guide.strip():
        parts.append(tool_guide.strip())
    loaded = loadout.of(project) if kind == PROJECT and project is not None else None
    if loaded is not None:
        catalog = skills.catalog_text(loaded.skills, loaded.unavailable)  # 都没有就是空串
        if catalog:
            parts.append(catalog.strip())
    if steps is not None:
        parts += index(kind, steps, loaded)
    parts.append(text)
    return "\n\n".join(parts) + "\n"
