"""仓根与几个根目录的读取点，全框架只此一处（纲领 P-15：读数据根的只有这里）。

两类目录分开想：随代码走的**库**——工作流库 `workflows/`、领域包 `domains/`、两位助理的指南
`coordinator/`、页面构建 `ui/web/dist`——缺省都在仓根下；随使用长出来的**数据**——工作区
`workspaces/`、编辑台的对话 `studio/`——根是 `AI4SCI_HOME`，0.x 缺省也是仓根。三个环境变量各自
只在这里读一次、断言一次：指向的不是目录当场炸，不静默回落（P-7 / P-8）。

`parents[1]` 是 framework/paths.py 往上两级，即仓根——搬包时这个数字要跟着改，所以它只在这一处出现。
"""

from __future__ import annotations

import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
HOME_ENV = "AI4SCI_HOME"
WORKFLOWS_ROOT_ENV = "AI4SCI_WORKFLOWS_ROOT"
DOMAINS_ROOT_ENV = "AI4SCI_DOMAINS_ROOT"
WORKFLOWS_DIRNAME = "workflows"
DOMAINS_DIRNAME = "domains"
GUIDES_DIRNAME = "coordinator"


def home() -> Path:
    """数据根：工作区与编辑台的对话都长在它下面。"""
    return _root(HOME_ENV, REPO_ROOT)


def workflows_root() -> Path:
    """工作流库：通用的流，编辑台改它；工作区里的是它的实例（workflow.md §1）。"""
    return _root(WORKFLOWS_ROOT_ENV, REPO_ROOT / WORKFLOWS_DIRNAME)


def domains_root() -> Path:
    return _root(DOMAINS_ROOT_ENV, REPO_ROOT / DOMAINS_DIRNAME)


def _root(env: str, default: Path) -> Path:
    raw = os.environ.get(env)
    root = Path(raw).resolve() if raw else default
    assert root.is_dir(), f"{env} 指向的不是目录：{root}"
    return root
