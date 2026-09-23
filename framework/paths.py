"""仓根与几个根目录的读取点，全框架只此一处（纲领 P-15：读数据根的只有这里）。

两类目录分开想：随代码走的**出厂件**——出厂的流程 `workflows/`、需求模板 `templates/`、领域包
`domains/`、skill 库 `skills/`、两位助理的指南 `coordinator/`、页面构建 `ui/web/dist`；随使用长出
来的**数据**——项目 `projects/`、编辑台的对话 `studio/chats/`、人在编辑台存的流程 `studio/workflows/`
——根是 `AI4SCI_HOME`。流程库是两层合起来看：出厂的只读，人存的在数据根（外层 #149）。

平台有两种活法（外层 #138）：
- **源码**：clone 了仓库、`make up` 起，出厂件就在仓根下，数据根不设也落在仓根（样例项目在那）。
- **包**：`uv tool install` 装的 wheel，出厂件由 `make package` 拷进 `framework/shipped/` 随包带走，
  数据根缺省 `~/ai4sci`（第一次用时建）。分辨只看一件事：仓根下有没有 `pyproject.toml`。
五个环境变量各自只在这里读一次、断言一次：指向的不是目录当场炸，不静默回落（P-7 / P-8）。
按人的配置目录 `~/.config/ai4sci/`（算力清单、底座清单，纲领 P-23 P-25）与 uv 的缓存也在这里
给出（页面「设置 → 存放」念给人看）；两份清单各自的读写点仍在 `framework/computes.py` 与
`framework/agents.py`。

`parents[1]` 是 framework/paths.py 往上两级，即仓根——搬包时这个数字要跟着改，所以它只在这一处出现。
"""

from __future__ import annotations

import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
# 打包时 .github/scripts/package.sh 把出厂件拷到这里（不进 git）；装出来的包里它就是出厂件的家
SHIPPED_DIR = Path(__file__).resolve().parent / "shipped"
HOME_ENV = "AI4SCI_HOME"
WORKFLOWS_ROOT_ENV = "AI4SCI_WORKFLOWS_ROOT"
DOMAINS_ROOT_ENV = "AI4SCI_DOMAINS_ROOT"
TEMPLATES_ROOT_ENV = "AI4SCI_TEMPLATES_ROOT"
SKILLS_ROOT_ENV = "AI4SCI_SKILLS_ROOT"
WORKFLOWS_DIRNAME = "workflows"
DOMAINS_DIRNAME = "domains"
TEMPLATES_DIRNAME = "templates"
SKILLS_DIRNAME = "skills"
GUIDES_DIRNAME = "coordinator"
UI_DIRNAME = "ui"
STUDIO_DIRNAME = "studio"  # 数据根下编辑台的家：chats/ 对话、workflows/ 人存的流程
# 出厂件里每一样在仓根下的位置（页面在 ui/web/dist，包里搬平成 ui/）
SHIPPED = {WORKFLOWS_DIRNAME: Path(WORKFLOWS_DIRNAME), DOMAINS_DIRNAME: Path(DOMAINS_DIRNAME),
           TEMPLATES_DIRNAME: Path(TEMPLATES_DIRNAME), SKILLS_DIRNAME: Path(SKILLS_DIRNAME),
           GUIDES_DIRNAME: Path(GUIDES_DIRNAME), UI_DIRNAME: Path("ui") / "web" / "dist"}
DEFAULT_HOME = Path.home() / "ai4sci"
CONFIG_DIR = Path.home() / ".config" / "ai4sci"
UV_CACHE_ENV = "UV_CACHE_DIR"
DEFAULT_UV_CACHE = Path.home() / ".cache" / "uv"


def from_source() -> bool:
    """在仓库里跑（clone + make up）还是装的包在跑：仓根下有 pyproject.toml 就是仓库。"""
    return (REPO_ROOT / "pyproject.toml").is_file()


def home() -> Path:
    """数据根：项目、编辑台的对话与人存的流程都长在它下面。不设：仓库里就是仓根（样例项目在那），
    装的包是 ~/ai4sci。"""
    raw = os.environ.get(HOME_ENV)
    if raw:
        return _existing(HOME_ENV, Path(raw).resolve())
    if from_source():
        return REPO_ROOT
    DEFAULT_HOME.mkdir(parents=True, exist_ok=True)
    return DEFAULT_HOME


def workflows_root() -> Path:
    """出厂的流程：随代码走、只读；与 `user_workflows_root()` 合起来才是库（workflow.md §1）。"""
    return _library(WORKFLOWS_ROOT_ENV, WORKFLOWS_DIRNAME)


def user_workflows_root(home_dir: Path | None = None) -> Path:
    """人在编辑台存的流程：数据根的 `studio/workflows/`，编辑台的对话在旁边的 `studio/chats/`。
    第一次用时建（与 `DEFAULT_HOME` 同理）：适配器把它作为可写目录交给 agent，目录得先在。
    给了 `home_dir` 就按它算（服务端持有自己的数据根，测试也从这里换）。"""
    root = (home() if home_dir is None else Path(home_dir)) / STUDIO_DIRNAME / WORKFLOWS_DIRNAME
    root.mkdir(parents=True, exist_ok=True)
    return root


def domains_root() -> Path:
    return _library(DOMAINS_ROOT_ENV, DOMAINS_DIRNAME)


def templates_root() -> Path:
    """需求模板的库：通用一份、按学科加；建工作区时照它起草 requirement.md（纲领 P-19）。"""
    return _library(TEMPLATES_ROOT_ENV, TEMPLATES_DIRNAME)


def skills_root() -> Path:
    """平台通用的 skill 库（纲领 P-22）；领域包自己的在 `domains/<包>/skills/`，不在这里。"""
    return _library(SKILLS_ROOT_ENV, SKILLS_DIRNAME)


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


def config_dir() -> Path:
    """按人的配置目录：算力清单与底座清单的家（两份文件各自可用环境变量指向别处，读写点在各自模块）。"""
    return CONFIG_DIR


def uv_cache_dir() -> Path:
    """uv 的缓存：skill 脚本 `uv run --offline` 建环境要往里写；uv 自己认 `UV_CACHE_DIR`，这里照它。
    """
    raw = os.environ.get(UV_CACHE_ENV)
    return Path(raw).expanduser() if raw else DEFAULT_UV_CACHE


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
