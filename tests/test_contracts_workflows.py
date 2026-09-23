"""流程文件（P-18）：阶段 + 断点读得出来，点名的能力得在那个阶段、参数得对得上描述符；
坏文件当场报，不静默跳过。"""

from __future__ import annotations

import pytest
import yaml

from framework import paths
from framework.capabilities import discover
from framework.contracts import workflows
from framework.contracts.workflows import Pick, Stage, Stop

GOOD = """\
name: w
title: 一条
summary: >
  两行的
  摘要
stages:
  - 假设
  - 断点: 看一眼假设
  - 设计: [design]
  - 断点: 核对评分脚本
  - 实验: {auto-research: {max_iters: 2}}
  - 验证
"""


def catalog():
    return {name: module.DESCRIPTOR for name, module in discover().items()}


SKILLS = frozenset({"pdf", "download"})


def write(tmp_path, text: str) -> None:
    (tmp_path / "w.yaml").write_text(text, encoding="utf-8")


def test_shipped_workflow_is_one_line_from_design_to_verification():
    found = workflows.load_workflows(paths.workflows_root())
    assert [wf.name for wf in found] == ["reproduce", "research"]
    repro, wf = found
    assert workflows.workflow_problems(repro, catalog(), SKILLS) == []
    assert workflows.remarks(repro) == []
    assert repro.covered == ["文献", "设计", "分析", "验证"]
    # 文献格挂的是两个 skill（能力库里 tag 为 skill 的那一半），不认 skill 时就是「没有这个能力」
    assert repro.caps == ["pdf", "download", "reproduction", "reproducibility"]
    assert [p for p in workflows.workflow_problems(repro, catalog()) if "pdf" in p]
    # 文献格上只有 skill：跑这一阶段的步骤按阶段对，不按名字（格子上的 skill 不算点名）
    assert workflows.matching_step(repro, "reproduction", "设计", skills=SKILLS) == 1
    assert workflows.matching_step(repro, "anything", "文献", skills=SKILLS) == 0
    assert workflows.matching_step(repro, "anything", "文献") is None
    assert workflows.workflow_problems(wf, catalog()) == [] and workflows.remarks(wf) == []
    assert wf.covered == ["设计", "实验", "分析", "验证"]
    assert wf.caps == ["auto-research"]  # 只点名了实验阶段；别的间由助理看着办
    stops = [r for r in wf.stages if isinstance(r, Stop)]
    assert [s.note for s in stops] == ["评分指标核对", "验收"]
    # 断点管前一项：设计完要签、验证完要签
    assert workflows.stop_after(wf, 0) is stops[0] and workflows.stop_after(wf, 4) is stops[1]
    assert workflows.stop_after(wf, 2) is None
    assert workflows.matching_step(wf, "auto-research", "实验") == 2
    assert workflows.matching_step(wf, "analysis", "分析", after=2) == 3
    assert workflows.matching_step(wf, "design", "设计", after=0) is None


def test_stages_parse_in_all_three_spellings(tmp_path):
    write(tmp_path, GOOD)
    [wf] = workflows.load_workflows(tmp_path)
    assert wf.summary == "两行的 摘要"
    assert wf.stages == (
        Stage("假设"), Stop("看一眼假设"), Stage("设计", (Pick("design"),)),
        Stop("核对评分脚本"), Stage("实验", (Pick("auto-research", {"max_iters": 2}),)),
        Stage("验证"))
    assert wf.to_dict()["stages"][4] == {
        "kind": "stage", "stage": "实验",
        "caps": [{"cap": "auto-research", "with": {"max_iters": 2}}]}
    assert wf.to_dict()["stages"][1] == {"kind": "stop", "note": "看一眼假设"}
    write(tmp_path, GOOD.replace("- 断点: 核对评分脚本", "- 断点"))  # 光秃秃的断点也行
    [wf] = workflows.load_workflows(tmp_path)
    assert wf.stages[3] == Stop()
    assert workflows.load_workflows(tmp_path / "nowhere") == []


def test_describe_dir_keeps_a_broken_file_as_a_problem_row(tmp_path):
    """一个坏文件不能让整张清单打不开：它自己占一条、problems 里说原因；反查只用读得出来的。"""
    write(tmp_path, GOOD)
    (tmp_path / "zz.yaml").write_text("name: zz\n", encoding="utf-8")
    rows = workflows.describe_dir(tmp_path, catalog())
    assert [r["name"] for r in rows] == ["w", "zz"]
    assert rows[0]["problems"] == [] and rows[0]["covers"] == ["假设", "设计", "实验", "验证"]
    assert rows[1]["stages"] == [] and rows[1]["problems"] == ["zz.yaml: 缺 title"]
    assert [wf.name for wf in workflows.load_valid(tmp_path)] == ["w"]
    assert workflows.describe_dir(tmp_path / "nowhere", catalog()) == []


def test_used_by_is_looked_up_from_the_files():
    found = workflows.load_workflows(paths.workflows_root())
    assert workflows.used_by(found) == {"auto-research": ["research"],
                                        "pdf": ["reproduce"], "download": ["reproduce"],
                                        "reproduction": ["reproduce"],
                                        "reproducibility": ["reproduce"]}


def test_pick_params_are_checked_against_the_descriptor(tmp_path):
    write(tmp_path, GOOD.replace("{max_iters: 2}", "{nope: 1, max_iters: 'x', resume: true}"))
    [wf] = workflows.load_workflows(tmp_path)
    problems = workflows.workflow_problems(wf, catalog())
    assert len(problems) == 3
    assert "没有的参数 'nope'" in problems[0] and "max_iters 要是 int" in problems[1]
    assert "resume 是每次调用时才定的，不写进流程" in problems[2]
    write(tmp_path, GOOD.replace("{auto-research: {max_iters: 2}}", "{auto-research: [1]}"))
    with pytest.raises(workflows.WorkflowInvalid, match="「参数名: 值」"):
        workflows.load_workflows(tmp_path)


def test_a_capability_must_sit_in_its_own_room(tmp_path):
    write(tmp_path, GOOD.replace("设计: [design]", "设计: [verify, nope]"))
    [wf] = workflows.load_workflows(tmp_path)
    problems = workflows.workflow_problems(wf, catalog())
    assert problems == [
        "第 3 项「设计」里的 verify 属于「验证」阶段，不能放在「设计」阶段里",
        "第 3 项「设计」里的 nope：没有这个能力（步骤：['analysis', 'auto-research', 'design', "
        "'reproducibility', 'reproduction', 'verify']；skill：[]）"]


def test_any_order_of_stages_is_fine_including_going_back(tmp_path):
    """阶段之间不做数据流校验（P-18）：假设完直接写作是开题报告，实验完回设计是改评分脚本，都不是问题。"""
    write(tmp_path, GOOD.replace("  - 验证\n", "  - 写作\n  - 设计\n  - 文献\n"))
    [wf] = workflows.load_workflows(tmp_path)
    assert workflows.workflow_problems(wf, catalog()) == []
    assert wf.covered == ["假设", "设计", "实验", "写作", "文献"]


def test_remarks_are_advice_not_problems(tmp_path):
    write(tmp_path, "name: w\ntitle: t\nsummary: s\nstages: [实验, 分析]\n")
    [wf] = workflows.load_workflows(tmp_path)
    assert workflows.workflow_problems(wf, catalog()) == []
    assert workflows.remarks(wf) == ["有实验或分析、没有验证：数字没人回溯，结果不能算可信"]
    write(tmp_path, GOOD)  # 末尾有验证
    [wf] = workflows.load_workflows(tmp_path)
    assert workflows.remarks(wf) == []


def test_save_workflow_writes_the_shortest_spelling_and_refuses_bad_or_duplicate(tmp_path):
    """编辑台存流程（外层 #68）：形状与检查都过了才落盘，存出的文件能被同一套读回来；同名不覆盖。"""
    doc = {"name": "my-look", "title": "我的流程", "summary": "看一眼",
           "stages": ["假设", {"断点": "看一眼"}, "设计",
                     {"实验": {"auto-research": {"max_iters": 2}}},
                     {"分析": ["analysis"]}, {"断点": "看一眼结论"}]}
    saved = workflows.save_workflow(tmp_path, doc, catalog())
    assert saved.name == "my-look"
    text = (tmp_path / "my-look.yaml").read_text(encoding="utf-8")
    assert "- 假设\n" in text and "- 断点: 看一眼\n" in text and "- 分析:\n  - analysis\n" in text
    [loaded] = workflows.load_workflows(tmp_path)
    assert loaded == saved
    with pytest.raises(FileExistsError, match="已经有一条"):
        workflows.save_workflow(tmp_path, doc, catalog())
    workflows.save_workflow(tmp_path, {**doc, "title": "改了"}, catalog(), overwrite=True)
    assert workflows.load_workflows(tmp_path)[0].title == "改了"
    with pytest.raises(workflows.WorkflowInvalid, match="没有这个能力"):
        workflows.save_workflow(tmp_path, {**doc, "name": "bad", "stages": [{"设计": ["nope"]}]},
                                catalog())
    with pytest.raises(workflows.WorkflowInvalid, match="小写英文"):
        workflows.save_workflow(tmp_path, {**doc, "name": "My Flow"}, catalog())
    assert not (tmp_path / "bad.yaml").exists()


def test_bad_shapes_are_named(tmp_path):
    cases = {
        "name 要等于文件名": GOOD.replace("name: w", "name: other"),
        "缺 title": GOOD.replace("title: 一条\n", ""),
        "缺 summary": GOOD.replace("summary: >\n  两行的\n  摘要\n", ""),
        "stages 要是非空列表": GOOD.replace("stages:", "stages: []\nsteps:"),
        "不是阶段也不是断点": GOOD.replace("- 假设", "- 调参"),
        "不是阶段": GOOD.replace("设计: [design]", "调参: [design]"),
        "第 1 项就是断点": GOOD.replace("  - 假设\n", ""),
        "两个断点挨着": GOOD.replace("  - 设计: [design]\n", ""),
        "要是一句话": GOOD.replace("断点: 看一眼假设", "断点: 3"),
        "单键映射": GOOD.replace("- 断点: 看一眼假设", "- {断点: 看一眼, 设计: null}"),
        "要是名字的列表": GOOD.replace("[design]", "[3]"),
    }
    for message, text in cases.items():
        write(tmp_path, text)
        with pytest.raises(workflows.WorkflowInvalid, match=message):
            workflows.load_workflows(tmp_path)


def test_layout_is_optional_and_round_trips(tmp_path):
    write(tmp_path, GOOD + "layout:\n" + "".join(f"  - [{i * 264}, 0]\n" for i in range(6)))
    [wf] = workflows.load_workflows(tmp_path)
    assert wf.layout is not None and len(wf.layout) == 6 and wf.layout[1] == (264.0, 0.0)
    assert wf.to_dict()["layout"][1] == [264.0, 0.0]
    raw = yaml.safe_load((tmp_path / "w.yaml").read_text(encoding="utf-8"))
    saved = workflows.save_workflow(tmp_path / "out", raw, catalog())
    assert saved.layout == wf.layout
    text = (tmp_path / "out" / "w.yaml").read_text(encoding="utf-8")
    assert "layout:\n- [0, 0]\n- [264, 0]\n" in text
    write(tmp_path, GOOD + "layout: [[0, 0]]\n")
    with pytest.raises(workflows.WorkflowInvalid, match="layout 要是与 stages 一样长"):
        workflows.load_workflows(tmp_path)



def test_a_skill_hangs_on_any_stage_without_params_and_is_tagged(tmp_path):
    """主人 2026-09-22：skill 是能力的一种（tag skill）。哪个阶段都能挂、不带参数；响应体给每个名字
    标 kind，步骤与 skill 不许重名（framework/abilities.py 查）。"""
    write(tmp_path, GOOD.replace("- 设计: [design]", "- 设计: [design, pdf]")
          .replace("- 验证", "- 验证: {download: {depth: 1}}"))
    [wf] = workflows.load_workflows(tmp_path)
    problems = workflows.workflow_problems(wf, catalog(), SKILLS)
    assert problems == ["第 6 项「验证」里的 download 是 skill，不带参数：它的参数在调用时给"]
    [described] = workflows.describe([wf], catalog(), SKILLS)
    assert described["stages"][2]["caps"] == [{"cap": "design", "with": {}, "kind": "步骤"},
                                              {"cap": "pdf", "with": {}, "kind": "skill"}]
    # 不认 skill：既不是步骤也不是 skill，报错里两半都列出来
    [problem, *_] = workflows.workflow_problems(wf, catalog())
    assert "没有这个能力" in problem and "skill：[]" in problem
    # 存回文件还是最短写法，skill 与步骤混在一个清单里
    doc = {**yaml.safe_load(GOOD), "name": "w", "stages": ["文献", {"设计": ["design", "pdf"]}]}
    saved = workflows.save_workflow(tmp_path / "lib", doc, catalog(), skills=SKILLS)
    text = (tmp_path / "lib" / "w.yaml").read_text(encoding="utf-8")
    assert text.endswith("- 设计:\n  - design\n  - pdf\n")
    assert saved.caps == ["design", "pdf"]
    with pytest.raises(workflows.WorkflowInvalid, match="skill：\\['pdf'\\]"):
        workflows.save_workflow(tmp_path / "lib2", {**yaml.safe_load(GOOD), "name": "w",
                                                    "stages": [{"文献": ["nope"]}]},
                                catalog(), skills={"pdf"})


def library(tmp_path) -> workflows.Library:
    """两层库：出厂的一条 research，用户库还不存在（第一次存时才建）。"""
    shipped = tmp_path / "shipped"
    shipped.mkdir()
    (shipped / "research.yaml").write_text(GOOD.replace("name: w", "name: research"),
                                           encoding="utf-8")
    return workflows.Library(shipped, tmp_path / "home" / "studio" / "workflows")


def test_library_lists_both_layers_shipped_first_and_flags_the_source(tmp_path):
    """外层 #149：库 = 出厂的 + 人存的，清单出厂在前、每条标 shipped；用户库不存在就是空。"""
    lib = library(tmp_path)
    assert [d["name"] for d in lib.describe(catalog())] == ["research"]
    assert lib.names() == ["research"] and lib.shipped_names() == {"research"}
    saved = lib.save({**yaml.safe_load(GOOD), "name": "mine"}, catalog())
    assert saved.name == "mine" and (lib.user / "mine.yaml").is_file()
    assert not (lib.shipped / "mine.yaml").exists()  # 出厂目录一个字节都没动
    flags = {d["name"]: d["shipped"] for d in lib.describe(catalog())}
    assert flags == {"research": True, "mine": False}
    assert lib.find("mine") == lib.user / "mine.yaml" and lib.find("nope") is None
    assert [wf.name for wf in lib.load_valid()] == ["research", "mine"]
    assert workflows.used_by(lib.load_valid())["auto-research"] == ["research", "mine"]


def test_library_refuses_shipped_names_on_save_and_remove_but_removes_user_ones(tmp_path):
    """主人 2026-09-22：出厂的流程是平台的底，不能改不能删；人存进去的能删。名字全库唯一：
    存与出厂重名的拒（同名不覆盖那一种拒法），手搬进用户库的重名文件在清单里是一条问题。"""
    lib = library(tmp_path)
    with pytest.raises(FileExistsError, match="出厂的流程，不能改"):
        lib.save({**yaml.safe_load(GOOD), "name": "research"}, catalog(), overwrite=True)
    assert not lib.user.exists()
    with pytest.raises(workflows.WorkflowInvalid, match="出厂的流程，不能删"):
        lib.remove("research")
    with pytest.raises(FileNotFoundError):
        lib.remove("mine")
    lib.save({**yaml.safe_load(GOOD), "name": "mine"}, catalog())
    assert lib.remove("mine") == lib.user / "mine.yaml" and not (lib.user / "mine.yaml").exists()
    (lib.user / "research.yaml").write_text(GOOD.replace("name: w", "name: research"),
                                            encoding="utf-8")
    shipped_row, user_row = lib.describe(catalog())  # 出厂在前，两条都叫 research
    assert shipped_row["shipped"] is True and shipped_row["problems"] == []
    assert user_row["shipped"] is False
    assert user_row["problems"] == ["与出厂的流程 research 重名：改名或删掉这份"]
    assert [wf.name for wf in lib.load_valid()] == ["research"]  # 重名的不算进反查


def test_describe_dir_marks_nothing_as_shipped_unless_told(tmp_path):
    """工作区里的实例哪怕叫 research 也不是出厂的：shipped 由目录定，不由名字定。"""
    (tmp_path / "research.yaml").write_text(GOOD.replace("name: w", "name: research"),
                                            encoding="utf-8")
    assert [d["shipped"] for d in workflows.describe_dir(tmp_path, catalog())] == [False]
    rows = workflows.describe_dir(tmp_path, catalog(), shipped=True)
    assert [d["shipped"] for d in rows] == [True]
