"""看板读盘：工作区一整份（需求、七个阶段的产出、每条流的进度、作业）、一次产出的细节、需求模板；
NaN 出门前换 None。纯读盘、零模型（P-19：只读框架认的东西）。"""

from __future__ import annotations

import json
import math

import pytest

from framework import paths
from framework.chat import boards
from framework.contracts import output, requirement, workflows
from framework.workspace import outputs, progress
from tests.fixtures import packs_factory as pf
from tests.fixtures import runs_factory as rf

FLOW = """\
name: quick
title: 快看
summary: 设计签过再实验，实验完看一眼。
stages:
  - 设计
  - 断点: 核对评分脚本
  - 实验: {auto-research: {max_iters: 2}}
  - 断点: 看一眼
  - 分析
"""


def catalog():
    from framework.capabilities import discover
    return {name: module.DESCRIPTOR for name, module in discover().items()}


def test_workspace_summary_and_detail(tmp_path):
    ws = pf.make_workspace(tmp_path, "w", confirmed=False)
    summary = boards.workspace_summary(ws)
    assert summary["id"] == "w" and summary["title"] == "夹具课题"
    assert summary["requirement"]["confirmed"] is False and summary["running"] == 0
    assert summary["counts"] == {s: 0 for s in ("literature", "hypothesis", "design", "experiment",
                                                "analysis", "writing", "verification")}
    detail = boards.workspace_detail(ws, catalog())
    assert [s["slug"] for s in detail["stages"]][:2] == ["literature", "hypothesis"]
    assert all(s["outputs"] == [] for s in detail["stages"])
    assert detail["flows"] == [] and detail["jobs"] == []
    req = detail["requirement"]
    assert req["title"] == "夹具课题"
    assert [s["heading"] for s in req["sections"]] == ["问题", "怎么算好"]
    assert req["pending"] is False and req["confirmed_text"] is None
    json.dumps(boards.jsonable(detail), allow_nan=False)


def test_requirement_detail_carries_diff_base_and_pending(tmp_path):
    ws = pf.make_workspace(tmp_path, "w")
    ws.requirement.write_text(pf.REQUIREMENT + "\n## 预算\n\n待填\n", encoding="utf-8")
    req = boards.requirement_detail(ws)
    assert req["confirmed"] and req["dirty"] and req["pending"]
    assert req["sections"][-1] == {"heading": "预算", "body": "待填", "pending": True}
    assert req["confirmed_text"] == pf.REQUIREMENT  # 页面拿它和现文件做 diff


def test_stages_list_outputs_with_signature_and_flows_carry_progress(tmp_path):
    pack = pf.make_pack(tmp_path)
    ws = pack.workspace
    (ws.flows / "quick.yaml").write_text(FLOW, encoding="utf-8")
    # 把设计产出记到流的第 0 项下，签字；实验在第 2 项下
    _, meta = outputs.find_output(ws, "design/1")
    meta.flow, meta.step = "quick", 0
    output.write_meta(pack.pack, meta)
    detail = boards.workspace_detail(ws, catalog())
    design = next(s for s in detail["stages"] if s["slug"] == "design")
    assert [o["id"] for o in design["outputs"]] == ["design/1"]
    assert design["outputs"][0]["signed"] is None and design["outputs"][0]["status"] == "ok"
    [flow] = detail["flows"]
    assert flow["name"] == "quick" and flow["problems"] == [] and flow["step"] == 0
    assert flow["waiting"] == progress.WAITING_SIGN  # 设计完了要签
    assert flow["items"][0]["outputs"][0]["id"] == "design/1"
    assert flow["items"][1]["signed"] is False
    output.sign(pack.pack, by="me")
    detail = boards.workspace_detail(ws, catalog())
    [flow] = detail["flows"]
    assert flow["waiting"] == progress.WAITING_ASSISTANT and flow["items"][1]["signed"] is True
    e1, me = outputs.open_output(ws, "experiment", title="t", by="auto-research",
                                 inputs=["design/1"], params={}, flow="quick", step=2,
                                 requirement=1, chat_id=None)
    outputs.close_output(e1, me, ok=True, line="stop")
    [flow] = boards.workspace_detail(ws, catalog())["flows"]
    assert flow["step"] == 2 and flow["waiting"] == progress.WAITING_SIGN
    # 签了实验，下一项是分析：轮到助理；分析做完就 done
    output.sign(e1, by="me")
    [flow] = boards.workspace_detail(ws, catalog())["flows"]
    assert flow["waiting"] == progress.WAITING_ASSISTANT
    a1, ma = outputs.open_output(ws, "analysis", title="t", by="analysis", inputs=["experiment/1"],
                                 params={}, flow="quick", step=4, requirement=1, chat_id=None)
    outputs.close_output(a1, ma, ok=True, line="ok")
    [flow] = boards.workspace_detail(ws, catalog())["flows"]
    assert flow["waiting"] == progress.DONE


def test_broken_flow_file_is_a_problem_row(tmp_path):
    ws = pf.make_workspace(tmp_path, "w")
    (ws.flows / "zz.yaml").write_text("name: zz\n", encoding="utf-8")
    [flow] = boards.workspace_detail(ws, catalog())["flows"]
    assert flow["name"] == "zz" and flow["problems"] == ["zz.yaml: 缺 title"]
    assert "waiting" not in flow


def test_output_detail_lists_files_with_small_text_inline(tmp_path):
    run_dir, pack = rf.make_run(tmp_path)
    doc = rf.write_analysis(pack, rf.good_analysis(run_dir))
    detail = boards.output_detail(pack.workspace, f"analysis/{doc.name}")
    assert detail["id"] == "analysis/1" and detail["from"] == ["experiment/1"]
    [entry] = detail["files"]
    assert entry["path"] == "analysis.md" and "## 结论" in entry["text"]
    detail = boards.output_detail(pack.workspace, "experiment/1")
    names = [f["path"] for f in detail["files"]]
    assert "ledger.tsv" in names and "checkpoint.json" in names
    assert not any(n.startswith((".venv", "work/.git", "executor")) for n in names)
    with pytest.raises(output.OutputNotFound):
        boards.output_detail(pack.workspace, "analysis/9")


def test_file_view_lists_a_directory_one_level_and_reads_files(tmp_path):
    """文件镜头：目录一层一层给、目录在前、.venv / .git 不列；文本带正文、大的截断、
    二进制 text 为 None。"""
    run_dir, pack = rf.make_run(tmp_path)
    ws = pack.workspace
    (ws.root / "materials" / "big.log").write_bytes(b"x" * (boards.TEXT_LIMIT + 10))
    (ws.root / "materials" / "blob.bin").write_bytes(b"\x00\x01\x02")
    (ws.root / "materials" / "\u6570\u636e.csv").write_text("a,b\n1,2\n", encoding="utf-8")

    top = boards.list_dir(ws, "")
    assert top["path"] == ""
    names = [e["name"] for e in top["entries"]]
    assert "requirement.md" in names and "design" in names and "experiment" in names
    kinds = [e["kind"] for e in top["entries"]]
    assert kinds == sorted(kinds, key=lambda k: k != "dir")  # 目录在前
    inner = boards.list_dir(ws, "experiment/1/")
    inner_names = {e["name"] for e in inner["entries"]}
    assert "ledger.tsv" in inner_names and ".venv" not in inner_names
    assert inner["path"] == "experiment/1"
    work = boards.list_dir(ws, "experiment/1/work")
    assert ".git" not in {e["name"] for e in work["entries"]}

    doc = boards.read_file(ws, "materials/\u6570\u636e.csv")
    assert doc["text"] == "a,b\n1,2\n" and doc["truncated"] is False and doc["size"] == 8
    big = boards.read_file(ws, "materials/big.log")
    assert big["truncated"] is True and len(big["text"]) == boards.TEXT_LIMIT
    blob = boards.read_file(ws, "materials/blob.bin")
    assert blob["text"] is None and blob["truncated"] is False and blob["size"] == 3
    data, ctype = boards.raw_file(ws, "materials/blob.bin")
    assert data == b"\x00\x01\x02" and ctype == "application/octet-stream"

    with pytest.raises(FileNotFoundError):
        boards.list_dir(ws, "nope")
    with pytest.raises(FileNotFoundError):
        boards.read_file(ws, "materials")  # 是目录不是文件


def test_file_view_refuses_paths_outside_the_workspace(tmp_path):
    """绝对路径、`..`、指到外面的符号链接，一律 ValueError；页面上是 422 一句话。"""
    _, pack = rf.make_run(tmp_path)
    ws = pack.workspace
    outside = tmp_path / "secret.txt"
    outside.write_text("x", encoding="utf-8")
    (ws.root / "materials" / "leak").symlink_to(outside)
    for rel in ("/etc/passwd", "../secret.txt", "materials/../../secret.txt", "materials/leak"):
        with pytest.raises(ValueError, match="要在工作区里"):
            boards.resolve_path(ws, rel)
    assert boards.resolve_path(ws, "") == ws.root.resolve()
    assert boards.resolve_path(ws, "materials/./env") == (ws.root / "materials" / "env").resolve()


def test_templates_are_listed_with_title_and_summary():
    found = boards.list_templates(paths.templates_root())
    assert [t["name"] for t in found] == ["ai", "cs", "generic", "materials"]
    generic = next(t for t in found if t["name"] == "generic")
    assert generic["title"] == "课题标题" and generic["summary"].startswith("通用模板")
    assert requirement.PLACEHOLDER in generic["text"]


def test_jsonable_turns_nan_into_null():
    doc = boards.jsonable({"a": math.nan, "b": [1.5, math.inf], "c": {"d": "x"}})
    assert doc == {"a": None, "b": [1.5, None], "c": {"d": "x"}}
    json.dumps(doc, allow_nan=False)


def test_workflow_helpers_used_by_the_board():
    wf = workflows.parse_workflow("quick.yaml", __import__("yaml").safe_load(FLOW))
    assert workflows.stop_after(wf, 0).note == "核对评分脚本"
    assert workflows.stop_after(wf, 4) is None
