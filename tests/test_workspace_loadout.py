"""能力按项目装载（纲领 P-26）的机器判据：一个项目里的会话装的是平台自带的常驻 skill，加本项目
各工作区流程实例上挂的能力；不往里切、不往外放。研究助理的 system prompt、执行层的 prompt、
`ai4sci skill` 与 `ai4sci cap` 都从 `workspace/loadout.py` 一处取，装载之外的拒。
"""

from __future__ import annotations

import json

import pytest

from framework import paths
from framework.chat import guide
from framework.cli import main
from framework.executor import prompting
from framework.workspace import loadout
from framework.workspace import project as project_mod
from tests.fixtures import packs_factory as pf
from tests.fixtures import spaces
from tests.test_skills import EMPTY_LEDGER, HELLO_PY, write_skill


@pytest.fixture
def lib(tmp_path, monkeypatch):
    """三处库：平台自带 pdf；收录 literature/paper-lookup、writing/polish（带脚本）、一个坏的；
    领域包 petab。"""
    resident = tmp_path / "skills"
    curated = tmp_path / "skills-curated"
    domains = tmp_path / "domains"
    write_skill(resident, "pdf")
    write_skill(curated / "literature", "paper-lookup", "# 查论文\n\n参考 references/api.md\n")
    (curated / "literature" / "paper-lookup" / "references").mkdir()
    (curated / "literature" / "paper-lookup" / "references" / "api.md").write_text(
        "接口手册\n", encoding="utf-8")
    write_skill(curated / "writing", "polish", "# 润色\n\n`ai4sci skill run polish`\n",
                scripts={"go.py": HELLO_PY})
    write_skill(curated / "writing", "broken", front="---\ndescription: 少了 name\n---\n")
    (curated / "provenance.yaml").write_text(EMPTY_LEDGER, encoding="utf-8")
    (domains / "petab").mkdir(parents=True)
    write_skill(domains / "petab" / "skills", "petab")
    monkeypatch.setenv(paths.SKILLS_ROOT_ENV, str(resident))
    monkeypatch.setenv(paths.CURATED_SKILLS_ROOT_ENV, str(curated))
    monkeypatch.setenv(paths.DOMAINS_ROOT_ENV, str(domains))
    return tmp_path


def _flow(ws, name: str, stages: str) -> None:
    ws.flows.mkdir(exist_ok=True)
    (ws.flows / f"{name}.yaml").write_text(
        f"name: {name}\ntitle: 夹具\nsummary: 夹具\nstages:\n{stages}", encoding="utf-8")


def _names(load: loadout.Loadout) -> list[str]:
    return [s.name for s in load.skills]


def test_a_project_without_flows_loads_only_the_resident_skills(lib):
    ws = spaces.make_workspace(lib, "w")
    load = loadout.of(project_mod.of(ws))
    assert _names(load) == ["pdf"] and load.unavailable == ()
    assert not load.allows_step("design", "设计")


def test_hung_skills_from_every_workspace_flow_are_loaded_and_nothing_else(lib):
    """边界是项目：两个工作区的流程上挂的合起来；没挂的（polish、库里另外的）不装。"""
    w1 = spaces.make_workspace(lib, "w1")
    w2 = spaces.make_workspace(lib, "w2")
    _flow(w1, "a", "  - 文献: [pdf, paper-lookup]\n")
    _flow(w2, "b", "  - 实验: [petab]\n  - 分析\n")
    load = loadout.of(project_mod.of(w1))
    assert _names(load) == ["pdf", "paper-lookup", "petab"]
    assert load.allows_step("analysis", "分析")  # 分析敞开着：这个阶段的步骤都装
    # 一格只挂 skill 不算点名步骤（推荐的工具不是谁来跑这一步），阶段照样敞开
    assert load.allows_step("auto-research", "实验") and load.allows_step("pdf-to-x", "文献")
    assert not load.allows_step("design", "设计")  # 流程里没有设计
    assert loadout.around(w2.root / "experiment") == load  # 执行层按产出目录所在的项目算


def test_the_loadout_follows_the_flow_files_on_every_call(lib):
    ws = spaces.make_workspace(lib, "w")
    _flow(ws, "a", "  - 设计: [design]\n")
    project = project_mod.of(ws)
    assert _names(loadout.of(project)) == ["pdf"]
    assert loadout.of(project).allows_step("design", "设计")
    _flow(ws, "a", "  - 设计: [design]\n  - 写作: [polish]\n")
    assert _names(loadout.of(project)) == ["pdf", "polish"]


def test_hung_but_unusable_skills_and_broken_flows_are_reported_not_dropped(lib):
    ws = spaces.make_workspace(lib, "w")
    _flow(ws, "a", "  - 写作: [broken]\n")
    (ws.flows / "bad.yaml").write_text("name: [\n", encoding="utf-8")
    load = loadout.of(project_mod.of(ws))
    assert _names(load) == ["pdf"]
    reasons = dict(load.unavailable)
    assert "缺 name" in reasons["broken"] and "读不出来" in reasons["w/flows/bad.yaml"]


def test_research_assistant_prompt_carries_this_projects_loadout(lib, tmp_path):
    ws = spaces.make_workspace(lib, "w")
    _flow(ws, "a", "  - 文献: [paper-lookup]\n  - 写作: [broken]\n")
    path = tmp_path / "README.md"
    path.write_text("# 指南正文\n", encoding="utf-8")
    text = guide.system_prompt(guide.PROJECT, path, project=project_mod.of(ws))
    head, _, _ = text.partition("# 指南正文")
    assert "<skill><name>pdf</name>" in head and "<skill><name>paper-lookup</name>" in head
    assert "polish" not in head and "petab" not in head  # 没挂的不进
    assert "- broken：" in head  # 挂着却用不了的单列
    assert "自带的联网搜索与网页读取工具" in head and "ai4sci show skills" in head
    studio = guide.system_prompt(guide.STUDIO, path)
    assert "<available_skills>" not in studio and "## 工具包" not in studio


def test_executor_prompt_carries_the_same_loadout(lib, tmp_path):
    ws = spaces.make_workspace(lib, "w")
    _flow(ws, "a", "  - 实验: [petab]\n")
    template = tmp_path / "prompt.md"
    template.write_text("# 任务 $x\n", encoding="utf-8")
    bare = prompting.build_prompt(template, {"x": "1"})
    assert bare.startswith("# 任务 1\n") and "## 联网" in bare and "## 工具包" not in bare
    full = prompting.build_prompt(template, {"x": "1"}, "领域一句",
                                  loadout.around(ws.root / "experiment" / "1"))
    assert full.index("## 领域约定") < full.index("## 工具包") < full.index("## 联网")
    assert "<skill><name>pdf</name>" in full and "<skill><name>petab</name>" in full
    assert "paper-lookup" not in full
    with pytest.raises(KeyError):
        prompting.build_prompt(template, {})


def test_cli_inside_a_project_only_reaches_the_loadout(lib, capfd, monkeypatch):
    ws = spaces.make_workspace(lib, "w")
    _flow(ws, "a", "  - 文献: [paper-lookup]\n")
    monkeypatch.chdir(project_mod.of(ws).root)
    assert main(["skill", "list"]) == 0
    assert capfd.readouterr().out.splitlines() == ["pdf\t平台\t夹具 pdf",
                                                   "paper-lookup\t收录·文献\t夹具 paper-lookup"]
    assert main(["skill", "show", "paper-lookup"]) == 0
    out = capfd.readouterr().out
    assert "files: references/api.md" in out and "ai4sci skill show paper-lookup <文件>" in out
    assert main(["skill", "show", "paper-lookup", "references/api.md"]) == 0
    assert capfd.readouterr().out == "接口手册\n"
    assert main(["skill", "show", "paper-lookup", "../../../skills/pdf/SKILL.md"]) == 2
    assert "没有文件" in capfd.readouterr().err
    # 没挂的：读、跑都拒，说清先挂到流程上
    assert main(["skill", "show", "polish"]) == 1
    err = capfd.readouterr().err
    assert "没有装载" in err and "flows/" in err and "show skills" in err
    assert main(["skill", "run", "polish"]) == 1
    capfd.readouterr()
    # 挂上，下一条命令就能跑
    _flow(ws, "a", "  - 文献: [paper-lookup]\n  - 写作: [polish]\n")
    assert main(["skill", "run", "polish", "--x"]) == 0
    assert json.loads(capfd.readouterr().out.strip()) == {"args": ["--x"]}


def test_show_skills_searches_the_whole_library_and_marks_the_loadout(lib, capfd, monkeypatch):
    ws = spaces.make_workspace(lib, "w")
    _flow(ws, "a", "  - 文献: [paper-lookup]\n")
    monkeypatch.chdir(project_mod.of(ws).root)
    assert main(["show", "skills"]) == 0
    rows = [line.split("\t") for line in capfd.readouterr().out.splitlines()]
    marks = {row[0]: row[2] for row in rows}
    assert marks == {"pdf": "已装载", "paper-lookup": "已装载", "polish": "未装载",
                     "petab": "未装载", "broken": "不可用"}
    assert main(["show", "skills", "--stage", "写作"]) == 0
    assert [r.split("\t")[0] for r in capfd.readouterr().out.splitlines()] == ["polish", "broken"]
    assert main(["show", "skills", "夹具", "LOOKUP"]) == 0  # 词都要有、不分大小写
    assert [r.split("\t")[0] for r in capfd.readouterr().out.splitlines()] == ["paper-lookup"]
    assert main(["show", "skills", "--stage", "杂项"]) == 2
    assert main(["show", "skills", "--json"]) == 0
    doc = json.loads(capfd.readouterr().out)
    assert {"name": "polish", "where": "收录·写作", "library": "收录", "shelf": "writing",
            "loaded": False, "description": "夹具 polish", "problems": []} in doc


def test_cap_refuses_steps_the_project_does_not_load(lib, capfd, monkeypatch):
    """步骤也按项目装载：流程里没有这个阶段（或那一格点了别的名字）就拒，说清先取流程或改实例。"""
    ws = pf.make_workspace(lib, "w", flow=False)  # 需求已确认：门过了才轮到装载
    monkeypatch.chdir(ws.root)
    assert main(["cap", "design"]) == 1
    err = capfd.readouterr().err
    assert "没有装载步骤 design" in err and "flow take" in err
    _flow(ws, "a", "  - 设计: [reproduction]\n")
    assert main(["cap", "design"]) == 1  # 设计那一格点了别的名字
    capfd.readouterr()
