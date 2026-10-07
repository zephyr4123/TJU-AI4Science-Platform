"""装出来的包得带齐运行时要读的文件（外层 #138）：每颗能力的提示模板（子包里的 .md：多数是
一份 prompt.md，文献检索有种子与筛选两份）都要在 pyproject 的 package-data 里，出厂件由
package.sh 拷进 framework/shipped/ 随包走。漏一样，装的包第一次用到才炸。"""

from __future__ import annotations

import ast
import re
import tomllib
from itertools import pairwise

from framework import paths


def test_every_capability_prompt_is_shipped():
    doc = tomllib.loads((paths.REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    data = doc["tool"]["setuptools"]["package-data"]
    for prompt in sorted((paths.REPO_ROOT / "framework" / "capabilities").glob("*/*.md")):
        package = f"framework.capabilities.{prompt.parent.name}"
        assert prompt.name in data.get(package, []), (
            f"{package} 的 {prompt.name} 没进 package-data")
    assert any(p.startswith("shipped/") for p in data["framework"])


def test_package_script_ships_every_library_paths_knows():
    script = (paths.REPO_ROOT / ".github" / "scripts" / "package.sh").read_text(encoding="utf-8")
    # 出厂件清单只有 paths.SHIPPED 一份：加了库（skills-curated/）这里自动跟上
    for dirname in set(paths.SHIPPED) - {paths.UI_DIRNAME}:
        assert dirname in script, f"package.sh 没拷 {dirname}"
    assert "framework/shipped/ui" in script


def _runtime_modules(root) -> set[str]:
    """框架用 `python -m <模块>` 起的外部模块（自己的包不算）。"""
    found: set[str] = set()
    for top in ("framework", "backends", "compute", "procs"):
        for path in (root / top).rglob("*.py"):
            for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
                if isinstance(node, ast.List):
                    words = [e.value for e in node.elts if isinstance(e, ast.Constant)]
                    for flag, module in pairwise(words):
                        if flag == "-m" and isinstance(module, str):
                            found.add(module.split(".")[0])
    return found - {"framework", "backends", "compute", "procs"}


def test_every_module_the_framework_runs_is_a_runtime_dependency():
    """`python -m ruff` 这类是装的包里也要跑的：放在 dev 组里，源码跑得通、装的包一用就炸
    （外层 #210 Windows 真机：设计作业「No module named ruff」，Mac 装的包一样）。"""
    doc = tomllib.loads((paths.REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    runtime = {re.split(r"[<>=!~ \[]", spec)[0] for spec in doc["project"]["dependencies"]}
    assert _runtime_modules(paths.REPO_ROOT) - runtime == set()


def test_runtime_module_check_sees_python_dash_m(tmp_path):
    (tmp_path / "framework").mkdir()
    (tmp_path / "framework" / "x.py").write_text(
        'run([sys.executable, "-m", "ruff", "check"])\nrun([py, "-m", "framework.cli"])\n',
        encoding="utf-8")
    assert _runtime_modules(tmp_path) == {"ruff"}
