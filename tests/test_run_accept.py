"""验收记录：三道门、签进去的是 checkpoint 里的 best、验收后 best 变了要看得出来。"""

from __future__ import annotations

import json

import pytest

from framework.run import accept, layout
from framework.run.checkpoint import read_checkpoint, write_checkpoint
from tests.fixtures.runs_factory import make_run


def test_accept_signs_best_and_reads_back(tmp_path):
    run_dir = make_run(tmp_path)
    record = accept.accept_run(run_dir, by=" 张三 ")
    state = read_checkpoint(run_dir)
    assert record["by"] == "张三"
    assert record["best_commit"] == state["best_commit"]
    assert record["best_metric"] == state["best_metric"]
    assert record["verify"] is None  # 没跑验证就没有结论可签，不编一个
    on_disk = json.loads((run_dir / accept.ACCEPT_NAME).read_text(encoding="utf-8"))
    assert on_disk == record
    assert accept.read_acceptance(run_dir) == {**record, "stale": False}


def test_accept_goes_stale_when_best_moves(tmp_path):
    run_dir = make_run(tmp_path)
    accept.accept_run(run_dir, by="张三")
    state = read_checkpoint(run_dir)
    write_checkpoint(run_dir, {**state, "best_commit": "f" * 40, "best_iter": 9})
    assert accept.read_acceptance(run_dir)["stale"] is True


def test_accept_refuses_without_name_or_while_running(tmp_path):
    run_dir = make_run(tmp_path)
    with pytest.raises(accept.AcceptRefused, match="署名"):
        accept.accept_run(run_dir, by="  ")
    layout.inflight(run_dir).write_text("{}", encoding="utf-8")
    with pytest.raises(accept.AcceptRefused, match="正在跑"):
        accept.accept_run(run_dir, by="张三")
    assert not (run_dir / accept.ACCEPT_NAME).exists()


def test_accept_refuses_baseline_only_run(tmp_path):
    run_dir = make_run(tmp_path)
    state = read_checkpoint(run_dir)
    write_checkpoint(run_dir, {**state, "last_iter": 0, "best_iter": 0})
    with pytest.raises(accept.AcceptRefused, match="一轮都没跑"):
        accept.accept_run(run_dir, by="张三")


def test_accept_refuses_broken_verify_report(tmp_path):
    run_dir = make_run(tmp_path)
    report = layout.verify_report(run_dir)
    report.parent.mkdir(parents=True)
    report.write_text('{"status": "MAYBE"}', encoding="utf-8")
    with pytest.raises(accept.AcceptRefused, match="验证报告不合约"):
        accept.accept_run(run_dir, by="张三")


def test_read_acceptance_absent_and_wrong_version(tmp_path):
    run_dir = make_run(tmp_path)
    assert accept.read_acceptance(run_dir) is None
    (run_dir / accept.ACCEPT_NAME).write_text('{"format_version": 99}', encoding="utf-8")
    with pytest.raises(ValueError, match="format_version"):
        accept.read_acceptance(run_dir)
