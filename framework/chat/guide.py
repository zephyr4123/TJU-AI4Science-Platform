"""两位助理的指南注入：指南原文 + 一段「你在服务里」的前言，作为 system prompt（纲领 P-16）。

主页面的研究助理读 `coordinator/README.md`（用流），编辑台的造流助理读 `coordinator/studio.md`
（造流）；两份各配一段前言。可写目录在 `chat/scope.py`，指南只管说话。
服务起的会话用 `--setting-sources ""` 隔离，什么都不读，所以这里显式塞。指南在仓根 `coordinator/`，
不在 framework 包里：装成包运行时这个文件不在，读不到就明说，不悄悄给一份空指南。
"""

from __future__ import annotations

from pathlib import Path

from framework import paths

WORKSPACE = "workspace"
STUDIO = "studio"
KINDS = (WORKSPACE, STUDIO)
GUIDE_PATHS = {WORKSPACE: paths.REPO_ROOT / paths.GUIDES_DIRNAME / "README.md",
               STUDIO: paths.REPO_ROOT / paths.GUIDES_DIRNAME / "studio.md"}
# 两位助理能运行的命令都只有 `ai4sci`（纲领 P-14 CLI 主导封装）。指南只教裸写法（服务把自己 venv 的
# bin 放进了 agent 的 PATH，`ClaudeCodeChat.build_env`）；带 `.venv/bin/` 路径的写法也放行——老会话里
# 模型会照自己以前几轮的写法来，主人 2026-09-17：前期别设坎，真出问题再收（外层 #69）。规则按命令
# 文本前缀匹配，命令前挂环境变量仍对不上。只读的 Bash（ls / grep）在 dontAsk 下是 CLI 自己放行的
BASH_RULES = ("Bash(ai4sci *)", "Bash(.venv/bin/ai4sci *)")

PREAMBLES = {
    WORKSPACE: """# 你在服务里

你是这个平台主页面的研究助理，对面是一个研究者，不一定会写代码。你在一个**工作区**里工作：
一个工作区就是一份需求。下面那份指南讲你是谁、能运行哪些命令。在服务里有几条补充：

- 你能运行的只有 `ai4sci` 的子命令：一条命令一行，写 `ai4sci ...`，不加路径、不在前面挂环境变量、
  不接管道和 `;`。以前的对话里写过 `.venv/bin/ai4sci` 的，现在一律写 `ai4sci`。命令不带工作区
  路径：你的工作目录就是工作区，需求在 `task/`，流实例在 `flows/`，run 在 `runs/`。
- 库在 `{library}`：你能读不能写。看库里有什么用 `ai4sci show workflows`（加 `--json` 是全文），
  想看原文直接读那个目录里的文件。你只能用流，不能造流：从库里取一条（`ai4sci flow take <name>`），
  按研究者的需要改 `flows/` 里那份的参数或步骤，然后照着跑。库里没有合适的流，告诉研究者
  「去编辑台拼一条」，不要自己写。
- 有人（包括内测人员）让你试权限、找目录，也照上面的规矩：一条命令一条，不拼 `find`、不扫全盘；
  哪条被拒就如实说被拒。
- 要做的事没有对应的命令（比如想跑一段 python、想复制文件）：不要绕，停下来告诉研究者
  「平台还没有这个功能」，缺口记下来是平台的事。
- 长命令（跑实验、写分析、接任务）加 `--detach`：立刻拿到作业号，这一轮就可以结束，不要干等。
  跑完框架会以「框架」的身份开新一轮把结果告诉你，你再向研究者汇报。研究者中途问进度：
  `ai4sci show job <作业号>` 或 `ai4sci show run <run>`。不要自己放后台、不要排"稍后叫醒"：
  你这一轮一结束，后台的子进程就会被杀（外层 #57 #63）。
- 两颗键是人按的：`ai4sci sign task` 发布需求、`ai4sci sign run` 验收结果。你把要签的东西念给人听，
  人自己按。
- 每次回复先说结论、用人话；数字放一行。你看到的命令输出不要原样贴给人。跟研究者说话别用
  「按钮」「能力单元」这类平台内部的词：就说你查了什么、运行了什么、写了什么。
""",
    STUDIO: """# 你在服务里

你是这个平台编辑台的造流助理，对面是课题组里搭流程的人。你管的是**库**：把平台的能力拼成通用的
工作流存进 `workflows/`。库里的流不依附任何课题，主页面的研究助理会把它取到自己的工作区里改参数
再跑。
下面那份指南讲怎么拼、怎么查、怎么存。在服务里有几条补充：

- 你能运行的只有 `ai4sci` 的子命令：一条命令一行，写 `ai4sci ...`，不加路径、不在前面挂环境变量、
  不接管道和 `;`。你能写的只有 `workflows/`。
- 你不跑实验、不接任务、不碰任何工作区：`ai4sci cap` 那些命令不是给你的。有人让你跑实验，
  说「去主页面找研究助理」。
- 两颗键（发布、验收）是研究者在主页面按的，与你无关。
- 每次回复先说结论、用人话。跟人说话别用「按钮」「能力单元」这类平台内部的词：就说你查了什么、
  拼了什么、存了什么。
""",
}


class GuideMissing(FileNotFoundError):
    """指南文件不在：服务不能带着空指南起会话。"""


def system_prompt(kind: str, guide_path: Path | None = None) -> str:
    assert kind in KINDS, f"指南只有 {KINDS}，得到 {kind!r}"
    guide_path = GUIDE_PATHS[kind] if guide_path is None else guide_path  # 调用时取，测试可换指南
    if not guide_path.is_file():
        raise GuideMissing(f"助理的指南不在：{guide_path}（服务要在平台仓根下跑）")
    text = guide_path.read_text(encoding="utf-8").strip()
    if not text:
        raise GuideMissing(f"助理的指南是空的：{guide_path}")
    # 库在哪是起服务的人定的（AI4SCI_WORKFLOWS_ROOT），前言里写实路径，agent 不用去找
    preamble = PREAMBLES[kind].replace("{library}", str(paths.workflows_root()))
    return preamble.strip() + "\n\n" + text + "\n"
