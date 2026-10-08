"""流程文件（P-18）：阶段 + 断点读得出来，点名的能力得在那个阶段、参数得对得上描述符；
坏文件当场报，不静默跳过。"""

from __future__ import annotations

import pytest
import yaml

from framework import paths
from framework.capabilities import discover
from framework.contracts import workflow_library, workflows
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


def test_shipped_workflows():
    found = workflows.load_workflows(paths.workflows_root())
    assert [wf.name for wf in found] == ["literature-survey", "reproduce", "research"]
    survey, repro, wf = found
    # 文献调研：一格里先检索再精读，到精读的 sources.md 为止，不排写作（外层 #239）
    assert workflows.workflow_problems(survey, catalog(), SKILLS) == []
    assert survey.covered == ["文献"] and survey.caps == ["literature-search", "literature-read"]
    assert workflows.matching_step(survey, "literature-read", "文献", after=0,
                                   made_by={"literature-search"}) == 0
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
    assert workflows.matching_step(wf, "design", "设计", after=0, made_by={"design"}) is None
    # 外层 #237：没点名的格子里，同一阶段别的步骤读这一格的产出，落在这一格
    assert workflows.matching_step(wf, "reproduction", "设计", after=0, made_by={"design"}) == 0


def test_a_second_step_fed_by_the_first_in_the_same_cell_stays_in_that_cell(tmp_path):
    """外层 #237：一格里点了几个步骤（先检索、再精读），后一个读前一个的产出，落在同一格；
    同一个能力接着自己的产出跑，照旧往后找。"""
    write(tmp_path, "name: w\ntitle: 文献\nsummary: 先检索再精读\nstages:\n"
                    "  - 文献: [literature-search, literature-read]\n  - 断点: 核对\n  - 写作\n")
    [wf] = workflows.load_workflows(tmp_path)
    assert workflows.matching_step(wf, "literature-read", "文献", after=0,
                                   made_by={"literature-search"}) == 0
    assert workflows.matching_step(wf, "literature-read", "文献", after=0,
                                   made_by={"literature-read"}) is None
    assert workflows.matching_step(wf, "literature-search", "文献", after=0,
                                   made_by={"literature-search"}) is None


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
                                        "literature-search": ["literature-survey"],
                                        "literature-read": ["literature-survey"],
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
        "第 3 项「设计」里的 nope：没有这个能力，拼错了？（步骤：['analysis', 'auto-research', "
        "'design', 'literature-read', 'literature-search', 'reproducibility', 'reproduction', "
        "'verify']；"
        "skill 用 ai4sci show skills <词> 查）"]


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




def test_guide_is_optional_round_trips_as_a_block_and_stays_out_of_the_hash(tmp_path):
    """流程的说明（外层 #287）：给研究助理读的「什么时候选它、断点要核什么、怎么走」，选填；存盘写成
    多行块；不算结构——改说明不改 hash、不算不一样（P-15）。"""
    write(tmp_path, GOOD)
    [bare] = workflows.load_workflows(tmp_path)
    assert bare.guide == "" and bare.to_dict()["guide"] == ""
    guide = "什么时候选它：改进一个方法。\n\n断点要核什么：评分脚本与需求一条条对。"
    raw = yaml.safe_load(GOOD) | {"guide": guide + "\n"}
    saved = workflows.save_workflow(tmp_path / "out", raw, catalog())
    assert saved.guide == guide and saved.content_hash() == bare.content_hash()
    text = (tmp_path / "out" / "w.yaml").read_text(encoding="utf-8")
    assert "guide: |-\n  什么时候选它：改进一个方法。\n\n  断点要核什么" in text
    [again] = workflows.load_workflows(tmp_path / "out")
    assert again.guide == guide and again.to_dict()["guide"] == guide
    with pytest.raises(workflows.WorkflowInvalid, match="guide 要是一段文字"):
        workflows.parse_workflow("w.yaml", yaml.safe_load(GOOD) | {"guide": ["不是", "文字"]})


def test_every_shipped_workflow_carries_a_guide_and_a_derived_one_keeps_it(tmp_path):
    """出厂的每条都写了说明（`show workflow` 与 `flow take` 打出来给研究助理）；派生、取到工作区
    都照抄它，不丢。"""
    for wf in workflows.load_workflows(paths.workflows_root()):
        assert wf.guide.strip(), f"{wf.name} 没写 guide"
    lib = library(tmp_path)
    doc = lib.derive("research")
    doc["stages"] = doc["stages"][:-1]
    derived = lib.save(doc, catalog())
    assert derived.guide == lib.load("research").guide

def test_a_skill_hangs_on_any_stage_without_params_and_is_tagged(tmp_path):
    """主人 2026-09-22：skill 是能力的一种（tag skill）。哪个阶段都能挂、不带参数；响应体给每个名字
    标 kind，步骤与 skill 不许重名（framework/capabilities/abilities.py 查）。"""
    write(tmp_path, GOOD.replace("- 设计: [design]", "- 设计: [design, pdf]")
          .replace("- 验证", "- 验证: {download: {depth: 1}}"))
    [wf] = workflows.load_workflows(tmp_path)
    problems = workflows.workflow_problems(wf, catalog(), SKILLS)
    assert problems == ["第 6 项「验证」里的 download 是 skill，不带参数：它的参数在调用时给"]
    [described] = workflows.describe([wf], catalog(), SKILLS)
    assert described["stages"][2]["caps"] == [{"cap": "design", "with": {}, "kind": "步骤"},
                                              {"cap": "pdf", "with": {}, "kind": "skill"}]
    # 不认 skill：既不是步骤也不是 skill，报错列出步骤、skill 指去查（库有几百个，不整串打出来）
    [problem, *_] = workflows.workflow_problems(wf, catalog())
    assert "没有这个能力" in problem and "show skills" in problem
    # 存回文件还是最短写法，skill 与步骤混在一个清单里
    doc = {**yaml.safe_load(GOOD), "name": "w", "stages": ["文献", {"设计": ["design", "pdf"]}]}
    saved = workflows.save_workflow(tmp_path / "lib", doc, catalog(), skills=SKILLS)
    text = (tmp_path / "lib" / "w.yaml").read_text(encoding="utf-8")
    assert text.endswith("- 设计:\n  - design\n  - pdf\n")
    assert saved.caps == ["design", "pdf"]
    with pytest.raises(workflows.WorkflowInvalid, match="nope：没有这个能力"):
        workflows.save_workflow(tmp_path / "lib2", {**yaml.safe_load(GOOD), "name": "w",
                                                    "stages": [{"文献": ["nope"]}]},
                                catalog(), skills={"pdf"})


def library(tmp_path) -> workflow_library.Library:
    """两层库：出厂的一条 research，用户库还不存在（第一次存时才建）。"""
    shipped = tmp_path / "shipped"
    shipped.mkdir()
    (shipped / "research.yaml").write_text(GOOD.replace("name: w", "name: research"),
                                           encoding="utf-8")
    return workflow_library.Library(shipped, tmp_path / "home" / "studio" / "workflows")


def mine() -> dict:
    """人存的一条：比出厂的 research 少最后那个断点（结构一样的会被查重拒）。"""
    doc = {**yaml.safe_load(GOOD), "name": "mine"}
    doc["stages"] = doc["stages"][:-1]
    return doc


def test_library_lists_both_layers_shipped_first_and_flags_the_source(tmp_path):
    """外层 #149：库 = 出厂的 + 人存的，清单出厂在前、每条标 shipped；用户库不存在就是空。"""
    lib = library(tmp_path)
    assert [d["name"] for d in lib.describe(catalog())] == ["research"]
    assert lib.names() == ["research"] and lib.shipped_names() == {"research"}
    saved = lib.save(mine(), catalog())
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
    lib.save(mine(), catalog())
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


# ── 起名、血缘、差异、查重（纲领 P-15，外层 #199）──────────────────────────────
def test_from_is_optional_and_checked_and_round_trips(tmp_path):
    """没有 from 的老文件照常读；from 要是 {name, hash}；存回去 from 紧跟在 name 后面。"""
    write(tmp_path, GOOD)
    assert workflows.load_workflow(tmp_path / "w.yaml").origin is None
    origin = "from: {name: research, hash: 3f2a9c1e0b7d}\n"
    write(tmp_path, GOOD.replace("title: 一条", origin + "title: 一条"))
    wf = workflows.load_workflow(tmp_path / "w.yaml")
    assert wf.origin == workflows.Origin("research", "3f2a9c1e0b7d")
    assert wf.to_dict()["from"] == {"name": "research", "hash": "3f2a9c1e0b7d"}
    for bad in ("from: research", "from: {name: research}", "from: {name: R, hash: abcdef12}",
                "from: {name: research, hash: zz}"):
        write(tmp_path, GOOD.replace("title: 一条", f"{bad}\ntitle: 一条"))
        with pytest.raises(workflows.WorkflowInvalid, match="from 要是"):
            workflows.load_workflow(tmp_path / "w.yaml")
    doc = {**yaml.safe_load(GOOD), "from": wf.origin.to_dict()}
    saved = workflows.save_workflow(tmp_path / "out", doc, catalog())
    text = (tmp_path / "out" / "w.yaml").read_text(encoding="utf-8")
    assert text.startswith("name: w\nfrom:\n  name: research\n") and saved.origin == wf.origin


def test_structure_hash_ignores_words_and_layout_but_not_params_or_stops():
    base = workflows.parse_workflow("w.yaml", yaml.safe_load(GOOD))
    reworded = workflows.parse_workflow("w.yaml", yaml.safe_load(
        GOOD.replace("title: 一条", "title: 换个标题").replace("断点: 看一眼假设", "断点: 换句话")))
    assert reworded.content_hash() == base.content_hash()
    more_iters = workflows.parse_workflow("w.yaml", yaml.safe_load(
        GOOD.replace("max_iters: 2", "max_iters: 3")))
    assert more_iters.content_hash() != base.content_hash()
    no_stop = workflows.parse_workflow("w.yaml", yaml.safe_load(
        GOOD.replace("  - 断点: 看一眼假设\n", "")))
    assert no_stop.content_hash() != base.content_hash()


def test_derived_flows_are_named_after_their_family_and_record_where_they_came_from(tmp_path):
    lib = library(tmp_path)
    research = lib.load("research")
    doc = lib.derive("research")
    assert doc["name"] == "research-2"
    assert doc["from"] == {"name": "research", "hash": research.content_hash()}
    doc["stages"] = doc["stages"][:-1]
    first = lib.save(doc, catalog())
    assert first.name == "research-2" and first.origin.name == "research"
    # 从 research-2 再派生：还是 research 家族，序号往后排
    second = lib.derive("research-2")
    assert second["name"] == "research-3" and second["from"]["name"] == "research-2"
    assert lib.family("research-2") == "research" and lib.family("research") == "research"
    with pytest.raises(FileNotFoundError, match="没有叫 'nope'"):
        lib.derive("nope")


def test_page_saves_get_names_from_the_platform(tmp_path):
    """页面存流程不填名字：带 from（父流程的名字）的是派生，按家族起；不带的按标题里的英文词起。"""
    lib = library(tmp_path)
    doc = {**yaml.safe_load(GOOD), "from": "research"}
    doc.pop("name")
    doc["stages"] = doc["stages"][:-1]
    saved = lib.save(doc, catalog())
    assert saved.name == "research-2"
    assert saved.origin == workflows.Origin("research", lib.load("research").content_hash())
    scratch = {**yaml.safe_load(GOOD), "title": "快速看一眼 Quick Look"}
    scratch.pop("name")
    scratch["stages"] = scratch["stages"][:3]
    assert lib.save(scratch, catalog()).name == "quick-look"
    chinese = {**yaml.safe_load(GOOD), "title": "只有中文"}
    chinese.pop("name")
    chinese["stages"] = chinese["stages"][:2]
    assert lib.save(chinese, catalog()).name == "flow"
    with pytest.raises(workflows.WorkflowInvalid, match="from 'gone' 不在库里"):
        lib.save({**doc, "from": "gone"}, catalog())


def test_names_are_never_handed_out_twice(tmp_path):
    """删掉的名字不再发（工作区实例的 from 还指着它）；序号取最大加一；按标题起名撞了加字母，
    不落进 <家族名>-<序号>（那是派生的）。"""
    lib = library(tmp_path)
    for n in (2, 3):
        doc = lib.derive("research")
        doc["stages"] = doc["stages"][:-n]
        assert lib.save(doc, catalog()).name == f"research-{n}"
    lib.remove("research-2")
    lib.remove("research-3")
    assert lib.next_name("research") == "research-4"
    for n in range(4, 11):
        doc = lib.derive("research")
        doc["stages"] = [*doc["stages"][:4], {"实验": {"auto-research": {"max_iters": n}}}]
        lib.save(doc, catalog())
    assert lib.next_name("research") == "research-11"  # 按数字比，不按字典序
    titled = {**yaml.safe_load(GOOD), "title": "Research"}
    titled.pop("name")
    titled["stages"] = titled["stages"][:1]
    assert lib.save(titled, catalog()).name == "research-b"
    titled["stages"] = titled["stages"] + ["验证"]
    assert lib.save(titled, catalog()).name == "research-c"


def test_structure_and_diff_agree_on_what_counts_as_the_same(tmp_path):
    """查重、hash 与差异同一个口径：一格里挂的先后不算、参数 2 与 2.0 是一个值；同一格挂两次拒。"""
    base = workflows.parse_workflow("w.yaml", {**yaml.safe_load(GOOD), "stages": [
        {"文献": ["pdf", "download"]}, {"实验": {"auto-research": {"max_iters": 2}}}]})
    swapped = workflows.parse_workflow("w.yaml", {**yaml.safe_load(GOOD), "stages": [
        {"文献": ["download", "pdf"]}, {"实验": {"auto-research": {"max_iters": 2.0}}}]})
    assert swapped.structure() == base.structure()
    assert swapped.content_hash() == base.content_hash()
    assert workflow_library.diff(base, swapped, catalog()) == []
    twice = workflows.parse_workflow("w.yaml", {**yaml.safe_load(GOOD), "stages": [
        {"文献": ["pdf", "download", "pdf"]}]})
    assert workflows.workflow_problems(twice, catalog(), SKILLS) == [
        "第 1 项「文献」里 pdf 挂了不止一次：留一个"]


def test_a_twin_pair_flags_the_child_not_the_parent(tmp_path):
    """一对一模一样的只报后到的：有血缘的报子流程（序号到 10 以后也不报到父流程头上，
    按名字的字典序 research-10 排在 research-2 前面）。"""
    lib = library(tmp_path)
    doc = lib.derive("research")
    doc["stages"] = doc["stages"][:-1]
    lib.save(doc, catalog())
    for n in range(3, 10):
        lib.save({**lib.derive("research-2"),
                  "stages": [*doc["stages"][:4], {"实验": {"auto-research": {"max_iters": n}}}]},
                 catalog())
    copy = lib.derive("research-2")
    assert copy["name"] == "research-10"
    lib.save(copy, catalog(), draft=True)
    problems = {row["name"]: row["problems"] for row in lib.describe(catalog())}
    assert problems["research-2"] == []
    assert problems["research-10"] == [
        "与 research-2 一模一样（阶段、能力、参数、断点都相同）：删掉一条"]


def test_a_flow_identical_to_one_in_the_library_is_refused(tmp_path):
    """结构一模一样的不存第二份；参数不同算不同；标题不同不算。"""
    lib = library(tmp_path)
    same = {**yaml.safe_load(GOOD), "name": "copy", "title": "换个标题"}
    with pytest.raises(workflow_library.DuplicateWorkflow, match="库里的 research 和这条一模一样"):
        lib.save(same, catalog())
    nine = {"实验": {"auto-research": {"max_iters": 9}}}
    tweaked = {**same, "stages": [*same["stages"][:4], nine, "验证"]}
    assert lib.save(tweaked, catalog()).name == "copy"
    # 改自己（覆盖）不算和自己重
    assert lib.save({**tweaked, "title": "再改"}, catalog(), overwrite=True).title == "再改"
    # 手搬进来的一模一样的：清单上后到的那条带问题
    (lib.user / "zzz.yaml").write_text(GOOD.replace("name: w", "name: zzz"), encoding="utf-8")
    problems = {row["name"]: row["problems"] for row in lib.describe(catalog())}
    assert problems["research"] == [] and problems["copy"] == []
    assert problems["zzz"] == ["与 research 一模一样（阶段、能力、参数、断点都相同）：删掉一条"]


def test_diff_says_what_changed_in_plain_words_and_flags_a_changed_parent(tmp_path):
    lib = library(tmp_path)
    doc = lib.derive("research")
    doc["stages"] = ["文献", {"假设": ["pdf"]}, "设计", {"断点": "核对评分脚本"},
                     {"实验": {"auto-research": {"max_iters": 5}}}, "验证"]
    lib.save(doc, catalog(), skills=SKILLS)
    row = next(r for r in lib.describe(catalog(), SKILLS) if r["name"] == "research-2")
    caps = catalog()
    design_title, auto = caps["design"].title, caps["auto-research"]
    iters = f"「实验」{auto.title} 的" + next(p.label for p in auto.params if p.name == "max_iters")
    assert row["family"] == "research" and row["parent_changed"] is False
    assert row["diff"] == ["加了阶段「文献」", "「假设」加挂 pdf", "去掉断点「看一眼假设」",
                           f"「设计」不再挂 {design_title}", f"{iters}：2 → 5"]
    # 父流程之后改过：差异照算，并提醒
    (lib.shipped / "research.yaml").write_text(
        GOOD.replace("name: w", "name: research").replace("max_iters: 2", "max_iters: 4"),
        encoding="utf-8")
    row = next(r for r in lib.describe(catalog(), SKILLS) if r["name"] == "research-2")
    assert row["parent_changed"] is True and f"{iters}：4 → 5" in row["diff"]
    assert next(r for r in lib.describe(catalog(), SKILLS) if r["name"] == "research")["diff"] == []
