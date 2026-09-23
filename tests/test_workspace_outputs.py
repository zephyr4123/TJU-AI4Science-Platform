"""产出目录的建、找、列与冻结（P-19）：序号只增不复用；被引用或被签的产出改了就拒读；没成的不能当输入。"""

from __future__ import annotations

import pytest

from framework.contracts import output
from framework.workspace import outputs
from tests.fixtures import spaces


def _ws(tmp_path):
    ws = spaces.make_workspace(tmp_path, "w")
    return ws


def _open(ws, slug, inputs=(), **kw):
    fields = {"title": "t", "by": "assistant", "inputs": list(inputs), "params": {},
              "flow": None, "step": None, "requirement": 1, "chat_id": None, **kw}
    return outputs.open_output(ws, slug, **fields)


def test_numbers_grow_and_never_reuse_and_failures_stay_on_disk(tmp_path):
    ws = _ws(tmp_path)
    d1, m1 = _open(ws, "design")
    assert m1.id == "design/1" and d1 == ws.root / "design" / "1" and m1.status == "running"
    outputs.close_output(d1, m1, ok=False, line="草稿有问题")
    assert output.read_meta(d1).status == "failed" and output.read_meta(d1).error == "草稿有问题"
    d2, m2 = _open(ws, "design")
    assert m2.id == "design/2"
    outputs.close_output(d2, m2, ok=True, line="design ok")
    assert output.read_meta(d2).result == "design ok" and output.read_meta(d2).finished_at
    # 删掉 2 再开：编号接着最大的已有编号，不复用不是硬保证（目录没了就没了），但不会撞上还在的 1
    assert [m.id for _, m in outputs.list_outputs(ws)] == ["design/1", "design/2"]
    assert [m.id for _, m in outputs.list_outputs(ws, "design")] == ["design/1", "design/2"]
    assert outputs.list_outputs(ws, "experiment") == []
    assert outputs.find_output(ws, "design/2")[1].id == "design/2"
    with pytest.raises(output.OutputNotFound, match="没有产出 design/9"):
        outputs.find_output(ws, "design/9")
    with pytest.raises(ValueError, match="<阶段目录>/<序号>"):
        outputs.find_output(ws, "design")


def test_inputs_must_exist_be_ok_and_be_unchanged_since_referenced(tmp_path):
    ws = _ws(tmp_path)
    d1, m1 = _open(ws, "design")
    (d1 / "scoring.yaml").write_text("a: 1\n", encoding="utf-8")
    with pytest.raises(output.OutputChanged, match="没成（running）"):
        outputs.resolve_inputs(ws, ["design/1"])
    outputs.close_output(d1, m1, ok=True, line="ok")
    # 没被引用之前随便改
    (d1 / "scoring.yaml").write_text("a: 2\n", encoding="utf-8")
    assert outputs.referenced_hash(ws, "design/1") is None
    got = outputs.resolve_inputs(ws, ["design/1", "design/1"])
    assert got.ids == ("design/1",) and got.outputs == (d1,) and got.workspace == ws.root
    # 被 experiment/1 引用后冻住：hash 记在 experiment/1 的 meta 里
    e1, me1 = _open(ws, "experiment", inputs=["design/1"])
    assert me1.inputs[0].id == "design/1" and me1.inputs[0].sha256 == output.tree_hash(d1)
    assert outputs.referenced_hash(ws, "design/1") == output.tree_hash(d1)
    outputs.check_frozen(ws, "design/1")  # 没改，过
    (d1 / "scoring.yaml").write_text("a: 3\n", encoding="utf-8")
    with pytest.raises(output.OutputChanged, match="改过了"):
        outputs.resolve_inputs(ws, ["design/1"])
    with pytest.raises(output.OutputChanged):
        outputs.check_frozen(ws, "design/1")


def test_a_signature_also_freezes(tmp_path):
    ws = _ws(tmp_path)
    d1, m1 = _open(ws, "design")
    (d1 / "x").write_text("1", encoding="utf-8")
    outputs.close_output(d1, m1, ok=True, line="ok")
    output.sign(d1, by="me")
    assert outputs.referenced_hash(ws, "design/1") == output.tree_hash(d1)
    (d1 / "x").write_text("2", encoding="utf-8")
    with pytest.raises(output.OutputChanged):
        outputs.resolve_inputs(ws, ["design/1"])


def test_reopen_clears_last_attempt_and_records_this_machine(tmp_path):
    """--continue 接着干：上一次的错、结论、结束时间作废，机器按这次的记（演练里第五次续跑
    还挂着「autodl」与上一次的 make_run0.sh 报错）。"""
    ws = _ws(tmp_path)
    d, m = _open(ws, "design", compute={"name": "autodl", "kind": "ssh"})
    outputs.close_output(d, m, ok=False, line="make_run0.sh 退出码 1")
    outputs.reopen_output(d, m, compute={"name": "local", "kind": "local"})
    again = output.read_meta(d)
    assert again.status == "running" and again.finished_at is None
    assert again.error == "" and again.result == ""
    assert again.compute == {"name": "local", "kind": "local"}
    outputs.close_output(d, m, ok=True, line="基线 3 次")
    assert output.read_meta(d).result == "基线 3 次" and output.read_meta(d).error == ""


def test_sibling_workspace_outputs_are_read_frozen_and_recorded_with_a_prefix(tmp_path):
    """跨工作区（外层 #136）：同一项目里兄弟的产出写 `<工作区>:<stage>/<n>`——找得到、当输入时
    meta 记这个写法、被兄弟读过的也冻住、自己的前缀会去掉；项目外没有这条路。"""
    ws = _ws(tmp_path)
    paper = spaces.make_workspace(tmp_path, "paper")
    d1, m1 = _open(ws, "analysis")
    outputs.close_output(d1, m1, ok=True, line="ok")
    (d1 / "analysis.md").write_text("结论", encoding="utf-8")
    assert output.parse_id("w:analysis/1") == output.OutputId("analysis", 1, "w")
    assert str(output.parse_id("w:analysis/1")) == "w:analysis/1"
    assert output.parse_id("w:analysis/1").local == "analysis/1"
    # 从 paper 看 w 的产出：目录是 w 里的；自己的名字当前缀等于不写
    assert outputs.find_output(paper, "w:analysis/1")[0] == d1
    assert outputs.owner_of(ws, "w:analysis/1")[1] == output.OutputId("analysis", 1)
    with pytest.raises(output.OutputNotFound, match="没有产出 w:analysis/9"):
        outputs.find_output(paper, "w:analysis/9")
    with pytest.raises(output.OutputNotFound, match="项目 p 里没有工作区 'nope'"):
        outputs.find_output(paper, "nope:analysis/1")
    resolved = outputs.resolve_inputs(paper, ["w:analysis/1", "w:analysis/1"])
    assert resolved.ids == ("w:analysis/1",) and resolved.outputs == (d1,)
    assert outputs.resolve_inputs(ws, ["w:analysis/1"]).ids == ("analysis/1",)
    # paper 读了它：meta 记 `from: [w:analysis/1]`，w 那边它就冻住了
    d2, m2 = _open(paper, "writing", inputs=["w:analysis/1"])
    outputs.close_output(d2, m2, ok=True, line="ok")
    assert m2.input_ids == ["w:analysis/1"]
    users = [(o.id, m.id) for o, m in outputs.referencing(ws, "analysis/1")]
    assert users == [("paper", "writing/1")]
    assert outputs.referenced_hash(ws, "analysis/1") == m2.inputs[0].sha256
    assert outputs.referenced_hash(paper, "w:analysis/1") == m2.inputs[0].sha256
    (d1 / "analysis.md").write_text("改了", encoding="utf-8")
    with pytest.raises(output.OutputChanged, match="w:analysis/1 被引用或签字之后改过了"):
        outputs.resolve_inputs(paper, ["w:analysis/1"])
    with pytest.raises(output.OutputChanged, match="analysis/1 被引用或签字之后改过了"):
        outputs.resolve_inputs(ws, ["analysis/1"])
