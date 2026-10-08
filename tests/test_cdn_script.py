"""发版往 CDN 传包（`.github/scripts/cdn.py`，外层 #277 #281）：1.8.0 的流水线在美国的 runner 上往
上海的桶分片上传，有分片失败就整个放弃（SDK 说「please upload_file again」）。这里用假 client 证明：
失败了照 SDK 的说法再调、试够了照样抛；带版本号的（不可变）桶里已有、大小一样就跳过，
重跑只补没传成的。
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / ".github" / "scripts" / "cdn.py"


def _cdn():
    spec = importlib.util.spec_from_file_location("cdn_script", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class Flaky(Exception):
    """SDK 的 CosClientError 的替身。"""


class FakeClient:
    def __init__(self, fail_times: int = 0, there: dict[str, int] | None = None):
        self.fail_times, self.there, self.calls = fail_times, dict(there or {}), []

    def object_exists(self, Bucket, Key):  # noqa: N803  SDK 的参数名
        return Key in self.there

    def head_object(self, Bucket, Key):  # noqa: N803
        return {"Content-Length": str(self.there[Key])}

    def upload_file(self, Bucket, Key, LocalFilePath, **_):  # noqa: N803
        self.calls.append(Key)
        if self.fail_times:
            self.fail_times -= 1
            raise Flaky("some upload_part fail after max_retry, please upload_file again")
        self.there[Key] = Path(LocalFilePath).stat().st_size


@pytest.fixture
def cdn(monkeypatch):
    module = _cdn()
    monkeypatch.setattr(module, "UPLOAD_WAIT_S", 0)
    return module


def _item(tmp_path: Path, name: str, cache: str, size: int = 10) -> tuple[str, Path, str]:
    path = tmp_path / name
    path.write_bytes(b"x" * size)
    return (f"ai4science/dist/1.8.0/{name}", path, cache)


def test_a_failed_upload_is_tried_again(cdn, tmp_path):
    client = FakeClient(fail_times=2)
    item = _item(tmp_path, "ai4sci.whl", cdn.IMMUTABLE)
    cdn.upload([item], client, retryable=(Flaky,))
    assert client.calls == [item[0]] * 3 and item[0] in client.there


def test_it_gives_up_after_the_last_try(cdn, tmp_path):
    client = FakeClient(fail_times=cdn.UPLOAD_TRIES)
    with pytest.raises(Flaky):
        cdn.upload([_item(tmp_path, "ai4sci.whl", cdn.IMMUTABLE)], client, retryable=(Flaky,))
    assert len(client.calls) == cdn.UPLOAD_TRIES


def test_immutable_objects_already_there_are_skipped_but_latest_ones_are_not(cdn, tmp_path):
    whl = _item(tmp_path, "ai4sci.whl", cdn.IMMUTABLE)
    half = _item(tmp_path, "uv.zip", cdn.IMMUTABLE, size=20)
    latest = _item(tmp_path, "install.sh", cdn.LATEST)
    client = FakeClient(there={whl[0]: 10, half[0]: 7, latest[0]: 10})  # uv.zip 大小不对：重传
    cdn.upload([whl, half, latest], client, retryable=(Flaky,))
    assert client.calls == [half[0], latest[0]]
