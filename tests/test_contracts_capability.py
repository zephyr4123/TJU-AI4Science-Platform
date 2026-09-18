"""能力描述符与发现：每颗能力都得说清自己属于哪一间、五栏（干什么 / 不干什么 / 要带什么进来 /
留下什么 / 什么时候停）都填了，入口签名与描述符对得上（P-12、P-18）。

`discover()` 里的断言是生产路径上的机器判据，这里既证明它对真能力放行，也证明它抓得住
各种对不上的假模块——一个永远放行的检查器比没有检查器更坏。
"""

from __future__ import annotations

import json
from types import ModuleType

import pytest

from framework.capabilities import check_capability_module, command_name, discover
from framework.contracts.capability import COLUMNS, STAGES, Capability, Param, Ports

FIVE = {"does": "干", "does_not": "不干", "brings": "带", "leaves": "留", "stops": "停"}


def C(name: str, level: str, **kw) -> Capability:
    """测试用的最小描述符：阶段、标题与五栏给定值，只让每个用例关心自己那一处。"""
    return Capability(name, level, **{"stage": "实验", "title": "t", **FIVE, **kw})


def _module(name: str, descriptor: object, entry: object) -> ModuleType:
    module = ModuleType(name)
    if descriptor is not None:
        module.DESCRIPTOR = descriptor
    if entry is not None:
        module.run = entry
    return module


def test_discover_finds_the_five_capabilities_and_all_pass_the_checks():
    found = discover()
    assert set(found) == {"init", "design", "auto-research", "analysis", "verify"}
    assert {found[n].DESCRIPTOR.level for n in ("init", "design", "auto-research")} == {"task"}
    assert {found[n].DESCRIPTOR.level for n in ("analysis", "verify")} == {"run"}
    for name, module in found.items():
        assert module.DESCRIPTOR.name == name
        json.dumps(module.DESCRIPTOR.to_dict(), ensure_ascii=False)  # UI 后端要能直接吃


def test_command_name_turns_underscores_into_hyphens():
    assert command_name("auto_research") == "auto-research"
    assert command_name("verify") == "verify"


def test_who_runs_what():
    found = discover()
    assert found["auto-research"].DESCRIPTOR.needs_compute is True
    assert found["analysis"].DESCRIPTOR.needs_compute is False
    assert found["verify"].DESCRIPTOR.needs_executor is False
    assert found["init"].DESCRIPTOR.needs_executor is False


def test_param_names_match_entrypoint_keyword_arguments():
    for name, module in discover().items():
        check_capability_module(name.replace("-", "_"), module)  # 不抛就是一致


@pytest.mark.parametrize("descriptor, entry, message", [
    (None, lambda run_dir, ports: "", "没有导出"),
    (C("other", "run"), lambda run_dir, ports: "", "必须等于子包名"),
    (C("cap", "run"), None, "没有导出 run"),
    (C("cap", "run"), lambda ports, run_dir: "", "前两个参数"),
    (C("cap", "run", params=(Param("k", "int", 1, "h"),)),
     lambda run_dir, ports: "", "对不上"),
    (C("cap", "run"), lambda run_dir, ports, *, k=1: "", "对不上"),
    (C("cap", "run"), lambda run_dir, ports, extra: "", "只许关键字参数"),
    # task 级的第一个参数叫 workspace：名字说明它动的是哪种目录
    (C("cap", "task"), lambda run_dir, ports: "", "前两个参数"),
    (C("cap", "project"), lambda project_dir, ports: "", "还没有入口约定"),
])
def test_check_rejects_modules_that_do_not_match(descriptor, entry, message):
    with pytest.raises(AssertionError, match=message):
        check_capability_module("cap", _module("cap", descriptor, entry))


def test_check_accepts_a_matching_module_and_maps_hyphens():
    descriptor = C("cap", "run", params=(Param("k", "int", 1, "h"),))
    module = _module("cap", descriptor, lambda run_dir, ports, *, k=1: "ok")
    assert check_capability_module("cap", module) is descriptor
    hyphened = C("auto-thing", "run")
    module = _module("auto_thing", hyphened, lambda run_dir, ports: "ok")
    assert check_capability_module("auto_thing", module) is hyphened


def test_descriptor_rejects_bad_level_stage_and_duplicate_params():
    with pytest.raises(AssertionError, match="level"):
        C("cap", "galaxy")
    with pytest.raises(AssertionError, match="阶段"):
        C("cap", "run", stage="调参")
    with pytest.raises(AssertionError, match="重复"):
        C("cap", "run", params=(Param("k", "int", 1, "h"),) * 2)


@pytest.mark.parametrize("key, label", COLUMNS)
def test_descriptor_needs_all_five_columns(key, label):
    with pytest.raises(AssertionError, match=f"「{label}」空着"):
        C("cap", "run", **{key: "  "})


def test_descriptor_needs_a_title_and_no_defaults_for_the_human_copy():
    with pytest.raises(AssertionError, match="title"):
        C("cap", "run", title=" ")
    with pytest.raises(TypeError):  # 阶段、标题与五栏都是必填的，不给缺省
        Capability("cap", "run")  # type: ignore[call-arg]


def test_every_shipped_capability_sits_in_a_room_with_all_columns_filled():
    stages = {name: module.DESCRIPTOR.stage for name, module in discover().items()}
    assert stages == {"init": "假设", "design": "设计", "auto-research": "实验",
                      "analysis": "分析", "verify": "验证"}
    for module in discover().values():
        d = module.DESCRIPTOR
        assert d.title
        assert d.to_dict()["stage"] in STAGES  # UI 与 show caps 读的就是这个键
        for key, _ in COLUMNS:
            assert len(getattr(d, key)) > 20, f"{d.name}.{key} 太短，五栏要讲机制"


def test_param_rejects_unknown_type_and_bad_name():
    with pytest.raises(AssertionError, match="类型"):
        Param("k", "list", [], "h")
    with pytest.raises(AssertionError, match="标识符"):
        Param("max-iters", "int", 1, "h")


def test_ports_default_to_nothing():
    assert Ports() == Ports(runner=None, compute=None)
