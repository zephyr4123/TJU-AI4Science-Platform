"""桌面外壳与后端的约定（外层 #282，spec desktop.md §3）：外壳把它写死在
`ui/desktop/src-tauri/src/contract.rs` 一个文件里，与 Python 常量、两份安装脚本、发版脚本是同一份事实。

改后端的 PR 跑的 `make check` 里没有 Rust，看不到外壳；这里用正则读 contract.rs 对账。这张表冻结、只加不改：
已装的外壳跟不上 wheel，哪一处悄悄改了名字，装着的 App 就打不开平台。
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from framework import paths
from framework.workspace import jobs, project

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "ui" / "desktop" / "src-tauri" / "src" / "contract.rs"
TAURI_CONF = ROOT / "ui" / "desktop" / "src-tauri" / "tauri.conf.json"
INSTALL_SH = ROOT / "install" / "install.sh"
INSTALL_PS1 = ROOT / "install" / "install.ps1"
CDN_PY = ROOT / ".github" / "scripts" / "cdn.py"
SERVE_PY = ROOT / "framework" / "cli" / "serve.py"


def _consts(text: str) -> dict[str, object]:
    """contract.rs 里一行一个的 `pub const 名字: 类型 = 字面量;`：字符串、整数、字符串数组。"""
    found: dict[str, object] = {}
    found.update(re.findall(r'^pub const (\w+): &str = "([^"]*)";', text, re.M))
    found.update((name, int(value)) for name, value in
                 re.findall(r"^pub const (\w+): i32 = (\d+);", text, re.M))
    for name, body in re.findall(r"^pub const (\w+): \[&str; \d+\] = \[(.*?)\];", text, re.M | re.S):
        found[name] = re.findall(r'"([^"]*)"', body)
    return found


def _install_vars(text: str) -> set[str]:
    """安装脚本读的平台变量（`$AI4SCI_X`、`${AI4SCI_X:-…}`、`$env:AI4SCI_X`）；脚本自己写给别人的
    （install.ps1 广播 PATH 变化用的 `AI4SCI_INSTALLING`）不算。"""
    return set(re.findall(r"\$(?:env:|\{)?(AI4SCI_[A-Z0-9_]+)", text))


def _contract() -> dict[str, object]:
    found = _consts(CONTRACT.read_text(encoding="utf-8"))
    assert len(found) >= 20, f"contract.rs 只读出 {len(found)} 个常量：写法变了，正则跟着改"
    return found


def test_the_shell_and_the_platform_agree_on_the_home():
    c = _contract()
    assert c["HOME_ENV"] == paths.HOME_ENV
    assert c["HOME_DIRNAME"] == paths.DEFAULT_HOME.name
    assert c["BIN_DIRNAME"] == paths.BIN_DIRNAME
    assert c["CLI_NAME"] == paths.CLI_NAME
    # `ai4sci --version` 打的是 `%(prog)s <版本>`，prog 就是 CLI 的名字
    assert c["VERSION_PREFIX"] == f"{paths.CLI_NAME} "
    assert 'f"' + str(c["SERVE_OK_PREFIX"]) in SERVE_PY.read_text(encoding="utf-8")


def test_the_shell_strips_the_variables_that_would_misplace_a_child():
    """漏进 serve：`AI4SCI_JOB_ID` 让所有 `--detach` 被拒，`AI4SCI_CHAT_ID` 让人的确认被当成助理在调，
    `AI4SCI_PROJECT` 让助理落到错的项目上。"""
    stripped = _contract()["STRIPPED_ENV"]
    assert isinstance(stripped, list)
    for name in (jobs.JOB_ID_ENV, jobs.CHAT_ID_ENV, project.PROJECT_ENV):
        assert name in stripped, name
    assert paths.HOME_ENV not in stripped  # 家原样传下去，测试靠它隔离


def test_the_shell_and_the_release_agree_on_the_dist():
    c = _contract()
    dist = c["DIST_DEFAULT"]
    sh = INSTALL_SH.read_text(encoding="utf-8")
    found = re.search(r'^DIST="\$\{(\w+):-([^}]*)\}"$', sh, re.M)
    assert found and found.groups() == (c["DIST_ENV"], dist), "install.sh 的 DIST"
    ps1 = INSTALL_PS1.read_text(encoding="utf-8")
    found = re.search(r"^\$DIST = if \(\$env:(\w+)\) \{ \$env:\w+ \} else \{ '([^']*)' \}$", ps1, re.M)
    assert found and found.groups() == (c["DIST_ENV"], dist), "install.ps1 的 DIST"
    cdn = CDN_PY.read_text(encoding="utf-8")
    base = re.search(r'^CDN = os\.environ\.get\("CDN_BASE", "([^"]+)"\)$', cdn, re.M)
    prefix = re.search(r'^PREFIX = "([^"]+)"$', cdn, re.M)
    assert base and prefix and f"{base.group(1)}/{prefix.group(1)}" == dist, "cdn.py 的前缀"
    conf = json.loads(TAURI_CONF.read_text(encoding="utf-8"))
    assert conf["plugins"]["updater"]["endpoints"] == [f"{dist}/desktop/latest.json"]


def test_install_scripts_only_read_variables_the_shell_knows():
    """外壳起安装脚本时给的变量与脚本读的是同一组名字：脚本里拼错一个，外壳给的就落空。"""
    c = _contract()
    known = {c["HOME_ENV"], c["DIST_ENV"], c["NO_SETUP_ENV"], c["WHEEL_SHA256_ENV"]}
    for script in (INSTALL_SH, INSTALL_PS1):
        unknown = _install_vars(script.read_text(encoding="utf-8")) - known
        assert unknown == set(), f"{script.name}：{sorted(unknown)}"


def test_the_checker_reads_every_kind_and_catches_a_drift():
    """反例：读得出三种写法；名字改了一个字、脚本里多读一个外壳不知道的变量，都抓得到。"""
    text = ('pub const HOME_ENV: &str = "AI4SCI_HOME";\n'
            'pub const EXIT_BUSY: i32 = 75;\n'
            'pub const STRIPPED_ENV: [&str; 2] = [\n    "AI4SCI_JOB_ID",\n    "PYTHONHOME",\n];\n')
    assert _consts(text) == {"HOME_ENV": "AI4SCI_HOME", "EXIT_BUSY": 75,
                             "STRIPPED_ENV": ["AI4SCI_JOB_ID", "PYTHONHOME"]}
    drifted = _consts(text.replace('"AI4SCI_HOME"', '"AI4SCI_HOMES"'))
    assert drifted["HOME_ENV"] != paths.HOME_ENV
    script = ('if [ -n "${AI4SCI_NO_SETUP:-}" ]; then sha="$AI4SCI_WHEEL_SHA"; fi\n'
              "[Environment]::SetEnvironmentVariable('AI4SCI_INSTALLING', '1', 'User')\n")
    assert _install_vars(script) - {"AI4SCI_NO_SETUP", "AI4SCI_WHEEL_SHA256"} == {"AI4SCI_WHEEL_SHA"}
