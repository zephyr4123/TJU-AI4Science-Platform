"""状态文件的原子写（`framework/files.py`，外层 #204）：写完才换、权限照旧、出错不动原文件。"""

from __future__ import annotations

import pytest

from framework.files import write_atomic


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
