"""看板读盘：工作区一行与一整份、任务包的阶段与钥匙、预检、run 的摘要与账本；页面直接显示。"""

from __future__ import annotations

import json
import math
import shutil

import pytest

from framework.chat import boards
from framework.contracts import publish
from framework.run import accept, layout, workspace
from framework.run.checkpoint import read_checkpoint, write_checkpoint
from tests.fixtures.packs_factory import make_pack
from tests.fixtures.runs_factory import make_run


def test_task_stage_walks_the_board(tmp_path):
    pack = make_pack(tmp_path, published=False)
    assert boards.stage(pack.task_dir) == "drafting"
    publish.publish_task(pack.task_dir, by="张三")
    assert boards.stage(pack.task_dir) == "baselined"  # 夹具自带 harness/ code/ run_0/
    shutil.rmtree(pack.task_dir / "run_0")
    assert boards.stage(pack.task_dir) == "designed"
    shutil.rmtree(pack.task_dir / "harness")
    assert boards.stage(pack.task_dir) == "published"


def test_task_summary_and_publish_state(tmp_path):
    pack = make_pack(tmp_path, published=False)
    found = boards.task_summary(pack.task_dir)
    assert found["id"] == "toy" and found["metric"]["name"] == "val_mse"
    assert found["publish"]["ok"] is False and found["publish"]["state"] == "missing"
    assert "还没发布" in found["publish"]["reason"]
    publish.publish_task(pack.task_dir, by="张三")
    found = boards.task_summary(pack.task_dir)
    assert found["publish"] == {"ok": True, "state": "ok", "by": "张三",
                                "at": found["publish"]["at"], "reason": None}
    # 发布后改了签的文件：钥匙失效，原因原样给看板
    (pack.task_dir / "design.md").write_text("改了\n", encoding="utf-8")
    found = boards.task_summary(pack.task_dir)["publish"]
    assert found["state"] == "invalid" and "改过了" in found["reason"]


def test_task_detail_has_design_intake_and_headroom(tmp_path):
    pack = make_pack(tmp_path)
    found = boards.task_detail(pack.task_dir)
    assert found["design"].startswith("code/ 写 predictions.json")
    assert found["intake_problems"] == []
    assert found["headroom"]["metric"] == "val_mse" and found["headroom"]["problems"] == []
    assert found["headroom"]["gates"] is None  # 没写 attainable：没有尽头就没有几个门
    shutil.rmtree(pack.task_dir / "run_0")
    assert boards.task_detail(pack.task_dir)["headroom"] is None


def test_workspace_summary_and_detail(tmp_path):
    """工作区一行：标题、任务包走到哪、几个 run；还没起任务包时 task 是 None。"""
    empty = workspace.create(tmp_path / "workspaces", "fresh", title="刚起的")
    row = boards.workspace_summary(empty)
    assert row["id"] == "fresh" and row["title"] == "刚起的" and row["task"] is None
    assert row["runs"] == 0 and boards.workspace_detail(empty)["runs"] == []
    run_dir = make_run(tmp_path)
    ws = workspace.load(run_dir.parent.parent)
    row = boards.workspace_summary(ws)
    assert row["id"] == "toy" and row["task"]["stage"] == "baselined" and row["runs"] == 1
    detail = boards.workspace_detail(ws)
    assert detail["task"]["design"].startswith("code/ 写") and detail["runs"][0]["run_id"] == "r1"


def test_run_summary_and_detail(tmp_path):
    run_dir = make_run(tmp_path)
    ws = workspace.load(run_dir.parent.parent)
    found = boards.run_summary(ws, run_dir)
    assert found["run_id"] == run_dir.name and found["metric"]["name"] == "val_mse"
    assert found["baseline"] == pytest.approx(0.03) and found["last_iter"] == 3
    assert found["best_metric"] == pytest.approx(0.001)
    assert found["running"] is False and found["verify"] is None and found["accept"] is None
    assert found["chat_id"] is None  # 老 run / 终端里开的：不知道是谁开的
    write_checkpoint(run_dir, {**read_checkpoint(run_dir), "chat_id": "chat-7"})
    assert boards.run_summary(ws, run_dir)["chat_id"] == "chat-7"
    detail = boards.run_detail(ws, run_dir)
    assert [row["status"] for row in detail["ledger"]] == ["keep", "discard", "keep"]
    assert detail["analysis_text"] is None
    accept.accept_run(run_dir, by="张三")
    assert boards.run_summary(ws, run_dir)["accept"]["by"] == "张三"


def test_list_runs_skips_non_run_dirs(tmp_path):
    run_dir = make_run(tmp_path)
    ws = workspace.load(run_dir.parent.parent)
    (ws.runs / "design").mkdir()  # 接任务的执行层日志不是 run
    assert [r["run_id"] for r in boards.list_runs(ws)] == [run_dir.name]
    assert boards.list_runs(workspace.create(tmp_path / "workspaces", "empty")) == []


def test_verify_state_reports_broken_report(tmp_path):
    run_dir = make_run(tmp_path)
    report = layout.verify_report(run_dir)
    report.parent.mkdir(parents=True)
    report.write_text('{"status": "MAYBE"}', encoding="utf-8")
    assert boards.verify_state(run_dir)["status"] == "invalid"


def test_jsonable_turns_nan_into_null():
    payload = {"a": math.nan, "b": [1.0, math.inf, {"c": -math.inf}], "d": "x"}
    assert json.dumps(boards.jsonable(payload), allow_nan=False) == \
        '{"a": null, "b": [1.0, null, {"c": null}], "d": "x"}'
