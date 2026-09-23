"""装出来的包得带齐运行时要读的文件（外层 #138）：每颗能力的 prompt.md 都要在 pyproject 的
package-data 里，出厂件由 package.sh 拷进 framework/shipped/ 随包走。漏一样，装的包第一次用到
才炸。"""

from __future__ import annotations

import tomllib

from framework import paths


def test_every_capability_prompt_is_shipped():
    doc = tomllib.loads((paths.REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    data = doc["tool"]["setuptools"]["package-data"]
    for prompt in sorted((paths.REPO_ROOT / "framework" / "capabilities").glob("*/prompt.md")):
        package = f"framework.capabilities.{prompt.parent.name}"
        assert "prompt.md" in data.get(package, []), f"{package} 的 prompt.md 没进 package-data"
    assert any(p.startswith("shipped/") for p in data["framework"])


def test_package_script_ships_every_library_paths_knows():
    script = (paths.REPO_ROOT / ".github" / "scripts" / "package.sh").read_text(encoding="utf-8")
    for dirname in (paths.WORKFLOWS_DIRNAME, paths.TEMPLATES_DIRNAME, paths.DOMAINS_DIRNAME,
                    paths.SKILLS_DIRNAME, paths.GUIDES_DIRNAME):
        assert dirname in script, f"package.sh 没拷 {dirname}"
    assert "framework/shipped/ui" in script
