"""协调层指南的注入：`coordinator/README.md` 原文 + 一段"你在服务里"的前言，作为 system prompt。

人在终端里当协调层时，Claude Code 读项目 CLAUDE.md 把 README 引进来；服务起的会话用
`--setting-sources ""` 隔离，什么都不读，所以这里显式塞。指南在仓根 `coordinator/`，
不在 framework 包里：装成包运行时这个文件不在，读不到就明说，不悄悄给一份空指南。
"""

from __future__ import annotations

from pathlib import Path

# framework/chat/guide.py 往上三级是仓根；搬包时这个数字要跟着改（同 run/context.py）
REPO_ROOT = Path(__file__).resolve().parents[2]
GUIDE_PATH = REPO_ROOT / "coordinator" / "README.md"
# 协调 agent 能按的按钮：只许裸 `ai4sci`（纲领 P-14 CLI 主导封装）。规则按命令文本前缀匹配，
# 前面挂环境变量、写 `.venv/bin/` 路径都对不上——歪路就此焊死；裸 `ai4sci` 找得到是因为服务把
# 自己 venv 的 bin 放进了 agent 的 PATH（`ClaudeCodeChat.build_env`）。只读的 Bash（ls / grep）
# 在 dontAsk 下是 Claude Code 自己放行的，不归这里管
BASH_RULES = ("Bash(ai4sci *)",)
# 协调 agent 能写的地方：任务包（manifest、design.md、data/README）、run 的 journal、
# 自己拼出来的工作流（外层 #56：拼得出来还要存得下来）
WRITABLE_DIRNAMES = ("tasks", "runs", "workflows")

PREAMBLE = """# 你在服务里

你是这个平台的协调 agent，对面是一个研究者，不一定会写代码。下面那份指南讲你是谁、怎么按按钮。
在服务里有几条补充：

- 你能按的只有 `ai4sci` 的子命令：一条命令一行，写 `ai4sci ...`，不加路径、不在前面挂环境变量、
  不接管道和 `;`。在仓根跑；任务包在 `tasks/`，run 在 `runs/`，工作流在 `workflows/`。
- 要做的事没有对应的按钮（比如想跑一段 python、想复制文件）：不要绕，停下来告诉研究者
  「平台缺这颗按钮」，缺口记下来是平台的事。
- 长按钮（跑实验、写分析、接任务）加 `--detach`：立刻拿到作业号，这一轮就可以结束，不要干等。
  跑完框架会以「框架」的身份开新一轮把结果告诉你，你再向研究者汇报。研究者中途问进度：
  `ai4sci show job <作业号>` 或 `ai4sci show run <run>`。不要自己放后台、不要排"稍后叫醒"：
  你这一轮一结束，后台的子进程就会被杀（外层 #57 #63）。
- 两颗键是人按的：`ai4sci sign task` 发布需求、`ai4sci sign run` 验收结果。你把要签的东西念给人听，
  人自己按。
- 每次回复先说结论、用人话；数字放一行。你看到的命令输出不要原样贴给人。
"""


class GuideMissing(FileNotFoundError):
    """指南文件不在：服务不能带着空指南起会话。"""


def system_prompt(guide_path: Path = GUIDE_PATH) -> str:
    if not guide_path.is_file():
        raise GuideMissing(f"协调层指南不在：{guide_path}（服务要在平台仓根下跑）")
    text = guide_path.read_text(encoding="utf-8").strip()
    if not text:
        raise GuideMissing(f"协调层指南是空的：{guide_path}")
    return PREAMBLE.strip() + "\n\n" + text + "\n"


def allowed_paths(cwd: Path) -> list[Path]:
    return [Path(cwd) / name for name in WRITABLE_DIRNAMES]
