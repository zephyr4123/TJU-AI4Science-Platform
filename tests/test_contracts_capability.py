"""能力描述符与发现：每个能力都得说清自己属于哪个阶段、五栏（职责 / 边界 / 输入 / 产出 / 终止条件）
都填了，入口签名与描述符对得上（P-12、P-18、P-19）；名、一行、详情各守各的文案规矩（P-21）。

`discover()` 里的断言是生产路径上的机器判据，这里既证明它对真能力放行，也证明它抓得住
各种对不上的假模块——一个永远放行的检查器比没有检查器更坏。
"""

from __future__ import annotations

import json
from pathlib import Path
from types import ModuleType

import pytest

from framework.capabilities import MAIN_FILES, check_capability_module, command_name, discover
from framework.contracts.capability import (
    COLUMNS,
    Capability,
    CapabilityFailed,
    Inputs,
    Param,
    Ports,
)
from framework.contracts.stages import STAGE_NAMES, STAGE_SLUGS, name_of, slug_of

FIVE = {"does": "干", "does_not": "不干", "brings": "带", "leaves": "留", "stops": "停"}


def C(name: str, **kw) -> Capability:
    """测试用的最小描述符：阶段、标题与五栏给定值，只让每个用例关心自己那一处。
    缺省阶段是还没定主文件的「假设」，主文件那条断言另有用例。"""
    return Capability(name, **{"stage": "假设", "title": "t", "brief": "b", **FIVE, **kw})


def _module(name: str, descriptor: object, entry: object) -> ModuleType:
    module = ModuleType(name)
    if descriptor is not None:
        module.DESCRIPTOR = descriptor
    if entry is not None:
        module.run = entry
    return module


def test_discover_finds_the_six_capabilities_and_all_pass_the_checks():
    found = discover()
    assert set(found) == {"design", "reproduction", "auto-research", "analysis", "reproducibility",
                          "verify"}
    for name, module in found.items():
        assert module.DESCRIPTOR.name == name
        json.dumps(module.DESCRIPTOR.to_dict(), ensure_ascii=False)  # UI 后端要能直接吃


def test_command_name_turns_underscores_into_hyphens():
    assert command_name("auto_research") == "auto-research"
    assert command_name("verify") == "verify"


def test_who_runs_what_and_who_can_continue():
    found = discover()
    assert found["auto-research"].DESCRIPTOR.needs_compute is True
    assert found["analysis"].DESCRIPTOR.needs_compute is False
    assert found["verify"].DESCRIPTOR.needs_executor is False
    assert {n for n, m in found.items() if m.DESCRIPTOR.continuable} == {
        "design", "reproduction", "auto-research"}


def test_param_names_match_entrypoint_keyword_arguments():
    for name, module in discover().items():
        check_capability_module(name.replace("-", "_"), module)  # 不抛就是一致


@pytest.mark.parametrize("descriptor, entry, message", [
    (None, lambda output_dir, inputs, ports: "", "没有导出"),
    (C("other"), lambda output_dir, inputs, ports: "", "必须等于子包名"),
    (C("cap"), None, "没有导出 run"),
    (C("cap"), lambda ports, inputs, output_dir: "", "前三个参数"),
    (C("cap"), lambda run_dir, ports: "", "前三个参数"),
    (C("cap", params=(Param("k", "int", 1, "h", "k"),)),
     lambda output_dir, inputs, ports: "", "对不上"),
    (C("cap"), lambda output_dir, inputs, ports, *, k=1: "", "对不上"),
    (C("cap"), lambda output_dir, inputs, ports, extra: "", "只许关键字参数"),
])
def test_check_rejects_modules_that_do_not_match(descriptor, entry, message):
    with pytest.raises(AssertionError, match=message):
        check_capability_module("cap", _module("cap", descriptor, entry))


def test_main_file_of_the_stage_must_be_named_in_leaves():
    """P-20：文件名按阶段定。进已定主文件的阶段，「产出」栏没写到主文件就不让注册；
    还没定主文件的阶段不查；真的四个都写到了。"""
    entry = lambda output_dir, inputs, ports: ""  # noqa: E731
    half = C("cap", stage="实验", leaves="留 results.json")
    with pytest.raises(AssertionError, match="主文件 ledger.tsv"):
        check_capability_module("cap", _module("cap", half, entry))
    ok = C("cap", stage="实验", leaves="ledger.tsv 与 iters/iter_N/results.json")
    assert check_capability_module("cap", _module("cap", ok, entry)) is ok
    open_stage = C("cap", stage="写作", leaves="留")
    assert check_capability_module("cap", _module("cap", open_stage, entry)) is open_stage
    assert set(MAIN_FILES) < set(STAGE_NAMES)
    for module in discover().values():
        for main in MAIN_FILES[module.DESCRIPTOR.stage]:
            assert main in module.DESCRIPTOR.leaves


def test_check_accepts_a_matching_module_and_maps_hyphens():
    descriptor = C("cap", params=(Param("k", "int", 1, "h", "k"),))
    module = _module("cap", descriptor, lambda output_dir, inputs, ports, *, k=1: "ok")
    assert check_capability_module("cap", module) is descriptor
    hyphened = C("auto-thing")
    module = _module("auto_thing", hyphened, lambda output_dir, inputs, ports: "ok")
    assert check_capability_module("auto_thing", module) is hyphened


def test_descriptor_rejects_bad_stage_and_duplicate_params():
    with pytest.raises(AssertionError, match="阶段"):
        C("cap", stage="调参")
    with pytest.raises(AssertionError, match="重复"):
        C("cap", params=(Param("k", "int", 1, "h", "k"),) * 2)


@pytest.mark.parametrize("key, label", COLUMNS)
def test_descriptor_needs_all_five_columns(key, label):
    with pytest.raises(AssertionError, match=f"「{label}」空着"):
        C("cap", **{key: "  "})


def test_descriptor_needs_a_title_and_no_defaults_for_the_human_copy():
    with pytest.raises(AssertionError, match="title"):
        C("cap", title=" ")
    with pytest.raises(TypeError):  # 阶段、标题与五栏都是必填的，不给缺省
        Capability("cap")  # type: ignore[call-arg]


@pytest.mark.parametrize("kw, message", [
    ({"title": "把评分脚本与基线都写出来"}, "title 超过"),          # 名：九个字
    ({"title": "干什么的"}, "「干什么」"),                          # 名：问句式口语
    ({"brief": " "}, "brief"),                                     # 一行：必填
    ({"brief": "一" * 31}, "brief 超过"),                           # 一行：三十字
    ({"brief": "读 design/1 的 scoring.yaml"}, "路径或参数名"),      # 一行：不带路径
    ({"brief": "按 max_iters 跑"}, "路径或参数名"),                  # 一行：不带参数名
    ({"does": "带 --from design/<n> 进来"}, "CLI 参数"),            # 详情：不写命令行
    ({"stops": "被杀了就续命"}, "「续命」"),                          # 详情：不口语
    ({"leaves": "留一颗文件"}, "「一颗」"),                           # 详情：不用借来的量词
])
def test_descriptor_copy_rules_are_machine_checked(kw, message):
    """P-21：名不超过八字且是词表里的话，一行三十字内不带路径与参数名，详情不写 CLI 参数与口语。"""
    with pytest.raises(AssertionError, match=message):
        C("cap", **kw)


def test_latin_proper_names_count_as_one_word():
    """AutoResearch 是一个词不是十二个字：方法有公认名字的原样写（P-21）。"""
    assert C("cap", title="AutoResearch").title == "AutoResearch"
    assert C("cap", title="AutoResearch 一二三四五六七").title  # 1 + 7 = 8，刚好
    with pytest.raises(AssertionError, match="title 超过"):
        C("cap", title="AutoResearch 一二三四五六七八")


def test_param_label_is_required_short_and_clean():
    with pytest.raises(AssertionError, match="label"):
        Param("k", "int", 1, "h", " ")
    with pytest.raises(AssertionError, match="label 超过"):
        Param("k", "int", 1, "h", "一二三四五六七八九")
    with pytest.raises(AssertionError, match="「在跑」"):
        Param("k", "int", 1, "h", "在跑的轮数")
    with pytest.raises(AssertionError, match="CLI 参数"):
        Param("k", "int", 1, "同 --max-iters", "轮数")
    assert Param("max_iters", "int", None, "本次最多跑几轮", "本次轮数").label == "本次轮数"


def test_every_shipped_capability_sits_in_a_stage_with_all_columns_filled():
    stages = {name: module.DESCRIPTOR.stage for name, module in discover().items()}
    assert stages == {"design": "设计", "reproduction": "设计", "auto-research": "实验",
                      "analysis": "分析", "reproducibility": "分析", "verify": "验证"}
    for module in discover().values():
        d = module.DESCRIPTOR
        assert d.title and d.brief
        assert all(p.label for p in d.params)
        doc = d.to_dict()
        assert doc["brief"] == d.brief
        assert [p["label"] for p in doc["params"]] == [p.label for p in d.params]
        assert doc["stage"] in STAGE_NAMES and doc["stage_slug"] == slug_of(d.stage)
        for key, _ in COLUMNS:
            assert len(getattr(d, key)) > 20, f"{d.name}.{key} 太短，五栏要讲机制"


def test_stage_table_maps_both_ways():
    assert len(STAGE_NAMES) == 7 and len(set(STAGE_SLUGS)) == 7
    for name, slug in zip(STAGE_NAMES, STAGE_SLUGS, strict=True):
        assert slug_of(name) == slug and name_of(slug) == name
        assert slug.isascii() and slug.islower()
    with pytest.raises(AssertionError):
        slug_of("调参")


def test_param_in_flow_defaults_true_and_invocation_only_ones_are_marked():
    assert Param("k", "int", 1, "h", "k").in_flow is True
    catalog = {name: module.DESCRIPTOR for name, module in discover().items()}
    by = {(c, p.name): p.in_flow for c in catalog for p in catalog[c].params}
    assert by[("auto-research", "resume")] is False and by[("auto-research", "reason")] is False
    assert by[("auto-research", "max_iters")] is True
    assert by[("design", "feedback")] is False and by[("design", "domain")] is True
    assert by[("verify", "tolerance")] is True


def test_param_rejects_unknown_type_and_bad_name():
    with pytest.raises(AssertionError, match="类型"):
        Param("k", "list", [], "h", "k")
    with pytest.raises(AssertionError, match="标识符"):
        Param("max-iters", "int", 1, "h", "k")


def test_ports_default_to_nothing():
    assert Ports() == Ports(runner=None, compute=None)


def test_inputs_pick_by_stage_and_demand_exactly_one():
    inputs = Inputs(Path("/ws"), (Path("/ws/design/1"), Path("/ws/experiment/2")),
                    ("design/1", "experiment/2"))
    assert inputs.of_stage("design") == [Path("/ws/design/1")]
    assert inputs.one_of("experiment", "验证") == Path("/ws/experiment/2")
    with pytest.raises(CapabilityFailed, match="要且只要一个「analysis」"):
        inputs.one_of("analysis", "验证")
