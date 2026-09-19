"""产出的两份框架文件（P-19）：meta.yaml 记读了谁、成没成；signed.json 是人签的，
目录一改签字就 stale；目录 hash 不算框架自己的文件与环境。"""

from __future__ import annotations

import pytest
import yaml

from framework.contracts import output
from framework.contracts.output import Input, Meta, OutputId, parse_id


def test_id_is_the_path():
    oid = parse_id("experiment/2")
    assert oid == OutputId("experiment", 2) and str(oid) == "experiment/2"
    assert oid.path("/ws").as_posix() == "/ws/experiment/2"
    for bad in ("experiment", "runs/1", "experiment/x", "调参/1", "experiment/1/2"):
        with pytest.raises(ValueError, match="<阶段目录>/<序号>"):
            parse_id(bad)


def test_meta_round_trips_with_from_spelled_as_from(tmp_path):
    meta = Meta(id="analysis/1", stage="analysis", title="分析初稿", by="analysis",
                created_at="2026-09-19T00:00:00+00:00",
                inputs=[Input("experiment/1", "a" * 64), Input("experiment/2", "b" * 64)],
                params={"tolerance": 0.01}, flow="research", step=3, requirement=2, chat_id="c1")
    output.write_meta(tmp_path, meta)
    raw = yaml.safe_load(output.meta_path(tmp_path).read_text(encoding="utf-8"))
    assert raw["from"] == [{"id": "experiment/1", "sha256": "a" * 64},
                           {"id": "experiment/2", "sha256": "b" * 64}]
    assert "inputs" not in raw and raw["status"] == "running"
    back = output.read_meta(tmp_path)
    assert back == meta and back.input_ids == ["experiment/1", "experiment/2"]
    with pytest.raises(AssertionError, match="状态只认"):
        output.write_meta(tmp_path, Meta(**{**meta.__dict__, "status": "lost"}))
    with pytest.raises(output.OutputNotFound):
        output.read_meta(tmp_path / "nope")
    output.meta_path(tmp_path).write_text("id: x\n", encoding="utf-8")
    with pytest.raises(ValueError, match="不是一份产出记录"):
        output.read_meta(tmp_path)


def test_tree_hash_ignores_framework_files_and_environments(tmp_path):
    (tmp_path / "a.txt").write_text("1", encoding="utf-8")
    before = output.tree_hash(tmp_path)
    output.write_meta(tmp_path, Meta(id="x/1", stage="x", title="t", by="b", created_at="c"))
    (tmp_path / ".venv" / "bin").mkdir(parents=True)
    (tmp_path / ".venv" / "bin" / "python").write_text("x", encoding="utf-8")
    (tmp_path / ".git").mkdir()
    (tmp_path / ".git" / "HEAD").write_text("ref", encoding="utf-8")
    output.signed_path(tmp_path).write_text("{}", encoding="utf-8")
    assert output.tree_hash(tmp_path) == before
    (tmp_path / "a.txt").write_text("2", encoding="utf-8")
    assert output.tree_hash(tmp_path) != before


def test_sign_records_the_hash_and_goes_stale_when_the_directory_changes(tmp_path):
    meta = Meta(id="design/1", stage="design", title="t", by="design", created_at="c")
    output.write_meta(tmp_path, meta)
    with pytest.raises(output.SignRefused, match="没成"):
        output.sign(tmp_path, by="me")
    meta.status = "ok"
    output.write_meta(tmp_path, meta)
    (tmp_path / "scoring.yaml").write_text("a: 1\n", encoding="utf-8")
    with pytest.raises(output.SignRefused, match="署名"):
        output.sign(tmp_path, by=" ")
    record = output.sign(tmp_path, by="me", note="看过了")
    assert record["by"] == "me" and record["note"] == "看过了"
    assert output.read_signed(tmp_path)["sha256"] == output.tree_hash(tmp_path)
    assert output.signature_state(tmp_path)["stale"] is False
    with pytest.raises(output.SignRefused, match="已经签过了"):
        output.sign(tmp_path, by="me")
    (tmp_path / "scoring.yaml").write_text("a: 2\n", encoding="utf-8")
    assert output.signature_state(tmp_path)["stale"] is True
    assert output.sign(tmp_path, by="me")["sha256"] != record["sha256"]  # 改了再签是新签字
    output.signed_path(tmp_path).write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError, match="不是一份签字记录"):
        output.read_signed(tmp_path)
    assert output.signature_state(tmp_path / "nowhere") is None
