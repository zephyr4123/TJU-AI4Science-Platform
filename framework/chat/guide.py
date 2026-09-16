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
# 协调 agent 能按的按钮：只许 ai4sci；只读的 Bash（ls / cat / grep）在 dontAsk 下本就放行
BASH_RULES = ("Bash(.venv/bin/ai4sci *)", "Bash(ai4sci *)")
# 协调 agent 能写的地方：任务包（manifest、design.md、data/README）与 run 的 journal
WRITABLE_DIRNAMES = ("tasks", "runs")

PREAMBLE = """# 你在服务里

你是这个平台的协调 agent，对面是一个研究者，不一定会写代码。下面那份指南讲你是谁、怎么按按钮。
在服务里有三条补充：

- 命令一律写 `.venv/bin/ai4sci ...`，在仓根跑；任务包在 `tasks/`，run 在 `runs/`。
- 发布键（`ai4sci task publish`）是人按的，你把 manifest 与 design.md 念给人听，人说"对"才按。
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
