"""复现性分析（纲领 P-24）：零模型的部分（收集设计那包的东西、组 prompt、判产物形状）用剧本执行层
测全；再让验证能力把它写的数回溯到 baseline/ 与论文值——两颗能力互不 import，共用的只有数据表契约。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from framework.capabilities import reproducibility as cap
from framework.capabilities import verify
from framework.contracts.capability import CapabilityFailed, Inputs, Ports
from framework.experiment import pack as packs
from framework.experiment.report import read_report
from framework.workspace import outputs
from tests.fixtures import packs_factory as pf
from tests.fixtures.scripted_backend import ScriptedRunner

PAPER_VALUE = 0.3


@pytest.fixture
def made(tmp_path) -> pf.Pack:
    """一次跑过基线的原码复现产出：论文值在 scoring 里，上游出处与改动留了档。"""
    scoring = pf.default_scoring()
    scoring["metrics"][0]["attainable"] = PAPER_VALUE
    pack = pf.make_pack(tmp_path, scoring=scoring)
    (pack.pack / packs.UPSTREAM_NAME).write_text(json.dumps(
        {"name": "corebench", "source": "https://github.com/x/corebench", "commit": "abc123"}),
        encoding="utf-8")
    (pack.pack / packs.UPSTREAM_DIFF_NAME).write_text(
        "# code/ 相对上游 corebench 的改动：1 个文件\n--- upstream/train.py\n+++ code/train.py\n"
        "+# 修了路径\n", encoding="utf-8")
    return pack


def _analysis(oid: str = "design/1") -> str:
    return f"""## 结论

用作者的代码原样重跑，主指标论文值 0.3、我们 0.5，高了 66.7%，按需求的容差没对上；
最可能是数据版本不同。

## 数据

| 来源 | 指标 | 值 |
|---|---|---|
| {oid}/scoring | val_mse | 0.3 |
| {oid}/baseline | val_mse | 0.5 |
| {oid}/repeat_43 | val_mse | 0.52 |
| {oid}/sigma | val_mse | 0.02 |

## 方法与环境

作者的代码 commit `abc123`，本机跑了 3 次。

## 偏离与改动

train.py 修了一处路径。

## 容易与困难

一次跑通。

## 证伪与未决

数据版本待核。
"""


def _out(pack: pf.Pack) -> tuple[Path, Inputs]:
    directory, _ = outputs.open_output(pack.workspace, "analysis", title="t", by=cap.NAME,
                                       inputs=["design/1"], params={}, flow=None, step=None,
                                       requirement=1, chat_id=None)
    return directory, Inputs(pack.workspace.root, (pack.pack,), ("design/1",))


def test_writes_the_doc_and_prompt_carries_paper_value_results_upstream_diff_env(made):
    out, inputs = _out(made)
    runner = ScriptedRunner([{"analysis.md": _analysis()}])
    line = cap.run(out, inputs, Ports(runner=runner))
    assert line.startswith("reproducibility ok\tclaims=4\tcost_usd=0.0100\tpath=analysis.md")
    assert "verify --from analysis/1 --from design/1" in line
    prompt = runner.prompts[0]
    for token in ("论文值 **0.3**", "design/1/scoring：val_mse = 0.3（论文值）",
                  "design/1/baseline：val_mse = 0.5", "design/1/repeat_43：val_mse = 0.52",
                  "design/1/sigma：val_mse = 0.02", "commit `abc123`", "修了路径",
                  "- Python：`", "没有材料清单", "复现到了哪一级"):
        assert token in prompt, token


def test_missing_baseline_or_broken_shape_fails(made):
    out, inputs = _out(made)
    broken = _analysis().replace("## 数据", "## 数字")
    with pytest.raises(CapabilityFailed, match="缺少小节 ## 数据"):
        cap.run(out, inputs, Ports(runner=ScriptedRunner([{"analysis.md": broken}])))
    import shutil

    shutil.rmtree(made.pack / "baseline")
    with pytest.raises(CapabilityFailed, match="还没有跑出 baseline/"):
        cap.run(out, inputs, Ports(runner=ScriptedRunner([{"analysis.md": _analysis()}])))


def test_verify_traces_the_numbers_back_to_the_design_pack(made):
    """验证能力对复现性分析：来源是设计那包的基线 / 重复 / 论文值 / σ，编一个数就 FAIL。"""
    out, inputs = _out(made)
    cap.run(out, inputs, Ports(runner=ScriptedRunner([{"analysis.md": _analysis()}])))
    ver, _ = outputs.open_output(made.workspace, "verification", title="t", by="verify",
                                 inputs=["analysis/1", "design/1"], params={}, flow=None,
                                 step=None, requirement=1, chat_id=None)
    vin = Inputs(made.workspace.root, (out, made.pack), ("analysis/1", "design/1"))
    line = verify.run(ver, vin, Ports())
    assert line.startswith("verify PASS\tchecks=3\t")
    report = read_report(ver / "report.json")
    assert [c["name"] for c in report["checks"]] == [
        "analysis_present", "numbers_traceable", "prose_numbers_in_table"]
    # 编一个数：论文值写成 0.31
    (out / "analysis.md").write_text(_analysis().replace("| design/1/scoring | val_mse | 0.3 |",
                                                         "| design/1/scoring | val_mse | 0.31 |"),
                                     encoding="utf-8")
    ver2, _ = outputs.open_output(made.workspace, "verification", title="t", by="verify",
                                  inputs=["analysis/1", "design/1"], params={}, flow=None,
                                  step=None, requirement=1, chat_id=None)
    with pytest.raises(CapabilityFailed, match="verify FAIL.*numbers_traceable"):
        verify.run(ver2, vin, Ports())
    assert read_report(ver2 / "report.json")["status"] == "FAIL"
