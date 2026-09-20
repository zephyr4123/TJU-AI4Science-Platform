"""skill 系统（纲领 P-22）的机器判据：库的格式、清单的注入、脚本的起法、CLI 的三个子命令。

出厂的两处库（`skills/`、`domains/*/skills/`）在这里逐条过门禁；格式规则用 tmp_path 里的假 skill
验，删掉真库照样过。`uv run --locked --offline` 那一条要环境预热过（`make skills`），没预热就照实
失败。
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from framework import paths, skills
from framework.chat import guide
from framework.cli import main
from framework.executor import prompting
from framework.skills import library, run

REPO_ROOT = Path(__file__).resolve().parent.parent
PEP723 = '# /// script\n# requires-python = ">=3.12"\n# dependencies = []\n# ///\n'
HELLO_PY = PEP723 + (
    '"""夹具脚本：把参数回显成 JSON。"""\nimport json\nimport sys\n\n'
    'print(json.dumps({"args": sys.argv[1:]}))\n'
)


def write_skill(root: Path, name: str, body: str = "# 正文\n\n用法。\n", *,
                front: str | None = None, scripts: dict[str, str] | None = None,
                lock: bool = True) -> Path:
    directory = root / name
    directory.mkdir(parents=True)
    front = f"---\nname: {name}\ndescription: 夹具 {name}\n---\n" if front is None else front
    (directory / "SKILL.md").write_text(front + "\n" + body, encoding="utf-8")
    for filename, text in (scripts or {}).items():
        script = directory / "scripts" / filename
        script.parent.mkdir(exist_ok=True)
        script.write_text(text, encoding="utf-8")
        if lock:
            _lock(script)
    return directory


def _lock(script: Path) -> None:
    proc = subprocess.run([*run.uv_argv(), "lock", "--script", str(script)],
                          capture_output=True, text=True, env=run.uv_env(), check=False)
    assert proc.returncode == 0, proc.stderr


@pytest.fixture
def libraries(tmp_path, monkeypatch):
    """一处通用库 + 一个带 skills/ 的领域包，环境变量指过去；返回 (generic, domains)。"""
    generic = tmp_path / "skills"
    generic.mkdir()
    domains = tmp_path / "domains"
    (domains / "petab").mkdir(parents=True)
    (domains / "bare").mkdir()  # 没有 skills/ 的领域包也得能扫
    monkeypatch.setenv(paths.SKILLS_ROOT_ENV, str(generic))
    monkeypatch.setenv(paths.DOMAINS_ROOT_ENV, str(domains))
    return generic, domains


# ── 出厂的库 ─────────────────────────────────────────────────────────────────
def test_shipped_libraries_pass_the_gate_and_names_are_unique():
    found = skills.all_skills()
    names = [s.name for s in found]
    assert len(names) == len(set(names))
    assert "pdf" in names and "petab" in names
    pdf = skills.find("pdf")
    assert pdf.library == library.GENERIC_LIBRARY
    assert [p.name for p in pdf.scripts] == ["extract.py"]
    assert library.lock_path(pdf.scripts[0]).is_file()
    assert skills.find("petab").library == "petab" and skills.find("petab").scripts == ()


def test_shipped_pdf_script_runs_locked_and_offline(tmp_path):
    """`uv run --locked --offline` 能起——环境要 `make skills` 预热过，这是 make check 的一步。"""
    script = skills.find("pdf").scripts[0]
    proc = subprocess.run([*run.uv_argv(), *run.UV_RUN_ARGS, str(script), "--help"],
                          capture_output=True, text=True, env=run.uv_env(), check=False)
    assert proc.returncode == 0, f"跑 make skills 预热 pdf 的环境：{proc.stderr[-800:]}"
    assert "--input" in proc.stdout and "--out" in proc.stdout
    # 输入不存在：退 2、stderr 说清、不写任何东西
    proc = subprocess.run([*run.uv_argv(), *run.UV_RUN_ARGS, str(script),
                           "--input", str(tmp_path / "nope.pdf")],
                          capture_output=True, text=True, env=run.uv_env(), check=False)
    assert proc.returncode == 2 and "不存在" in proc.stderr and not list(tmp_path.iterdir())


def test_shipped_skill_bodies_are_within_the_spec_limits():
    for skill in skills.all_skills():
        assert len(skill.body.splitlines()) <= library.BODY_MAX_LINES, skill.name
        assert len(skill.description) <= library.DESCRIPTION_MAX, skill.name
        assert "ai4sci skill run" in skill.body or not skill.scripts, \
            f"{skill.name} 有脚本，正文就得写怎么运行"


# ── 格式规则（假 skill）────────────────────────────────────────────────────
def test_load_skill_reads_spec_fields_and_body(tmp_path):
    front = ("---\nname: toy\ndescription: 一句话\ncompatibility: Python 3.12\n"
             "metadata:\n  ai4sci-system-tools: pdftoppm tesseract\n---\n")
    directory = write_skill(tmp_path, "toy", "# toy\n\n正文。\n", front=front,
                            scripts={"go.py": HELLO_PY})
    (directory / "references").mkdir()
    (directory / "references" / "more.md").write_text("细节\n", encoding="utf-8")
    skill = library.load_skill(directory, "通用")
    assert skill.name == "toy" and skill.description == "一句话" and skill.body == "# toy\n\n正文。"
    assert skill.compatibility == "Python 3.12" and skill.system_tools == ("pdftoppm", "tesseract")
    assert [p.name for p in skill.scripts] == ["go.py"]
    assert [p.name for p in skill.references] == ["more.md"]


@pytest.mark.parametrize("front, message", [
    ("---\ndescription: x\n---\n", "缺 name"),
    ("---\nname: other\ndescription: x\n---\n", "与目录名"),
    ("---\nname: Toy_1\ndescription: x\n---\n", "小写字母数字连字符"),
    ("---\nname: toy\n---\n", "缺 description"),
    ("---\nname: toy\ndescription: x\nallowed-tools: Bash\n---\n", "规范之外的字段"),
    ("---\nname: toy\ndescription: x\nmetadata:\n  ai4sci_layer: a\n---\n", "ai4sci- 前缀"),
    ("---\nname: toy\ndescription: x\nmetadata: [1]\n---\n", "字符串到字符串"),
    ("---\nname: toy\ndescription: x\n", "结尾的 ---"),
])
def test_frontmatter_rules_are_enforced(tmp_path, front, message):
    directory = write_skill(tmp_path, "toy", front=front)
    with pytest.raises(library.SkillInvalid, match=message):
        library.load_skill(directory)


def test_missing_skill_md_and_oversized_body_are_rejected(tmp_path):
    (tmp_path / "empty").mkdir()
    with pytest.raises(library.SkillInvalid, match="没有 SKILL.md"):
        library.load_skill(tmp_path / "empty")
    long_body = "\n".join("行" for _ in range(library.BODY_MAX_LINES + 1)) + "\n"
    with pytest.raises(library.SkillInvalid, match="references/"):
        library.load_skill(write_skill(tmp_path, "long", long_body))


def test_scripts_need_a_pep723_header_and_a_lockfile(tmp_path):
    no_header = write_skill(tmp_path, "nohdr", scripts={"go.py": "print(1)\n"}, lock=False)
    with pytest.raises(library.SkillInvalid, match="PEP 723"):
        library.load_skill(no_header)
    no_lock = write_skill(tmp_path, "nolock", scripts={"go.py": HELLO_PY}, lock=False)
    with pytest.raises(library.SkillInvalid, match="锁文件"):
        library.load_skill(no_lock)


def test_scan_reports_every_bad_skill_and_duplicate_names_at_once(tmp_path):
    generic = tmp_path / "skills"
    domain = tmp_path / "domain-skills"
    write_skill(generic, "dup")
    write_skill(domain, "dup")
    write_skill(generic, "bad", front="---\ndescription: x\n---\n")
    with pytest.raises(library.SkillInvalid) as exc:
        library.scan([("通用", generic), ("petab", domain)])
    text = str(exc.value)
    assert "缺 name" in text and "重复" in text


# ── 两层各自的清单 ───────────────────────────────────────────────────────────
def test_coordinator_sees_generic_only_and_executor_sees_its_domain_too(libraries):
    generic, domains = libraries
    write_skill(generic, "pdf")
    write_skill(domains / "petab" / "skills", "petab")
    (domains / "other").mkdir()
    write_skill(domains / "other" / "skills", "other")
    assert [s.name for s in skills.for_coordinator()] == ["pdf"]
    assert [s.name for s in skills.for_executor("petab")] == ["pdf", "petab"]
    assert [s.name for s in skills.for_executor("bare")] == ["pdf"]
    assert [s.name for s in skills.all_skills()] == ["pdf", "other", "petab"]
    with pytest.raises(skills.SkillNotFound, match="有：pdf, other, petab"):
        skills.find("nope")


def test_catalog_is_xml_with_one_line_per_skill_and_empty_when_none(libraries):
    generic, _ = libraries
    assert skills.catalog_text([]) == ""
    write_skill(generic, "pdf", front="---\nname: pdf\ndescription: 解析 <PDF> & 图\n---\n")
    text = skills.catalog_text(skills.for_coordinator())
    assert text.startswith("## 工具包\n\n<available_skills>\n")
    line = "  <skill><name>pdf</name><description>解析 &lt;PDF&gt; &amp; 图</description></skill>"
    assert line in text
    assert "</available_skills>\n\nai4sci skill show" not in text  # 说明句在块后面另起
    assert "`ai4sci skill show <name>`" in text and "`ai4sci skill run <name> …`" in text


def test_research_assistant_prompt_carries_the_catalog_and_the_web_rule(libraries, tmp_path):
    generic, domains = libraries
    write_skill(generic, "pdf")
    write_skill(domains / "petab" / "skills", "petab")
    path = tmp_path / "README.md"
    path.write_text("# 指南正文\n", encoding="utf-8")
    text = guide.system_prompt(guide.WORKSPACE, path)
    head, _, tail = text.partition("# 指南正文")
    assert "<skill><name>pdf</name>" in head and "petab" not in head  # 领域 skill 不给协调层
    assert "自带的联网搜索与网页读取工具" in head and "curl" in head
    assert "ai4sci skill show" in head and "materials/" in head
    studio = guide.system_prompt(guide.STUDIO, path)
    assert "<available_skills>" not in studio and "## 工具包" not in studio


def test_executor_prompt_appends_catalog_and_web_rule(libraries, tmp_path):
    generic, _ = libraries
    write_skill(generic, "pdf")
    template = tmp_path / "prompt.md"
    template.write_text("# 任务 $x\n", encoding="utf-8")
    bare = prompting.build_prompt(template, {"x": "1"})
    assert bare.startswith("# 任务 1\n") and "## 联网" in bare and "## 工具包" not in bare
    full = prompting.build_prompt(template, {"x": "1"}, "领域一句", skills.for_executor("bare"))
    assert full.index("## 领域约定") < full.index("## 工具包") < full.index("## 联网")
    assert "<skill><name>pdf</name>" in full
    with pytest.raises(KeyError):
        prompting.build_prompt(template, {})


def test_executor_bash_whitelist_is_only_the_skill_subcommands():
    assert skills.EXECUTOR_BASH_RULES == ("Bash(ai4sci skill *)",)
    assert set(skills.EXECUTOR_BASH_RULES) < {"Bash(ai4sci *)", "Bash(ai4sci skill *)"}
    assert "Bash(ai4sci skill *)" not in guide.BASH_RULES  # 协调层的 `ai4sci *` 已经盖住它


# ── 起脚本 ───────────────────────────────────────────────────────────────────
def test_pick_script_wants_a_name_only_when_there_are_several(tmp_path):
    one = library.load_skill(write_skill(tmp_path, "one", scripts={"go.py": HELLO_PY}))
    assert run.pick_script(one, None).name == "go.py"
    assert run.pick_script(one, "go").name == "go.py"
    two = library.load_skill(write_skill(tmp_path, "two", scripts={"a.py": HELLO_PY,
                                                                   "b.py": HELLO_PY}))
    with pytest.raises(library.SkillInvalid, match="--script"):
        run.pick_script(two, None)
    assert run.pick_script(two, "b.py").name == "b.py"
    with pytest.raises(library.SkillInvalid, match="没有叫 'c'"):
        run.pick_script(two, "c")
    none = library.load_skill(write_skill(tmp_path, "none"))
    with pytest.raises(library.SkillInvalid, match="没有脚本"):
        run.pick_script(none, None)


def test_run_script_passes_args_through_and_returns_the_exit_code(tmp_path, capfd):
    skill = library.load_skill(write_skill(tmp_path, "echo", scripts={"go.py": HELLO_PY}))
    code = run.run_script(skill.scripts[0], ["--input", "x.pdf", "--out", "d"], cwd=tmp_path)
    out, err = capfd.readouterr()
    assert code == 0 and json.loads(out.strip()) == {"args": ["--input", "x.pdf", "--out", "d"]}
    assert "VIRTUAL_ENV" not in err and "warning" not in err.lower(), err


# ── CLI ──────────────────────────────────────────────────────────────────────
def test_cli_list_show_run(libraries, capfd, tmp_path):
    generic, domains = libraries
    write_skill(generic, "echo", "# echo\n\n运行：`ai4sci skill run echo -- x`\n",
                scripts={"go.py": HELLO_PY})
    write_skill(domains / "petab" / "skills", "petab")
    assert main(["skill", "list"]) == 0
    out = capfd.readouterr().out.splitlines()
    assert out == ["echo\t通用\t夹具 echo", "petab\tpetab\t夹具 petab"]

    assert main(["skill", "show", "echo"]) == 0
    out = capfd.readouterr().out
    assert out.startswith(f"# echo\t通用\t{(generic / 'echo').resolve()}\n")
    assert "scripts: go.py" in out and "运行：`ai4sci skill run echo -- x`" in out
    assert main(["skill", "show", "nope"]) == 2
    assert "有：echo, petab" in capfd.readouterr().err

    assert main(["skill", "run", "echo", "--input", "a", "--flag"]) == 0
    assert json.loads(capfd.readouterr().out.strip()) == {"args": ["--input", "a", "--flag"]}
    assert main(["skill", "run", "petab"]) == 2  # 没有脚本
    assert "没有脚本" in capfd.readouterr().err


def test_make_skills_entry_warms_every_script_and_probes_system_tools(libraries, capsys,
                                                                       monkeypatch):
    generic, _ = libraries
    write_skill(generic, "echo", scripts={"go.py": HELLO_PY})
    proc = subprocess.run([sys.executable, "-m", "framework.skills"], capture_output=True,
                          text=True, env={**run.uv_env(), "PYTHONPATH": str(REPO_ROOT)},
                          check=False, cwd=REPO_ROOT)
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.splitlines() == [f"echo\t通用\t1 个脚本\t{(generic / 'echo').resolve()}"]
    write_skill(generic, "needs", front="---\nname: needs\ndescription: x\nmetadata:\n"
                                        "  ai4sci-system-tools: definitely-not-a-command\n---\n")
    proc = subprocess.run([sys.executable, "-m", "framework.skills"], capture_output=True,
                          text=True, env={**run.uv_env(), "PYTHONPATH": str(REPO_ROOT)},
                          check=False, cwd=REPO_ROOT)
    assert proc.returncode == 1 and "definitely-not-a-command" in proc.stderr
