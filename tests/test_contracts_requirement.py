"""需求与它的确认（P-19）：文档按二级标题切格、「待填」不能签、确认后再改就是 dirty、
唯一内置的门。"""

from __future__ import annotations

import json

import pytest

from framework.contracts import requirement

DOC = "# 一维回归\n\n引言。\n\n## 问题\n\n把 mse 压到最低。\n\n## 数据\n\n待填\n\n## 预算\n\n"


def _write(root, text=DOC):
    requirement.path(root).write_text(text, encoding="utf-8")


def test_title_and_sections_come_from_the_headings(tmp_path):
    assert requirement.title(DOC, "ws") == "一维回归"
    assert requirement.title("no heading", "ws") == "ws"
    sections = requirement.sections(DOC)
    assert [s.heading for s in sections] == ["问题", "数据", "预算"]
    assert [s.pending for s in sections] == [False, True, True]  # 待填 与空格都是 pending
    assert sections[0].body == "把 mse 压到最低。"


def test_status_before_and_after_confirm_and_dirty_after_edit(tmp_path):
    _write(tmp_path, "# t\n\n## 问题\n\n有。\n")
    assert requirement.status(tmp_path) == {"confirmed": False, "version": None, "by": None,
                                            "at": None, "dirty": False}
    with pytest.raises(requirement.NotConfirmed, match="还没确认"):
        requirement.require_confirmed(tmp_path)
    record = requirement.confirm(tmp_path, by="zephyr")
    assert record["version"] == 1 and record["by"] == "zephyr"
    archived = (requirement.history_dir(tmp_path) / "v1.md").read_text(encoding="utf-8")
    assert archived == "# t\n\n## 问题\n\n有。\n"
    lock = json.loads(requirement.lock_path(tmp_path).read_text(encoding="utf-8"))
    assert lock["sha256"] == record["sha256"]
    assert requirement.require_confirmed(tmp_path) == 1
    state = requirement.status(tmp_path)
    assert state["confirmed"] and state["version"] == 1 and not state["dirty"]
    # 改了：dirty，门关上，diff 的底本是 v1
    _write(tmp_path, "# t\n\n## 问题\n\n改了。\n")
    assert requirement.status(tmp_path)["dirty"] is True
    with pytest.raises(requirement.NotConfirmed, match="又改过"):
        requirement.require_confirmed(tmp_path)
    assert requirement.confirmed_text(tmp_path) == "# t\n\n## 问题\n\n有。\n"
    # 再确认成 v2
    assert requirement.confirm(tmp_path, by="zephyr")["version"] == 2
    assert requirement.require_confirmed(tmp_path) == 2
    assert (requirement.history_dir(tmp_path) / "v2.md").is_file()


def test_confirm_refuses_placeholders_empty_unsigned_and_unchanged(tmp_path):
    with pytest.raises(requirement.ConfirmRefused, match="没有 requirement.md"):
        requirement.confirm(tmp_path, by="me")
    _write(tmp_path, "  \n")
    with pytest.raises(requirement.ConfirmRefused, match="是空的"):
        requirement.confirm(tmp_path, by="me")
    _write(tmp_path)
    with pytest.raises(requirement.ConfirmRefused, match="待填.*数据, 预算"):
        requirement.confirm(tmp_path, by="me")
    # 只看格子：模板引言那句「把每一格的「待填」换成实话」带这个词，照抄了也不算没填
    # （Codex 演练里助理照抄了引言，整份被拒）；一个二级标题都没有的也不能签
    _write(tmp_path, "# t\n\n> 把每一格的「待填」换成实话。\n\n## 问题\n\n有。\n")
    requirement.confirm(tmp_path, by="me")
    _write(tmp_path, "# t\n\n只有一段话，没分格。\n")
    with pytest.raises(requirement.ConfirmRefused, match="没有一个二级标题"):
        requirement.confirm(tmp_path, by="me")
    _write(tmp_path, "# t\n\n## 问题\n\n有。\n")
    with pytest.raises(requirement.ConfirmRefused, match="署名"):
        requirement.confirm(tmp_path, by="  ")
    requirement.confirm(tmp_path, by="me")
    with pytest.raises(requirement.ConfirmRefused, match="内容没变"):
        requirement.confirm(tmp_path, by="me")


def test_a_broken_lock_is_reported_not_ignored(tmp_path):
    _write(tmp_path)
    requirement.lock_path(tmp_path).write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError, match="不是一份确认记录"):
        requirement.status(tmp_path)
