"""能力描述符与发现：每个能力都得说清自己吃什么吐什么，入口签名与描述符对得上（P-12）。

`discover()` 里的断言是生产路径上的机器判据，这里既证明它对真能力放行，也证明它抓得住
各种对不上的假模块——一个永远放行的检查器比没有检查器更坏。
"""

from __future__ import annotations

import json
from types import ModuleType

import pytest

from framework.capabilities import check_capability_module, check_catalog, discover
from framework.contracts.capability import STAGES, Artifact, Capability, Param, Ports

OUT = (Artifact("x", "x/", "产物"),)


def C(name: str, level: str, inputs=(), outputs=OUT, **kw) -> Capability:
    """测试用的最小描述符：阶段与人话字段给定值，只让每个用例关心自己那一处。"""
    return Capability(name, level, "s", inputs, outputs, stage="实验", title="t", what="w", **kw)


def _module(name: str, descriptor: object, entry: object) -> ModuleType:
    module = ModuleType(name)
    if descriptor is not None:
        module.DESCRIPTOR = descriptor
    if entry is not None:
        module.run = entry
    return module


def test_discover_finds_the_five_capabilities_and_all_pass_the_checks():
    found = discover()
    assert {"design", "baseline", "experiment", "analysis", "verify"} <= set(found)
    assert {found[n].DESCRIPTOR.level for n in ("design", "baseline")} == {"task"}
    for name, module in found.items():
        assert module.DESCRIPTOR.name == name
        json.dumps(module.DESCRIPTOR.to_dict(), ensure_ascii=False)  # UI 后端要能直接吃


def test_only_experiment_needs_compute_and_verify_needs_no_executor():
    found = discover()
    assert found["experiment"].DESCRIPTOR.needs_compute is True
    assert found["analysis"].DESCRIPTOR.needs_compute is False
    assert found["verify"].DESCRIPTOR.needs_executor is False


def test_param_names_match_entrypoint_keyword_arguments():
    for name, module in discover().items():
        check_capability_module(name, module)  # 不抛就是一致


@pytest.mark.parametrize("descriptor, entry, message", [
    (None, lambda run_dir, ports: "", "没有导出"),
    (C("other", "run"), lambda run_dir, ports: "", "必须等于子包名"),
    (C("cap", "run"), None, "没有导出 run"),
    (C("cap", "run"), lambda ports, run_dir: "", "前两个参数"),
    (C("cap", "run", params=(Param("k", "int", 1, "h"),)),
     lambda run_dir, ports: "", "对不上"),
    (C("cap", "run"), lambda run_dir, ports, *, k=1: "", "对不上"),
    (C("cap", "run"), lambda run_dir, ports, extra: "", "只许关键字参数"),
    # task 级的第一个参数叫 task_dir：名字说明它动的是哪种目录
    (C("cap", "task"), lambda run_dir, ports: "", "前两个参数"),
    (C("cap", "project"), lambda project_dir, ports: "", "还没有入口约定"),
])
def test_check_rejects_modules_that_do_not_match(descriptor, entry, message):
    with pytest.raises(AssertionError, match=message):
        check_capability_module("cap", _module("cap", descriptor, entry))


def test_check_accepts_a_matching_module():
    descriptor = C("cap", "run", params=(Param("k", "int", 1, "h"),))
    module = _module("cap", descriptor, lambda run_dir, ports, *, k=1: "ok")
    assert check_capability_module("cap", module) is descriptor


def test_descriptor_rejects_bad_level_missing_outputs_and_duplicate_params():
    with pytest.raises(AssertionError, match="level"):
        C("cap", "galaxy")
    with pytest.raises(AssertionError, match="产物"):
        C("cap", "run", outputs=())
    with pytest.raises(AssertionError, match="重复"):
        C("cap", "run", params=(Param("k", "int", 1, "h"),) * 2)


def test_descriptor_needs_a_known_stage_and_human_copy():
    with pytest.raises(AssertionError, match="阶段"):
        Capability("cap", "run", "s", (), OUT, stage="调参", title="t", what="w")
    with pytest.raises(AssertionError, match="title 与 what"):
        Capability("cap", "run", "s", (), OUT, stage="实验", title=" ", what="w")
    with pytest.raises(TypeError):  # 阶段与人话是必填的，不给缺省
        Capability("cap", "run", "s", (), OUT)  # type: ignore[call-arg]


def test_every_shipped_capability_sits_in_a_stage_with_human_copy():
    stages = {name: module.DESCRIPTOR.stage for name, module in discover().items()}
    assert stages == {"init": "设计", "design": "设计", "baseline": "设计", "start": "实验",
                      "experiment": "实验", "analysis": "分析", "verify": "验证"}
    for module in discover().values():
        assert module.DESCRIPTOR.title and module.DESCRIPTOR.what
        assert module.DESCRIPTOR.to_dict()["stage"] in STAGES  # UI 与 show caps 读的就是这个键


def test_catalog_rejects_a_second_producer_and_a_dangling_input():
    a = C("a", "run", outputs=(Artifact("o", "a/out.json", "d"),))
    also_a = C("b", "run", outputs=(Artifact("o", "a/out.json", "d"),))
    with pytest.raises(AssertionError, match="都声明输出 'a/out.json'"):
        check_catalog([a, also_a])
    reader = C("c", "run", inputs=(Artifact("i", "summary.md", "d"),))
    with pytest.raises(AssertionError, match="要 'summary.md'，run 级里没人产出"):
        check_catalog([a, reader])
    # 种子不需要生产者；同级能力的输出算有出处
    ok = C("c", "run", inputs=(Artifact("i", "work/", "d"), Artifact("j", "a/out.json", "d")))
    check_catalog([a, ok])
    # 出处只在同一级别里找：task 级的输出喂不了 run 级的输入
    task_side = C("t", "task", outputs=(Artifact("o", "a/out.json", "d"),))
    with pytest.raises(AssertionError, match="run 级里没人产出"):
        check_catalog([task_side, reader])


def test_shipped_catalog_has_one_producer_per_path_and_no_dangling_input():
    descriptors = [module.DESCRIPTOR for module in discover().values()]  # discover 自己已经查过
    outputs = [(d.level, a.path) for d in descriptors for a in d.outputs]
    assert len(outputs) == len(set(outputs))
    assert "checkpoint.json" not in {a.path for d in descriptors for a in d.outputs}  # run 的种子


def test_param_rejects_unknown_type_and_bad_name():
    with pytest.raises(AssertionError, match="类型"):
        Param("k", "list", [], "h")
    with pytest.raises(AssertionError, match="标识符"):
        Param("max-iters", "int", 1, "h")


def test_ports_default_to_nothing():
    assert Ports() == Ports(runner=None, compute=None)
