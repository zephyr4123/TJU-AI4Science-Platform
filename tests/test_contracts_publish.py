"""发布钥匙：签的是内容不是时间戳——签的文件改一个字节钥匙就失效，没签过能力不开。"""

from __future__ import annotations

import json

import pytest

from framework.contracts import publish
from tests.fixtures import packs_factory as pf


def test_publish_signs_manifest_and_brief_and_require_accepts(tmp_path):
    pack = pf.make_pack(tmp_path, published=False)
    record = publish.publish_task(pack.task_dir, by="小王")
    on_disk = json.loads((pack.task_dir / publish.PUBLISH_NAME).read_text(encoding="utf-8"))
    assert on_disk == record
    assert record["by"] == "小王" and set(record["files"]) == {"manifest.yaml", "design.md"}
    assert publish.require_published(pack.task_dir) == record


def test_require_fails_closed_without_a_record(tmp_path):
    pack = pf.make_pack(tmp_path, published=False)
    with pytest.raises(publish.NotPublished, match="还没发布"):
        publish.require_published(pack.task_dir)


@pytest.mark.parametrize("name", ["manifest.yaml", "design.md"])
def test_editing_a_signed_file_after_publish_invalidates_the_key(tmp_path, name):
    pack = pf.make_pack(tmp_path, published=False)
    publish.publish_task(pack.task_dir, by="小王")
    path = pack.task_dir / name
    path.write_text(path.read_text(encoding="utf-8") + "\n# 改了一行\n", encoding="utf-8")
    with pytest.raises(publish.NotPublished, match=f"{name} 改过了"):
        publish.require_published(pack.task_dir)
    publish.publish_task(pack.task_dir, by="小王")  # 重新看过、重新发布，钥匙又对了
    publish.require_published(pack.task_dir)


def test_deleting_a_signed_file_after_publish_invalidates_the_key(tmp_path):
    pack = pf.make_pack(tmp_path, published=False)
    publish.publish_task(pack.task_dir, by="小王")
    (pack.task_dir / "design.md").unlink()
    with pytest.raises(publish.NotPublished, match="design.md 没了"):
        publish.require_published(pack.task_dir)


@pytest.mark.parametrize("text, message", [
    ("not json", "不是合法 JSON"),
    (json.dumps({"format_version": 99, "files": {}}), "format_version"),
    (json.dumps({"format_version": 1}), "缺 files"),
])
def test_broken_records_are_reported_not_trusted(tmp_path, text, message):
    pack = pf.make_pack(tmp_path, published=False)
    (pack.task_dir / publish.PUBLISH_NAME).write_text(text, encoding="utf-8")
    with pytest.raises(publish.NotPublished, match=message):
        publish.require_published(pack.task_dir)


def test_publish_refuses_when_the_intake_is_not_ready(tmp_path):
    pack = pf.make_pack(tmp_path, published=False)
    (pack.task_dir / "design.md").write_text("   \n", encoding="utf-8")
    with pytest.raises(publish.PublishRefused, match="design.md"):
        publish.publish_task(pack.task_dir, by="小王")
    manifest = pf.default_manifest()
    manifest["metrics"] = []
    (pack.task_dir / "manifest.yaml").write_text(pf.to_yaml(manifest), encoding="utf-8")
    (pack.task_dir / "design.md").write_text(pf.BRIEF, encoding="utf-8")
    with pytest.raises(publish.PublishRefused, match="metrics"):
        publish.publish_task(pack.task_dir, by="小王")
    with pytest.raises(publish.PublishRefused, match="署名"):
        publish.publish_task(pack.task_dir, by="  ")
    assert not (pack.task_dir / publish.PUBLISH_NAME).exists()
