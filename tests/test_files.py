"""状态文件的原子写（`framework/files.py`，外层 #204）：写完才换、权限照旧、出错不动原文件。
边跑边追加的进度（外层 #242）：一行一个事件、带时间，几个线程一起写也不交错。"""

from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

import pytest

from framework.files import append_event, write_atomic


def test_write_atomic_replaces_whole_keeps_mode_and_leaves_no_temp(tmp_path):
    path = tmp_path / "state.json"
    write_atomic(path, '{"v": 1}\n')
    assert path.read_text(encoding="utf-8") == '{"v": 1}\n'
    assert path.stat().st_mode & 0o777 == 0o644  # 不是 mkstemp 的 0600
    path.chmod(0o640)
    write_atomic(path, '{"v": 2}\n')
    assert path.read_text(encoding="utf-8") == '{"v": 2}\n'
    assert path.stat().st_mode & 0o777 == 0o640
    assert [p.name for p in tmp_path.iterdir()] == ["state.json"]


def test_write_atomic_failure_keeps_the_old_file(tmp_path, monkeypatch):
    path = tmp_path / "state.json"
    write_atomic(path, "旧\n")

    def boom(src, dst):
        raise OSError("盘满了")

    monkeypatch.setattr("framework.files.os.replace", boom)
    with pytest.raises(OSError, match="盘满了"):
        write_atomic(path, "新\n")
    assert path.read_text(encoding="utf-8") == "旧\n"
    assert [p.name for p in tmp_path.iterdir()] == ["state.json"]


def test_append_event_adds_one_whole_line_with_the_time(tmp_path):
    path = tmp_path / "progress.jsonl"
    append_event(path, step="seeds")
    append_event(path, step="seeds", done=True, seeds=13, title="中文不转义")
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    assert [{k: v for k, v in r.items() if k != "at"} for r in rows] == [
        {"step": "seeds"}, {"step": "seeds", "done": True, "seeds": 13, "title": "中文不转义"}]
    assert all(datetime.fromisoformat(r["at"]).tzinfo is not None for r in rows)
    assert "中文不转义" in path.read_text(encoding="utf-8")


def test_append_event_from_many_threads_never_interleaves(tmp_path):
    """精读同时开几个会话、下原文同时下几篇，都往同一份进度里写：每行都得完整。"""
    path = tmp_path / "progress.jsonl"
    long = "长" * 5000
    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(lambda i: append_event(path, n=i, text=long), range(200)))
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    assert sorted(r["n"] for r in rows) == list(range(200))
