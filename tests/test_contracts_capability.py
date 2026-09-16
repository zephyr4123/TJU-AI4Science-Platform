"""能力描述符与发现：每个能力都得说清自己吃什么吐什么，入口签名与描述符对得上（P-12）。

`discover()` 里的断言是生产路径上的机器判据，这里既证明它对真能力放行，也证明它抓得住
各种对不上的假模块——一个永远放行的检查器比没有检查器更坏。
"""

from __future__ import annotations

import json
from types import ModuleType

import pytest

from framework.capabilities import check_capability_module, discover
from framework.contracts.capability import Artifact, Capability, Param, Ports

OUT = (Artifact("x", "x/", "产物"),)


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
    (Capability("other", "run", "s", (), OUT), lambda run_dir, ports: "", "必须等于子包名"),
    (Capability("cap", "run", "s", (), OUT), None, "没有导出 run"),
    (Capability("cap", "run", "s", (), OUT), lambda ports, run_dir: "", "前两个参数"),
    (Capability("cap", "run", "s", (), OUT, params=(Param("k", "int", 1, "h"),)),
     lambda run_dir, ports: "", "对不上"),
    (Capability("cap", "run", "s", (), OUT), lambda run_dir, ports, *, k=1: "", "对不上"),
    (Capability("cap", "run", "s", (), OUT), lambda run_dir, ports, extra: "", "只许关键字参数"),
    # task 级的第一个参数叫 task_dir：名字说明它动的是哪种目录
    (Capability("cap", "task", "s", (), OUT), lambda run_dir, ports: "", "前两个参数"),
    (Capability("cap", "project", "s", (), OUT), lambda project_dir, ports: "", "还没有入口约定"),
])
def test_check_rejects_modules_that_do_not_match(descriptor, entry, message):
    with pytest.raises(AssertionError, match=message):
        check_capability_module("cap", _module("cap", descriptor, entry))


def test_check_accepts_a_matching_module():
    descriptor = Capability("cap", "run", "s", (), OUT, params=(Param("k", "int", 1, "h"),))
    module = _module("cap", descriptor, lambda run_dir, ports, *, k=1: "ok")
    assert check_capability_module("cap", module) is descriptor


def test_descriptor_rejects_bad_level_missing_outputs_and_duplicate_params():
    with pytest.raises(AssertionError, match="level"):
        Capability("cap", "galaxy", "s", (), OUT)
    with pytest.raises(AssertionError, match="产物"):
        Capability("cap", "run", "s", (), ())
    with pytest.raises(AssertionError, match="重复"):
        Capability("cap", "run", "s", (), OUT, params=(Param("k", "int", 1, "h"),) * 2)


def test_param_rejects_unknown_type_and_bad_name():
    with pytest.raises(AssertionError, match="类型"):
        Param("k", "list", [], "h")
    with pytest.raises(AssertionError, match="标识符"):
        Param("max-iters", "int", 1, "h")


def test_ports_default_to_nothing():
    assert Ports() == Ports(runner=None, compute=None)
