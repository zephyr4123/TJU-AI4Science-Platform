"""skill 系统（纲领 P-22、P-27）的机器判据：三处库的格式、宽进与隔离、清单的样子、脚本的起法、
零 key、收录台账。按项目装载（P-26）在 `test_workspace_loadout.py`。

出厂的三处库（`skills/`、`skills-curated/`、`domains/*/skills/`）在这里逐条过门禁；格式规则用
tmp_path 里的假 skill 验，删掉真库照样过。平台自带的脚本 `uv run --locked` 那一条要环境预热过
（`make skills`），没预热就照实失败。
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from framework import paths, skills
from framework.chat import guide
from framework.cli import main
from framework.skills import library, provenance, run
from framework.workspace import project as project_mod
from tests.fixtures import spaces

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


EMPTY_LEDGER = "upstreams: {}\nskills: []\nrejected: []\n"


@pytest.fixture
def libraries(tmp_path, monkeypatch):
    """平台自带一处、收录一处（带空台账）、一个带 skills/ 的领域包，环境变量指过去；
    返回 (resident, curated, domains)。"""
    resident = tmp_path / "skills"
    resident.mkdir()
    curated = tmp_path / "skills-curated"
    curated.mkdir()
    (curated / "provenance.yaml").write_text(EMPTY_LEDGER, encoding="utf-8")
    domains = tmp_path / "domains"
    (domains / "petab").mkdir(parents=True)
    (domains / "bare").mkdir()  # 没有 skills/ 的领域包也得能扫
    monkeypatch.setenv(paths.SKILLS_ROOT_ENV, str(resident))
    monkeypatch.setenv(paths.CURATED_SKILLS_ROOT_ENV, str(curated))
    monkeypatch.setenv(paths.DOMAINS_ROOT_ENV, str(domains))
    return resident, curated, domains


# ── 出厂的库 ─────────────────────────────────────────────────────────────────
def test_shipped_libraries_pass_the_gate_and_names_are_unique():
    """三处库全部合格（宽进只给研究者自己放进来的）、零 key、台账对得上、平台自带的没有提醒。"""
    found = skills.everything()
    assert found.invalid == (), [(i.dir, i.problems) for i in found.invalid]
    names = [s.name for s in found.skills]
    assert len(names) == len(set(names))
    pdf = skills.find("pdf")
    assert pdf.library == library.RESIDENT and pdf.where == "平台"
    assert [p.name for p in pdf.scripts] == ["extract.py"]
    assert library.lock_path(pdf.scripts[0]).is_file()
    petab = skills.find("petab")
    assert petab.library == "petab" and petab.scripts == ()
    assert [s.name for s in skills.resident().skills] == ["download", "pdf"]
    for skill in found.skills:
        assert library.key_mentions(skill) == [], skill.name
        if skill.library == library.RESIDENT:
            assert skill.notes == (), (skill.name, skill.notes)
    entries = provenance.check()
    assert {e.name for e in entries} == {s.name for s in found.skills
                                         if s.library == library.CURATED}


def test_shipped_pdf_script_runs_locked(tmp_path):
    """`uv run --locked` 能起——平台自带的环境由 `make skills` 预热过，这是 make check 的一步。"""
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


def test_shipped_skills_with_scripts_say_how_to_run_them():
    """有脚本的 skill 正文得写 `ai4sci skill run`（两层 agent 只有这一种起法）；平台自带的正文在
    规范建议的行数以内。"""
    for skill in skills.everything().skills:
        assert "ai4sci skill run" in skill.body or not skill.scripts, \
            f"{skill.dir} 有脚本，正文就得写怎么用 ai4sci skill run 起"
        if skill.library == library.RESIDENT:
            assert len(skill.body.splitlines()) <= library.BODY_MAX_LINES, skill.name


# ── 格式规则（假 skill）────────────────────────────────────────────────────
def test_load_skill_reads_spec_fields_and_body(tmp_path):
    front = ("---\nname: toy\ndescription: 一句话\ncompatibility: Python 3.12\n"
             "metadata:\n  ai4sci-system-tools: pdftoppm tesseract\n---\n")
    directory = write_skill(tmp_path, "toy", "# toy\n\n正文。\n", front=front,
                            scripts={"go.py": HELLO_PY})
    (directory / "references").mkdir()
    (directory / "references" / "more.md").write_text("细节\n", encoding="utf-8")
    skill = library.load_skill(directory)
    assert skill.name == "toy" and skill.description == "一句话" and skill.body == "# toy\n\n正文。"
    assert skill.compatibility == "Python 3.12" and skill.system_tools == ("pdftoppm", "tesseract")
    assert [p.name for p in skill.scripts] == ["go.py"]
    assert [p.name for p in skill.references] == ["more.md"]
    assert skill.files() == ["references/more.md", "scripts/go.py"]  # 锁文件不列
    assert skill.notes == ()


@pytest.mark.parametrize("front, message", [
    ("---\ndescription: x\n---\n", "缺 name"),
    ("---\nname: other\ndescription: x\n---\n", "与目录名"),
    ("---\nname: Toy_1\ndescription: x\n---\n", "小写字母数字连字符"),
    ("---\nname: toy\n---\n", "缺 description"),
    ("---\nname: toy\ndescription: x\n", "结尾的 ---"),
    ("---\n[1, 2]\n---\n", "键值对"),
])
def test_what_a_skill_cannot_do_without_is_rejected(tmp_path, front, message):
    """拦下的只有 agent 认不出、叫不到它的那几样。"""
    directory = write_skill(tmp_path, "toy", front=front)
    with pytest.raises(library.SkillInvalid, match=message):
        library.load_skill(directory)


@pytest.mark.parametrize("front, note", [
    ("---\nname: toy\ndescription: x\nallowed-tools: Bash\nversion: 1\n---\n", "规范之外的字段"),
    ("---\nname: toy\ndescription: x\nmetadata:\n  ai4sci_layer: a\n---\n", "ai4sci- 前缀"),
    ("---\nname: toy\ndescription: x\nmetadata:\n  tags: [a, b]\n---\n", "不是字符串"),
    ("---\nname: toy\ndescription: x\nmetadata: [1]\n---\n", "不是映射"),
    ("---\nname: toy\ndescription: x\nlicense: [MIT]\n---\n", "license"),
])
def test_what_is_off_spec_but_harmless_only_leaves_a_note(tmp_path, front, note):
    """宽进（纲领 P-22）：社区 skill 常带各家的字段，读不了的不读，记一条提醒，不拦。"""
    skill = library.load_skill(write_skill(tmp_path, "toy", front=front))
    assert skill.name == "toy" and any(note in n for n in skill.notes), skill.notes


def test_missing_skill_md_is_rejected_and_a_long_body_only_noted(tmp_path):
    (tmp_path / "empty").mkdir()
    with pytest.raises(library.SkillInvalid, match="没有 SKILL.md"):
        library.load_skill(tmp_path / "empty")
    long_body = "\n".join("行" for _ in range(library.BODY_MAX_LINES + 1)) + "\n"
    skill = library.load_skill(write_skill(tmp_path, "long", long_body))
    assert any("规范建议" in n for n in skill.notes)


def test_scripts_need_a_pep723_header_and_a_lockfile(tmp_path):
    no_header = write_skill(tmp_path, "nohdr", scripts={"go.py": "print(1)\n"}, lock=False)
    with pytest.raises(library.SkillInvalid, match="PEP 723"):
        library.load_skill(no_header)
    no_lock = write_skill(tmp_path, "nolock", scripts={"go.py": HELLO_PY}, lock=False)
    with pytest.raises(library.SkillInvalid, match="锁文件"):
        library.load_skill(no_lock)


def test_scan_isolates_bad_and_duplicate_skills_without_dropping_the_rest(tmp_path):
    """一个坏的不拖垮整库：好的照常在，坏的与重名的（后到的那个）带原因隔离出去。"""
    resident = tmp_path / "skills"
    domain = tmp_path / "domain-skills"
    write_skill(resident, "dup")
    write_skill(resident, "good")
    write_skill(domain, "dup")
    write_skill(resident, "bad", front="---\ndescription: x\n---\n")
    found = library.scan([library.Root(library.RESIDENT, resident),
                          library.Root("petab", domain)])
    assert [s.name for s in found.skills] == ["dup", "good"]
    reasons = {i.name: i.problems for i in found.invalid}
    assert "缺 name" in reasons["bad"][0] and "重复" in reasons["dup"][0]
    assert found.names() == {"dup", "good", "bad"}


def test_curated_library_is_sorted_onto_stage_shelves(libraries):
    """收录库按阶段分架：架决定出处的说法；查找只看目录名，三处合起来唯一，重名就报。"""
    resident, curated, domains = libraries
    write_skill(resident, "pdf")
    write_skill(curated / "literature", "paper-lookup")
    write_skill(curated / "general", "plot-style")
    write_skill(domains / "petab" / "skills", "petab")
    found = skills.everything()
    assert [(s.name, s.where) for s in found.skills] == [
        ("pdf", "平台"), ("paper-lookup", "收录·文献"), ("plot-style", "收录·通用"),
        ("petab", "petab")]
    assert skills.find("paper-lookup").shelf == "literature"
    assert library.shelf_of("文献") == "literature" and library.shelf_of("通用") == "general"
    with pytest.raises(ValueError, match="不是阶段"):
        library.shelf_of("杂项")
    write_skill(curated / "writing", "pdf")
    with pytest.raises(skills.SkillInvalid, match="重名"):
        skills.find("pdf")
    with pytest.raises(skills.SkillNotFound, match="show skills"):
        skills.find("nope")


def test_skill_files_are_readable_but_never_outside_the_skill(libraries, tmp_path):
    resident, _, _ = libraries
    directory = write_skill(resident, "router")
    (directory / "static").mkdir()
    (directory / "static" / "part.md").write_text("片段\n", encoding="utf-8")
    (tmp_path / "secret.txt").write_text("不许读\n", encoding="utf-8")
    skill = skills.find("router")
    assert skill.read("static/part.md") == "片段\n"
    for bad in ("../../secret.txt", str(tmp_path / "secret.txt"), "static/nope.md"):
        with pytest.raises(skills.SkillNotFound, match="没有文件"):
            skill.read(bad)


def test_key_mentions_catch_credentials_but_not_tokenizer_words(tmp_path):
    """零 key（纲领 P-27）：说法与环境变量名都算；分词器里的 pad_token 这类词不算。"""
    clean = write_skill(tmp_path, "clean", "# x\n\ntokenizer.pad_token = tokenizer.eos_token\n")
    assert library.key_mentions(library.load_skill(clean)) == []
    for i, text in enumerate(("Set OPENAI_API_KEY first", "needs an API key", "export HF_TOKEN=x",
                              "client = Client(api_key=k)", "an access token is required")):
        skill = library.load_skill(write_skill(tmp_path, f"dirty{i}", f"# x\n\n{text}\n"))
        assert library.key_mentions(skill) == [f"SKILL.md:8: {text}"], text


def test_ledger_must_match_the_shelves(tmp_path):
    """收录台账（provenance.yaml）与目录一一对得上、许可证在可收的里、原文在 licenses/。"""
    curated = tmp_path / "skills-curated"
    write_skill(curated / "literature", "paper-lookup")
    write_skill(curated / "writing", "stray")
    (curated / "licenses").mkdir()
    (curated / "licenses" / "up.txt").write_text("MIT\n", encoding="utf-8")
    ledger = curated / "provenance.yaml"
    ledger.write_text(
        "upstreams:\n  up:\n    title: Up\n    url: https://x\n    commit: abc\n"
        "    license: MIT\n    license_file: licenses/up.txt\n"
        "  nc:\n    title: NC\n    url: https://y\n    commit: def\n"
        "    license: CC-BY-NC-4.0\n    license_file: licenses/nc.txt\n"
        "skills:\n  - {name: paper-lookup, shelf: writing, upstream: up, path: s/p}\n"
        "  - {name: ghost, shelf: literature, upstream: up, path: s/g}\n"
        "rejected:\n  - {upstream: up, path: s/r}\n", encoding="utf-8")
    with pytest.raises(provenance.LedgerInvalid) as exc:
        provenance.check(curated)
    text = str(exc.value)
    for expected in ("CC-BY-NC-4.0", "licenses/nc.txt 不在",
                     "writing/stray: 在收录库里但台账里没有", "ghost: 台账里有但收录库里没有",
                     "paper-lookup: 台账写架 writing，目录在 literature", "rejected 第 1 行"):
        assert expected in text, expected


# ── 清单 ─────────────────────────────────────────────────────────────────────
def test_catalog_is_xml_with_one_line_per_skill_and_lists_the_unusable(libraries):
    resident, _, _ = libraries
    assert skills.catalog_text([]) == ""
    write_skill(resident, "pdf", front="---\nname: pdf\ndescription: 解析 <PDF> & 图\n---\n")
    text = skills.catalog_text(skills.resident().skills)
    assert text.startswith("## 工具包\n\n<available_skills>\n")
    line = "  <skill><name>pdf</name><description>解析 &lt;PDF&gt; &amp; 图</description></skill>"
    assert line in text
    assert "</available_skills>\n\nai4sci skill show" not in text  # 说明句在块后面另起
    assert "`ai4sci skill show <name>`" in text and "`ai4sci skill run <name> …`" in text
    assert "`ai4sci skill show <name> <文件>`" in text and "清单之外的用不了" in text
    with_bad = skills.catalog_text(skills.resident().skills, [("broken", "缺 name")])
    assert "用不了的" in with_bad and "- broken：缺 name" in with_bad
    assert skills.catalog_text([], [("broken", "缺 name")]).startswith("## 工具包")


def test_executor_bash_whitelist_is_only_the_skill_subcommands():
    assert skills.EXECUTOR_BASH_RULES == ("ai4sci skill",)  # 命令前缀，与 CLI 无关
    assert all(p.startswith("ai4sci") for p in skills.EXECUTOR_BASH_RULES)
    assert "ai4sci skill" not in guide.BASH_RULES  # 协调层的 `ai4sci` 已经盖住它


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
def test_cli_outside_a_project_sees_every_library(libraries, capfd, tmp_path, monkeypatch):
    """不在任何项目里（人在终端、门禁）：三处库全部能列、能读、能跑；按项目装载在
    test_workspace_loadout。"""
    resident, curated, domains = libraries
    monkeypatch.chdir(tmp_path)
    write_skill(resident, "echo", "# echo\n\n运行：`ai4sci skill run echo -- x`\n",
                scripts={"go.py": HELLO_PY})
    write_skill(curated / "writing", "polish")
    write_skill(domains / "petab" / "skills", "petab")
    write_skill(resident, "broken", front="---\ndescription: x\n---\n")
    assert main(["skill", "list"]) == 0
    out = capfd.readouterr().out.splitlines()
    assert out[:3] == ["echo\t平台\t夹具 echo", "polish\t收录·写作\t夹具 polish",
                       "petab\tpetab\t夹具 petab"]
    assert out[3].startswith("broken\t不可用\t") and "缺 name" in out[3]

    assert main(["skill", "show", "echo"]) == 0
    out = capfd.readouterr().out
    assert out.startswith(f"# echo\t平台\t{(resident / 'echo').resolve()}\n")
    assert "scripts: go.py" in out and "运行：`ai4sci skill run echo -- x`" in out
    assert main(["skill", "show", "nope"]) == 2
    assert "show skills" in capfd.readouterr().err
    assert main(["skill", "show", "broken"]) == 1

    assert main(["skill", "run", "echo", "--input", "a", "--flag"]) == 0
    assert json.loads(capfd.readouterr().out.strip()) == {"args": ["--input", "a", "--flag"]}
    assert main(["skill", "run", "petab"]) == 2  # 没有脚本
    assert "没有脚本" in capfd.readouterr().err


CWD_PY = PEP723 + (
    '"""夹具脚本：回显自己在哪跑、拿到了哪些参数。"""\nimport json\nimport os\nimport sys\n\n'
    'print(json.dumps({"cwd": os.getcwd(), "args": sys.argv[1:]}))\n'
)


def test_cli_run_with_ws_starts_the_script_inside_that_workspace(libraries, capfd, tmp_path,
                                                                   monkeypatch):
    """助理站在项目里，skill 写的相对路径（materials/…）得落到点名的工作区，不是项目根（复现那条流程
    里 download 拉到了项目 materials/，reproduction --code 却只找工作区的 materials/，两边对不上）。
    `--ws` 写在 skill 名前后都认，且不递给脚本。"""
    generic, _, _ = libraries
    write_skill(generic, "where", "# where\n\n运行：`ai4sci skill run where`\n",
                scripts={"go.py": CWD_PY})
    ws = spaces.make_workspace(tmp_path, "w1")
    monkeypatch.chdir(project_mod.of(ws).root)
    assert main(["skill", "run", "where", "--out", "materials/x", "--ws", "w1"]) == 0
    doc = json.loads(capfd.readouterr().out.strip())
    assert Path(doc["cwd"]).resolve() == ws.root.resolve()
    assert doc["args"] == ["--out", "materials/x"]
    assert main(["skill", "run", "--ws", "w1", "where", "--out", "materials/x"]) == 0
    again = json.loads(capfd.readouterr().out.strip())
    assert Path(again["cwd"]).resolve() == ws.root.resolve()
    assert main(["skill", "run", "where", "--ws", "nope"]) == 2  # 项目里没有这个工作区
    assert main(["skill", "run", "where", "--ws"]) == 2  # 名字没给


def _make_skills() -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, "-m", "framework.skills"], capture_output=True,
                          text=True, env={**run.uv_env(), "PYTHONPATH": str(REPO_ROOT)},
                          check=False, cwd=REPO_ROOT)


def test_make_skills_gates_all_libraries_and_warms_only_the_resident(libraries):
    resident, curated, _ = libraries
    write_skill(resident, "echo", scripts={"go.py": HELLO_PY})
    proc = _make_skills()
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.splitlines() == ["平台\t1 个 skill\t1 个脚本\t0 条提醒"]
    # 一个不合格就不过（出厂的三处库我们自己负责）
    bad = write_skill(curated / "writing", "Bad_Name", front="---\nname: x\ndescription: y\n---\n")
    proc = _make_skills()
    assert proc.returncode == 1 and "Bad_Name" in proc.stderr
    shutil.rmtree(bad)
    # 收录的进了目录却不在台账里也不过
    write_skill(curated / "writing", "polish")
    proc = _make_skills()
    assert proc.returncode == 1 and "台账里没有" in proc.stderr
    shutil.rmtree(curated / "writing" / "polish")
    # 零 key
    write_skill(resident, "keyed", "# x\n\n先设 OPENAI_API_KEY\n")
    proc = _make_skills()
    assert proc.returncode == 1 and "零 key" in proc.stderr
    shutil.rmtree(resident / "keyed")
    # 平台自带的声明了系统命令就要在 PATH 上
    write_skill(resident, "needs", front="---\nname: needs\ndescription: x\nmetadata:\n"
                                         "  ai4sci-system-tools: definitely-not-a-command\n---\n")
    proc = _make_skills()
    assert proc.returncode == 1 and "definitely-not-a-command" in proc.stderr


def test_download_skill_clones_at_a_commit_and_checks_sha256(tmp_path):
    """出厂的 download skill（P-24）：git 子命令 clone 到指定 commit、留收据；file 子命令校验
    sha256，不对就删掉退 4；目录已存在退 2。不联网：上游是本地 git 仓，文件走 file://。"""
    import hashlib

    fetch = REPO_ROOT / "skills" / "download" / "scripts" / "fetch.py"
    up = tmp_path / "up"
    up.mkdir()
    subprocess.run(["git", "init", "-q", str(up)], check=True)
    (up / "README.md").write_text("hi\n", encoding="utf-8")
    (up / "LICENSE").write_text("MIT\n", encoding="utf-8")
    env = {"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t",
           "GIT_COMMITTER_EMAIL": "t@t"}
    subprocess.run(["git", "-C", str(up), "add", "-A"], check=True)
    subprocess.run(["git", "-C", str(up), "commit", "-qm", "init"], check=True,
                   env={**dict(__import__("os").environ), **env})
    sha = subprocess.run(["git", "-C", str(up), "rev-parse", "HEAD"], capture_output=True,
                         text=True, check=True).stdout.strip()
    ws = tmp_path / "ws"
    ws.mkdir()
    code = run.run_script(fetch, ["git", str(up), "--commit", sha], cwd=ws)
    assert code == 0
    receipt = json.loads((ws / "materials" / "up" / ".ai4sci-download.json").read_text("utf-8"))
    assert receipt["kind"] == "git" and receipt["commit"] == sha and receipt["license"] == "LICENSE"
    assert receipt["out"] == "materials/up" and receipt["files"] == 2
    assert run.run_script(fetch, ["git", str(up)], cwd=ws) == 2  # 已存在不覆盖
    assert run.run_script(fetch, ["git", str(up), "--commit", "deadbeef", "--out", "m/x"],
                          cwd=ws) == 4
    assert not (ws / "m" / "x").exists()
    digest = hashlib.sha256((up / "README.md").read_bytes()).hexdigest()
    url = (up / "README.md").as_uri()
    assert run.run_script(fetch, ["file", url, "--sha256", digest, "--out", "m/readme"],
                          cwd=ws) == 0
    assert (ws / "m" / "readme" / "README.md").read_text(encoding="utf-8") == "hi\n"
    assert run.run_script(fetch, ["file", url, "--sha256", "00", "--out", "m/bad"], cwd=ws) == 4
    assert not (ws / "m" / "bad").exists()
