"""发版往 CDN 传包（`.github/scripts/cdn.py`，外层 #277 #281）：1.8.0 的流水线在美国的 runner 上往
上海的桶分片上传，有分片失败就整个放弃（SDK 说「please upload_file again」）。这里用假 client 证明：
失败了照 SDK 的说法再调、试够了照样抛；带版本号的（不可变）桶里已有、大小一样就跳过，
重跑只补没传成的。
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

import pytest

from framework import desktop

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


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _fake_github(url: str, dest: Path) -> Path:
    """uv 的发布包与它的 .sha256：不连 GitHub，两样对得上。"""
    name = url.rsplit("/", 1)[1]
    archive = name.removesuffix(".sha256").encode()
    if name.endswith(".sha256"):
        dest.write_text(f"{hashlib.sha256(archive).hexdigest()}  {name}\n", encoding="utf-8")
    else:
        dest.write_bytes(archive)
    return dest


@pytest.fixture
def packaged(cdn, monkeypatch, tmp_path):
    """make package 出的包放进 tmp 的 dist/、uv 的发布包不连网；返回「放一个这个版本的 wheel」。"""
    dist = tmp_path / "dist"
    dist.mkdir()
    monkeypatch.setattr(cdn, "PACKAGES", dist)
    monkeypatch.setattr(cdn, "fetch", _fake_github)

    def put(version: str) -> Path:
        wheel = dist / f"ai4sci-{version}-py3-none-any.whl"
        wheel.write_bytes(f"wheel {version}".encode())
        side = dist / f"{wheel.name}.sha256"
        side.write_text(f"{_sha(wheel)}  {wheel.name}\n", encoding="utf-8")
        return wheel

    return put


def test_an_rc_takes_its_version_from_the_wheel_and_leaves_the_latest_ones_alone(
        cdn, packaged, capsys):
    """tag 是 SemVer（v1.9.0-rc.1），setuptools-scm 出的 wheel 是 PEP 440 的 1.9.0rc1：以前照
    tag 拼 wheel 名，rc 一跑就停（spec §3 §11）。目录与安装脚本都用 wheel 的写法；预发布不碰最新的
    那几份。"""
    packaged("1.9.0rc1")
    assert cdn.main(["wheel", "v1.9.0-rc.1", "--dry-run"]) == 0
    keys = {line.split("\t")[0].removeprefix(f"{cdn.CDN}/")
            for line in capsys.readouterr().out.splitlines()}
    assert {"ai4science/dist/1.9.0rc1/ai4sci-1.9.0rc1-py3-none-any.whl",
            "ai4science/dist/1.9.0rc1/install.sh", "ai4science/dist/1.9.0rc1/install.ps1"} <= keys
    latest = {f"ai4science/dist/{name}" for name in
              ("install.sh", "install.ps1", "platform.json", "platform.json.sig")}
    assert not keys & latest


def test_a_wheel_that_is_not_the_tag_is_refused(cdn, packaged, capsys):
    """package.sh 只警告：HEAD 不在 tag 上出的是快照（.devN），不能当这一版传上去。"""
    packaged("1.9.1.dev3+g1234567")
    with pytest.raises(SystemExit):
        cdn.main(["wheel", "v1.9.0", "--dry-run"])
    assert "1.9.1.dev3" in capsys.readouterr().err


def test_an_official_release_writes_a_platform_json_with_what_the_shell_checks(
        cdn, packaged, tmp_path):
    """外壳只认签名的 platform.json（spec §3）：版本、后端要求的最低外壳版本、两份带版本号的安装
    脚本（传上去的那几个字节）与 wheel 的 sha256。它和签名排在最后：前面的都传完，外壳才看得到
    新版本。"""
    wheel = packaged("1.9.0")
    work = tmp_path / "work"
    work.mkdir()

    def sign(path: Path) -> Path:
        sig = path.with_name(path.name + ".sig")
        sig.write_text("签名", encoding="utf-8")
        return sig

    items = cdn.plan("1.9.0", "ai4science/dist", work, sign=sign)
    by_key = {item.key: item for item in items}
    pinned = {name: by_key[f"ai4science/dist/1.9.0/{name}"].path
              for name in ("install.sh", "install.ps1")}
    manifest = json.loads(by_key["ai4science/dist/platform.json"].path.read_text(encoding="utf-8"))
    hashes = {"install.sh": _sha(pinned["install.sh"]), "install.ps1": _sha(pinned["install.ps1"]),
              "wheel": _sha(wheel)}
    assert manifest == {"version": "1.9.0", "min_desktop": desktop.MIN_DESKTOP, "sha256": hashes}
    for name, path in pinned.items():
        assert "__VERSION__" not in path.read_text(encoding="utf-8"), name
        assert by_key[f"ai4science/dist/{name}"].path == path  # 最新的那份就是这一版的
    assert [(i.key, i.cache) for i in items[-2:]] == [
        ("ai4science/dist/platform.json", cdn.LATEST),
        ("ai4science/dist/platform.json.sig", cdn.LATEST)]
