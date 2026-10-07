"""文本一律按 UTF-8 读写：中文 Windows 上不写 `encoding`，Python 按系统编码（GBK）来（外层 #210）。

Win11 真机基线里栽在这的有两类：子进程（claude、codex、git 吐 UTF-8，按 GBK 解一遇中文就
`UnicodeDecodeError`，25 条）与测试夹具写的文件（按 GBK 写下、框架按 UTF-8 读）。规矩是「文本模式的
子进程与文件读写都写上 `encoding`」，靠人记迟早漏，所以这里用 ast 把仓里每一处摊开查；每条检查都
带一条反例，证明它抓得到漏写的。
"""

from __future__ import annotations

import ast
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCANNED = ("framework", "backends", "compute", "tests", ".github/scripts")
SUBPROCESS_CALLS = ("run", "Popen", "check_output", "check_call", "call")
TEXT_FILE_CALLS = ("read_text", "write_text")
# 叫 open 但不是开文本文件的：os.open 是文件描述符，tarfile / zipfile 是归档，webbrowser 是浏览器
NOT_TEXT_OPEN = ("os", "tarfile", "zipfile", "gzip", "webbrowser")


def _calls(root: Path):
    for top in SCANNED:
        for path in sorted((root / top).rglob("*.py")):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                if isinstance(node, ast.Call):
                    yield f"{path.relative_to(root).as_posix()}:{node.lineno}", node


def _name(node: ast.Call) -> str:
    func = node.func
    return func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", "")


def _const(node: ast.AST | None) -> object:
    return node.value if isinstance(node, ast.Constant) else None


def _is_ours(func: ast.AST) -> bool:
    """`read_text(p)` / `files.read_text(p)`：平台自己的读法（framework/files.py）。"""
    if isinstance(func, ast.Name):
        return True
    return isinstance(func, ast.Attribute) and getattr(func.value, "id", "") == "files"


def missing_subprocess_encoding(root: Path) -> list[str]:
    """文本模式（`text=True` / `universal_newlines=True`）却没写 `encoding` 的子进程调用。"""
    problems: list[str] = []
    for where, node in _calls(root):
        if _name(node) not in SUBPROCESS_CALLS:
            continue
        kwargs = {kw.arg: kw.value for kw in node.keywords}
        text = kwargs.get("text") or kwargs.get("universal_newlines")
        if _const(text) is True and "encoding" not in kwargs:
            problems.append(where)
    return problems


def missing_file_encoding(root: Path) -> list[str]:
    """没写 `encoding` 的 `read_text` / `write_text` 与文本模式的 `open`。"""
    problems: list[str] = []
    for where, node in _calls(root):
        name, kwargs = _name(node), {kw.arg: kw.value for kw in node.keywords}
        if "encoding" in kwargs:
            continue
        if name in TEXT_FILE_CALLS:
            if _is_ours(node.func):  # `framework.files.read_text`：固定按 UTF-8 读
                continue
            problems.append(where)
        elif name == "open":
            func = node.func
            if isinstance(func, ast.Attribute) and getattr(func.value, "id", "") in NOT_TEXT_OPEN:
                continue
            # 内建 open(路径, 模式)，Path.open(模式)
            args = node.args[1:] if isinstance(func, ast.Name) else node.args
            mode = _const(kwargs.get("mode")) or (_const(args[0]) if args else None) or "r"
            if "b" not in str(mode):
                problems.append(where)
    return problems


def test_every_text_mode_subprocess_names_its_encoding():
    assert missing_subprocess_encoding(REPO_ROOT) == []


def test_every_text_file_read_or_write_names_its_encoding():
    assert missing_file_encoding(REPO_ROOT) == []


def _fake_repo(tmp_path: Path, body: str) -> Path:
    for top in SCANNED:
        (tmp_path / top).mkdir(parents=True)
    (tmp_path / "framework" / "bad.py").write_text(body, encoding="utf-8")
    return tmp_path


def test_checker_catches_a_text_mode_subprocess_without_encoding(tmp_path):
    root = _fake_repo(tmp_path, "import subprocess\n"
                      "subprocess.run(['git', 'log'], capture_output=True, text=True)\n"
                      "subprocess.run(['git', 'log'], text=True, encoding='utf-8')\n")
    assert missing_subprocess_encoding(root) == ["framework/bad.py:2"]


def test_checker_catches_text_files_without_encoding(tmp_path):
    root = _fake_repo(tmp_path, "import os, tarfile\n"
                      "p.write_text('x')\n"
                      "open(p, 'w')\n"
                      "p.open()\n"
                      "p.read_text(encoding='utf-8')\n"
                      "open(p, 'rb')\n"
                      "p.open('wb')\n"
                      "tarfile.open(p, 'w:gz')\n"
                      "read_text(p)\n"
                      "files.read_text(p)\n"
                      "os.open(p, os.O_RDONLY)\n")
    assert missing_file_encoding(root) == ["framework/bad.py:2", "framework/bad.py:3",
                                           "framework/bad.py:4"]
