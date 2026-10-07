"""仓根与平台的家：全框架读这些位置只在这一处（纲领 P-15：读家在哪的只有这里）。

两类目录分开想：随代码走的**出厂件**——出厂的流程 `workflows/`、需求模板 `templates/`、领域包
`domains/`、平台自带的 skill `skills/`、收录的社区 skill `skills-curated/`、两位助理的指南
`coordinator/`、页面构建 `ui/web/dist`；随使用长出来的一切都在**平台的家** `~/.ai4sci`
（外层 #263，主人 2026-10-06：像 Claude Code 的 `~/.claude`，平台的私有东西收在一处、一把清除）：

    ~/.ai4sci/            AI4SCI_HOME 可指向别处（开发、测试）
      agents.yaml         用哪家、每家的供应商 / 模型 / 思考深度（读写点 framework/agents.py）
      computes.yaml       算力（framework/computes.py）
      keys.yaml           key，只有本人能读（framework/keys.py）
      projects/ studio/   项目与编辑台
      claude_code/ codex/ 两家 CLI 的私有目录：会话记录、平台自己的登录
      cache/uv/           skill 与实验环境的依赖缓存
      bin/ tools/         一行命令装出来的程序（外层 #277）：bin/ 只有 ai4sci、进 PATH；tools/ 下
                          是平台本体、Python、uv、两家 CLI 的原生程序。清除留着它们（回到刚装好的
                          样子）

平台不再写用户自己的 `~/.claude`、`~/.codex`、`~/.config`。流程库是两层合起来看：出厂的只读，
人存的在家里的 `studio/workflows/`（外层 #149）。

出厂件有两种活法（外层 #138）：**源码**（clone 了仓库、`make up` 起）出厂件就在仓根下；**包**
（`uv tool install` 装的 wheel）出厂件由 `make package` 拷进 `framework/shipped/` 随包带走。分辨只看
一件事：仓根下有没有 `pyproject.toml`。家在哪与活法无关。
六个环境变量各自只在这里读一次、断言一次：指向的不是目录当场炸，不静默回落（P-7 / P-8）。

`parents[1]` 是 framework/paths.py 往上两级，即仓根——搬包时这个数字要跟着改，所以它只在这一处出现。
"""

from __future__ import annotations

import os
import shlex
import shutil
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
# 打包时 .github/scripts/package.sh 把出厂件拷到这里（不进 git）；装出来的包里它就是出厂件的家
SHIPPED_DIR = Path(__file__).resolve().parent / "shipped"
HOME_ENV = "AI4SCI_HOME"
WORKFLOWS_ROOT_ENV = "AI4SCI_WORKFLOWS_ROOT"
DOMAINS_ROOT_ENV = "AI4SCI_DOMAINS_ROOT"
TEMPLATES_ROOT_ENV = "AI4SCI_TEMPLATES_ROOT"
SKILLS_ROOT_ENV = "AI4SCI_SKILLS_ROOT"
CURATED_SKILLS_ROOT_ENV = "AI4SCI_CURATED_SKILLS_ROOT"
WORKFLOWS_DIRNAME = "workflows"
DOMAINS_DIRNAME = "domains"
TEMPLATES_DIRNAME = "templates"
SKILLS_DIRNAME = "skills"
CURATED_SKILLS_DIRNAME = "skills-curated"
GUIDES_DIRNAME = "coordinator"
UI_DIRNAME = "ui"
STUDIO_DIRNAME = "studio"  # 家里编辑台那一块：chats/ 对话、workflows/ 人存的流程
# 出厂件里每一样在仓根下的位置（页面在 ui/web/dist，包里搬平成 ui/）
SHIPPED = {WORKFLOWS_DIRNAME: Path(WORKFLOWS_DIRNAME), DOMAINS_DIRNAME: Path(DOMAINS_DIRNAME),
           TEMPLATES_DIRNAME: Path(TEMPLATES_DIRNAME), SKILLS_DIRNAME: Path(SKILLS_DIRNAME),
           CURATED_SKILLS_DIRNAME: Path(CURATED_SKILLS_DIRNAME),
           GUIDES_DIRNAME: Path(GUIDES_DIRNAME), UI_DIRNAME: Path("ui") / "web" / "dist"}
DEFAULT_HOME = Path.home() / ".ai4sci"
# 家的标记：平台建的家里才有它；清除（framework/chat/reset.py）只删有标记的目录，
# AI4SCI_HOME 指错了也删不到别处
MARKER_NAME = ".ai4sci-home"
AGENTS_FILENAME = "agents.yaml"
COMPUTES_FILENAME = "computes.yaml"
KEYS_FILENAME = "keys.yaml"
UV_CACHE_PARTS = ("cache", "uv")
# 一行命令装出来的程序（外层 #277）：install/install.sh 写死了同样的名字，
# tests/test_install_script.py 对账
BIN_DIRNAME = "bin"
TOOLS_DIRNAME = "tools"
PYTHON_DIRNAME = "python"
CLI_NAME = "ai4sci"


def from_source() -> bool:
    """在仓库里跑（clone + make up）还是装的包在跑：仓根下有 pyproject.toml 就是仓库。"""
    return (REPO_ROOT / "pyproject.toml").is_file()


def cli() -> str:
    """人在终端里敲什么才跑到这一份安装上（外层 #274）：页面与自检让人照抄的命令用它。入口脚本与
    解释器在同一个 bin 目录（venv 的 `.venv/bin`、`uv tool` 的工具目录都是）；PATH 上找到的
    `ai4sci` 就是它（`~/.local/bin` 的软链也算）写 `ai4sci`，不是就写全路径——源码跑的 `.venv/bin`
    多半不在 PATH 上，PATH 上还可能留着以前装的旧版本，照抄 `ai4sci` 会跑到别的版本上。"""
    here = Path(sys.executable).parent
    mine = shutil.which(CLI_NAME, path=str(here))
    if mine is None:  # 只有 `python -m framework.cli` 能跑的安装
        return f"{shlex.quote(sys.executable)} -m framework.cli"
    found = shutil.which(CLI_NAME)
    if found is not None and Path(found).resolve() == Path(mine).resolve():
        return CLI_NAME
    return shlex.quote(mine)


def home() -> Path:
    """平台的家：缺省 `~/.ai4sci`，第一次用时建、放下标记；`AI4SCI_HOME` 指的目录得已经在。
    指到的目录空着才放标记——指到一个已有东西的目录（比如误设成 `~`）平台照样能用，
    只是清除不认它。"""
    raw = os.environ.get(HOME_ENV)
    root = _existing(HOME_ENV, Path(raw).resolve()) if raw else DEFAULT_HOME
    root.mkdir(parents=True, exist_ok=True)
    if not (root / MARKER_NAME).exists() and not any(root.iterdir()):
        mark(root)
    return root


def mark(root: Path) -> None:
    """放下家的标记：新建的家、清除后留下的空家、迁移脚本搬好的家。"""
    (root / MARKER_NAME).write_text("ai4sci 的家（外层 #263）：清除只删有这个文件的目录。\n",
                                    encoding="utf-8")


def agents_file() -> Path:
    """用哪家、每家的供应商 / 模型 / 思考深度（纲领 P-25）。"""
    return home() / AGENTS_FILENAME


def computes_file() -> Path:
    """算力清单（纲领 P-23）。"""
    return home() / COMPUTES_FILENAME


def keys_file() -> Path:
    """key：只有本人能读（外层 #263）。"""
    return home() / KEYS_FILENAME


def agent_home(name: str) -> Path:
    """一家 CLI 在家里的私有目录（Claude Code 的 CLAUDE_CONFIG_DIR、Codex 的 CODEX_HOME）：
    会话记录与平台自己的登录在里面；名字就是适配器的名字。"""
    root = home() / name
    root.mkdir(exist_ok=True)
    return root


def uv_cache_dir() -> Path:
    """uv 的缓存：skill 脚本与实验环境的依赖都装在这；平台起 uv 时显式交给它（`UV_CACHE_DIR`），
    不用本机的 `~/.cache/uv`，清除时一起走。"""
    return home().joinpath(*UV_CACHE_PARTS)


def bin_dir() -> Path:
    """家里进 PATH 的那个目录：一行命令装的 `ai4sci` 在这（外层 #277）。"""
    return home() / BIN_DIRNAME


def tools_dir() -> Path:
    """一行命令装出来的程序（外层 #277）：`tools/<名字>/`，两家 CLI 的名字就是适配器的名字。"""
    return home() / TOOLS_DIRNAME


def python_dir() -> Path:
    """uv 装 Python 装到这（`UV_PYTHON_INSTALL_DIR`）：一行命令装平台时、平台起 uv 时都指这里，
    不往本机 uv 的缺省位置放第二份。"""
    return tools_dir() / PYTHON_DIRNAME


def workflows_root() -> Path:
    """出厂的流程：随代码走、只读；与 `user_workflows_root()` 合起来才是库（workflow.md §1）。"""
    return _library(WORKFLOWS_ROOT_ENV, WORKFLOWS_DIRNAME)


def user_workflows_root(home_dir: Path | None = None) -> Path:
    """人在编辑台存的流程：家里的 `studio/workflows/`，编辑台的对话在旁边的 `studio/chats/`。
    第一次用时建：适配器把它作为可写目录交给 agent，目录得先在。
    给了 `home_dir` 就按它算（服务端持有自己的家，测试也从这里换）。"""
    root = (home() if home_dir is None else Path(home_dir)) / STUDIO_DIRNAME / WORKFLOWS_DIRNAME
    root.mkdir(parents=True, exist_ok=True)
    return root


def domains_root() -> Path:
    return _library(DOMAINS_ROOT_ENV, DOMAINS_DIRNAME)


def templates_root() -> Path:
    """需求模板的库：通用一份、按学科加；建工作区时照它起草 requirement.md（纲领 P-19）。"""
    return _library(TEMPLATES_ROOT_ENV, TEMPLATES_DIRNAME)


def skills_root() -> Path:
    """平台自带的 skill（纲领 P-22）：常驻，项目里的会话一直装载（P-26）。收录的在
    `curated_skills_root()`，领域包自己的在 `domains/<包>/skills/`；三处都摆成 `<架>/<tag>/<name>/`
    （分类表 `framework/skills/shelves.py`）。"""
    return _library(SKILLS_ROOT_ENV, SKILLS_DIRNAME)


def curated_skills_root() -> Path:
    """收录的社区 skill：按分类表分拣成 `<架>/<tag>/` 子目录，挂到流程实例上才装载
    （P-22、P-26）。"""
    return _library(CURATED_SKILLS_ROOT_ENV, CURATED_SKILLS_DIRNAME)


def guides_root() -> Path:
    """两位助理的指南：README.md 研究助理、studio.md 流程助理（`chat/guide.py` 读）。"""
    return _library(None, GUIDES_DIRNAME)


def ui_dir() -> Path:
    """页面构建出来的静态文件，`ai4sci serve` 缺省端它；没构建就没有，serve 只开接口，所以这里
    不断言。"""
    return shipped_home() / SHIPPED[UI_DIRNAME] if from_source() else SHIPPED_DIR / UI_DIRNAME


def shipped_home() -> Path:
    """出厂件的家：仓库里是仓根，包里是 framework/shipped/。"""
    return REPO_ROOT if from_source() else SHIPPED_DIR


def _library(env: str | None, dirname: str) -> Path:
    """一样出厂件在哪：环境变量指了就它，否则仓库里在仓根下、包里在 framework/shipped/ 下。"""
    raw = os.environ.get(env) if env else None
    if raw:
        return _existing(env or dirname, Path(raw).resolve())
    root = shipped_home() / (SHIPPED[dirname] if from_source() else Path(dirname))
    label = env or f"出厂件 {dirname}"
    return _existing(label, root)


def _existing(label: str, root: Path) -> Path:
    assert root.is_dir(), f"{label} 指向的不是目录：{root}"
    return root
