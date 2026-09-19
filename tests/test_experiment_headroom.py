"""接任务预检：门与空间的算术，判无解就停。门高的算式只有这一处，内环的 gate 也用它。"""

from __future__ import annotations

import pytest

from framework.capabilities.auto_research import gate as loop_gate
from framework.experiment import context, headroom
from tests.fixtures import packs_factory as pf


def pack_with(tmp_path, *, values=pf.DEFAULT_VALUES, attainable=None, direction="minimize",
              **budget):
    scoring = pf.default_scoring()
    scoring["metrics"][0]["direction"] = direction
    if attainable is not None:
        scoring["metrics"][0]["attainable"] = attainable
    scoring["budget"].update(budget)
    return pf.make_pack(tmp_path, scoring=scoring, values=values)


def test_gate_height_is_the_larger_of_sigma_term_and_min_delta():
    assert headroom.gate_height(2.0, 0.02, 0.0) == pytest.approx(0.04)
    assert headroom.gate_height(2.0, 0.0, 0.01) == 0.01
    assert headroom.gate_height(2.0, 0.02, 0.1) == 0.1
    assert headroom.DEFAULT_MIN_DELTA == context.DEFAULT_MIN_DELTA, "预检与内环的缺省要同值"
    assert loop_gate.gate_height is headroom.gate_height, "内环的门必须是同一个函数"


def test_assess_reads_baseline_sigma_and_reports_no_attainable(tmp_path):
    pack = pack_with(tmp_path)
    room = headroom.assess(pack.pack)
    assert (room.metric, room.direction) == ("val_mse", "minimize")
    assert room.baseline == 0.5 and room.sigma == pytest.approx(0.02)
    assert room.gate == pytest.approx(0.04) and room.attainable is None and room.room is None
    assert room.problems() == []
    assert room.summary() == "baseline=0.5\tsigma=0.02\tgate=0.04\tattainable=-"


def test_room_is_direction_aware_and_counted_in_gates(tmp_path):
    room = headroom.assess(pack_with(tmp_path, attainable=0.3).pack)
    assert room.room == pytest.approx(0.2) and "（5.0 个门）" in room.summary()
    assert room.problems() == []
    pack = pack_with(tmp_path / "max", attainable=0.9, direction="maximize")
    room = headroom.assess(pack.pack)
    assert room.room == pytest.approx(0.4) and room.problems() == []


def test_no_room_beyond_the_gate_is_unsolvable(tmp_path):
    room = headroom.assess(pack_with(tmp_path, attainable=0.47).pack)  # 0.03 < 门 0.04
    assert len(room.problems()) == 1 and "无解" in room.problems()[0]
    room = headroom.assess(pack_with(tmp_path / "edge", attainable=0.46).pack)  # 0.04 == 门
    assert "无解" in room.problems()[0]


def test_attainable_better_than_baseline_is_a_data_error(tmp_path):
    room = headroom.assess(pack_with(tmp_path, attainable=0.6).pack)  # minimize：尽头比基线还差
    assert len(room.problems()) == 1 and "填错" in room.problems()[0]


def test_zero_gate_is_a_problem_and_min_delta_fixes_it(tmp_path):
    flat = (0.5, 0.5, 0.5)
    room = headroom.assess(pack_with(tmp_path, values=flat).pack)
    assert room.gate == 0 and "统计门是 0" in room.problems()[0]
    room = headroom.assess(pack_with(tmp_path / "fixed", values=flat, min_delta=0.01).pack)
    assert room.gate == 0.01 and room.problems() == []


def test_assess_names_the_missing_file(tmp_path):
    pack = pack_with(tmp_path)
    (pack.pack / "baseline" / "sigma.json").unlink()
    with pytest.raises(FileNotFoundError, match="sigma.json"):
        headroom.assess(pack.pack)
