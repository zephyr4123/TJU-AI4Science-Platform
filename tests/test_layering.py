"""依赖方向的机器判据：能用一条命令查的规矩才是规矩。

纲领 §5 给 framework/ 定了单向依赖 `cli → capabilities → chat → experiment → executor →
workspace → skills → contracts`，外加两条：`backends/` 与 `compute/` 是端口，framework 可以用它们、
它们不许反过来 import framework；能力之间互不 import。这些话写在文档里只是标语，靠人
review 迟早会漏，所以这里用 ast 把每个模块的 import 摊开逐条判。

判的是 import 语句本身而不是运行时依赖：静态、不用装环境、也不受 import 顺序影响。
最后一条用例证明这个检查器抓得到反向 import——一个永远返回"没问题"的检查器
比没有检查器更坏。
"""

from __future__ import annotations

import ast
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# 从底到顶：下标越大越靠上层，只许 import 下标不大于自己的层（同层与包内随意）。
LAYERS = ("contracts", "skills", "workspace", "executor", "experiment", "chat", "capabilities",
          "cli")
# 端口：framework 任何一层都可以 import 它们，它们不许 import framework。
PORTS = ("backends", "compute", "tools")


def _imported_modules(path: Path, root: Path) -> list[str]:
    """一个文件里 import 到的模块全名；相对 import 按它在 root 下所处的包补全。"""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    package = list(path.relative_to(root).parent.parts)
    names: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names += [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            if node.level:  # 相对 import：往上退 level-1 级再接 module
                base = package[: len(package) - node.level + 1]
                names.append(".".join([*base, node.module] if node.module else base))
            elif node.module:
                names.append(node.module)
    return names


def _layer_of(module: str) -> str | None:
    """`framework.<layer>...` 里的那个 layer；不是 framework 的模块返回 None。"""
    parts = module.split(".")
    if len(parts) >= 2 and parts[0] == "framework" and parts[1] in LAYERS:
        return parts[1]
    return None


def _capability_of(module: str) -> str | None:
    """`framework.capabilities.<name>...` 里的那个 name。"""
    parts = module.split(".")
    if len(parts) >= 3 and parts[:2] == ["framework", "capabilities"]:
        return parts[2]
    return None


def violations(root: Path) -> list[str]:
    """扫一个仓根，返回越界清单；空清单表示依赖方向是对的。"""
    problems: list[str] = []
    for path in sorted((root / "framework").rglob("*.py")):
        rel = path.relative_to(root)
        own_layer = _layer_of(".".join(rel.with_suffix("").parts))
        own_capability = _capability_of(".".join(rel.with_suffix("").parts))
        for module in _imported_modules(path, root):
            layer = _layer_of(module)
            if layer is None:
                continue
            if own_layer is None:
                problems.append(f"{rel}: framework 顶层模块不该 import 分层包里的 {module}")
                continue
            if LAYERS.index(layer) > LAYERS.index(own_layer):
                problems.append(
                    f"{rel}: {own_layer} 层不许 import 更上层的 {module}"
                    f"（允许的方向是 {' → '.join(reversed(LAYERS))}）"
                )
            capability = _capability_of(module)
            if (own_capability and capability and capability != own_capability):
                problems.append(f"{rel}: 能力 {own_capability} 不许 import 另一个能力 {module}")

    for port in PORTS:
        for path in sorted((root / port).rglob("*.py")):
            rel = path.relative_to(root)
            for module in _imported_modules(path, root):
                if module == "framework" or module.startswith("framework."):
                    problems.append(f"{rel}: 端口 {port}/ 不许 import framework（{module}）")
    return problems


# ── 真仓 ────────────────────────────────────────────────────────────────
def test_framework_dependencies_point_one_way():
    assert violations(REPO_ROOT) == []


def test_every_layer_directory_exists():
    """层名写死在这里，目录被改名时要立刻炸，而不是悄悄少查一层。"""
    for layer in LAYERS:
        assert (REPO_ROOT / "framework" / layer / "__init__.py").is_file(), layer


# ── 检查器自身：抓不到反向 import 的检查器等于没有 ──────────────────────
def _fake_repo(tmp_path: Path, files: dict[str, str]) -> Path:
    for rel, text in files.items():
        path = tmp_path / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    return tmp_path


def test_checker_catches_a_reverse_import(tmp_path):
    root = _fake_repo(tmp_path, {
        "framework/contracts/bad.py": "from framework.cli import main\n",
        "framework/workspace/fine.py": "from framework.contracts import output\n",
    })
    problems = violations(root)
    assert len(problems) == 1, problems
    assert "framework/contracts/bad.py" in problems[0] and "framework.cli" in problems[0]


def test_checker_catches_a_port_importing_framework(tmp_path):
    root = _fake_repo(tmp_path, {"backends/bad.py": "import framework.run.gitwork\n"})
    problems = violations(root)
    assert len(problems) == 1 and "端口" in problems[0]


def test_checker_catches_one_capability_importing_another(tmp_path):
    root = _fake_repo(tmp_path, {
        "framework/capabilities/experiment/bad.py":
            "from framework.capabilities.analysis import report\n",
    })
    problems = violations(root)
    assert len(problems) == 1 and "另一个能力" in problems[0]


def test_checker_resolves_relative_imports(tmp_path):
    """相对 import 也要还原成全名，否则 `from ..cli import x` 就能绕过检查。"""
    root = _fake_repo(tmp_path, {"framework/run/bad.py": "from ..cli import main\n"})
    assert _imported_modules(root / "framework/run/bad.py", root) == ["framework.cli"]
    assert len(violations(root)) == 1
