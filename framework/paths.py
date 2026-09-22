"""仓根与几个根目录的读取点，全框架只此一处（纲领 P-15：读数据根的只有这里）。

两类目录分开想：随代码走的**库**——流程库 `workflows/`、需求模板 `templates/`、领域包 `domains/`、
skill 库 `skills/`、两位助理的指南 `coordinator/`、页面构建 `ui/web/dist`——缺省都在仓根下；
随使用长出来的**数据**——工作区 `workspaces/`、编辑台的对话 `studio/`——根是 `AI4SCI_HOME`，
0.x 缺省也是仓根。五个环境变量各自只在这里读一次、断言一次：指向的不是目录当场炸，
不静默回落（P-7 / P-8）。
按人的配置目录 `~/.config/ai4sci/`（算力清单、底座清单，纲领 P-23 P-25）与 uv 的缓存也在这里给出：
它们和数据根一起是「平台自己要写的目录」（`runtime_paths`），有沙箱的 agent CLI（Codex）要把它们设成
可写根，agent 敲的 `ai4sci` 才写得进去；两份清单各自的读写点仍在 `framework/computes.py` 与
`framework/agents.py`。

`parents[1]` 是 framework/paths.py 往上两级，即仓根——搬包时这个数字要跟着改，所以它只在这一处出现。
"""

from __future__ import annotations

import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
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
CONFIG_DIR = Path.home() / ".config" / "ai4sci"
UV_CACHE_ENV = "UV_CACHE_DIR"
DEFAULT_UV_CACHE = Path.home() / ".cache" / "uv"


def home() -> Path:
    """数据根：工作区与编辑台的对话都长在它下面。"""
    return _root(HOME_ENV, REPO_ROOT)


def workflows_root() -> Path:
    """流程库：通用的流程，编辑台改它；工作区里的是它的实例（workflow.md §1）。"""
    return _root(WORKFLOWS_ROOT_ENV, REPO_ROOT / WORKFLOWS_DIRNAME)


def domains_root() -> Path:
    return _root(DOMAINS_ROOT_ENV, REPO_ROOT / DOMAINS_DIRNAME)


def templates_root() -> Path:
    """需求模板的库：通用一份、按学科加；建工作区时照它起草 requirement.md（纲领 P-19）。"""
    return _root(TEMPLATES_ROOT_ENV, REPO_ROOT / TEMPLATES_DIRNAME)


def skills_root() -> Path:
    """平台通用的 skill 库（纲领 P-22）；领域包自己的在 `domains/<包>/skills/`，不在这里。"""
    return _root(SKILLS_ROOT_ENV, REPO_ROOT / SKILLS_DIRNAME)


def config_dir() -> Path:
    """按人的配置目录：算力清单与底座清单的家（两份文件各自可用环境变量指向别处，读写点在各自模块）。"""
    return CONFIG_DIR


def uv_cache_dir() -> Path:
    """uv 的缓存：skill 脚本 `uv run --offline` 建环境要往里写；uv 自己认 `UV_CACHE_DIR`，这里照它。
    """
    raw = os.environ.get(UV_CACHE_ENV)
    return Path(raw).expanduser() if raw else DEFAULT_UV_CACHE


def runtime_paths() -> list[Path]:
    """平台自己要写的目录（数据根、按人的配置、uv 缓存）：agent 敲的 `ai4sci` 会往里写。
    给端口的 `runtime_paths`（纲领 P-25）；不存在的先建——沙箱的可写根要是真目录。"""
    dirs = [home(), config_dir(), uv_cache_dir()]
    for path in dirs:
        path.mkdir(parents=True, exist_ok=True)
    return dirs


def _root(env: str, default: Path) -> Path:
    raw = os.environ.get(env)
    root = Path(raw).resolve() if raw else default
    assert root.is_dir(), f"{env} 指向的不是目录：{root}"
    return root
