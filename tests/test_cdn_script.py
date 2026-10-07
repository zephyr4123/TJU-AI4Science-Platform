"""发版往 CDN 传包（`.github/scripts/cdn.py`，外层 #277 #281 #282）。

1.8.0 的流水线在美国的 runner 上往上海的桶分片上传，有分片失败就整个放弃（SDK 说「please upload_file
again」）。这里用假 client 证明：失败了照 SDK 的说法再调、试够了照样抛；带版本号的（不可变）桶里已有
同一份（sha256）就跳过，重跑只补没传成的，同名不同内容让作业失败；每种文件带对的 Content-Type。
版本从 wheel 文件名取（rc 是 PEP 440 的写法），正式版写 platform.json。
"""

from __future__ import annotations

import hashlib
import importlib.util
import io
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
    """桶的替身：对象键 → (内容, 元数据)。`there` 给的是 1.9.0 以前传的，没有 sha256 元数据。"""

    def __init__(self, fail_times: int = 0, there: dict[str, bytes] | None = None):
        self.fail_times, self.calls, self.reads, self.headers = fail_times, [], [], {}
        self.objects = {key: (body, {}) for key, body in (there or {}).items()}

    def object_exists(self, Bucket, Key):  # noqa: N803  SDK 的参数名
        return Key in self.objects

    def head_object(self, Bucket, Key):  # noqa: N803
        body, meta = self.objects[Key]
        return {"Content-Length": str(len(body)), **meta}

    def get_object(self, Bucket, Key):  # noqa: N803
        self.reads.append(Key)
        return {"Body": FakeBody(self.objects[Key][0])}

    def upload_file(self, Bucket, Key, LocalFilePath, **headers):  # noqa: N803
        self.calls.append(Key)
        if self.fail_times:
            self.fail_times -= 1
            raise Flaky("some upload_part fail after max_retry, please upload_file again")
        self.headers[Key] = headers
        self.objects[Key] = (Path(LocalFilePath).read_bytes(), headers.get("Metadata", {}))


class FakeBody:
    def __init__(self, body: bytes):
        self.body = body

    def get_raw_stream(self):
        return io.BytesIO(self.body)


@pytest.fixture
def cdn(monkeypatch):
    module = _cdn()
    monkeypatch.setattr(module, "UPLOAD_WAIT_S", 0)
    return module


def _item(cdn, where: Path, name: str, cache: str, body: bytes = b"x" * 10, **extra):
    where.mkdir(parents=True, exist_ok=True)
    path = where / name
    path.write_bytes(body)
    return cdn.Item(f"ai4science/dist/1.8.0/{name}", path, cache, **extra)


def test_a_failed_upload_is_tried_again(cdn, tmp_path):
    client = FakeClient(fail_times=2)
    item = _item(cdn, tmp_path, "ai4sci.whl", cdn.IMMUTABLE)
    cdn.upload([item], client, retryable=(Flaky,))
    assert client.calls == [item.key] * 3 and item.key in client.objects


def test_it_gives_up_after_the_last_try(cdn, tmp_path):
    client = FakeClient(fail_times=cdn.UPLOAD_TRIES)
    with pytest.raises(Flaky):
        cdn.upload([_item(cdn, tmp_path, "ai4sci.whl", cdn.IMMUTABLE)], client, retryable=(Flaky,))
    assert len(client.calls) == cdn.UPLOAD_TRIES


def test_a_rerun_skips_immutable_objects_already_there_but_not_the_latest_ones(cdn, tmp_path):
    whl = _item(cdn, tmp_path, "ai4sci.whl", cdn.IMMUTABLE)
    latest = _item(cdn, tmp_path, "install.sh", cdn.LATEST)
    client = FakeClient()
    cdn.upload([whl, latest], client, retryable=(Flaky,))
    cdn.upload([whl, latest], client, retryable=(Flaky,))
    assert client.calls == [whl.key, latest.key, latest.key]


def test_the_same_name_with_other_bytes_fails_the_job(cdn, tmp_path, capsys):
    """重新出的包与桶里那份同名不同内容：以前只比大小（签名永远一样长）就跳过，覆盖了边缘节点也照
    一年的缓存发旧字节，更新器拿新签名验旧包，所有人更新失败（spec §7）。不覆盖，让作业停下。"""
    first = _item(cdn, tmp_path / "first", "AAAI4S.app.tar.gz.sig", cdn.IMMUTABLE, b"A" * 10)
    client = FakeClient()
    cdn.upload([first], client, retryable=(Flaky,))
    rebuilt = _item(cdn, tmp_path / "rebuilt", "AAAI4S.app.tar.gz.sig", cdn.IMMUTABLE, b"B" * 10)
    with pytest.raises(SystemExit):
        cdn.upload([rebuilt], client, retryable=(Flaky,))
    assert client.calls == [first.key] and client.objects[first.key][0] == b"A" * 10
    assert "AAAI4S.app.tar.gz.sig" in capsys.readouterr().err


def test_objects_from_before_the_sha256_metadata_are_judged_by_their_content(cdn, tmp_path):
    """1.9.0 以前传的没有 sha256 元数据：旁边有 .sha256 的读它（uv 的包几十 MB，不从上海取回美国），
    没有的取回来算；内容不同照样失败。"""
    archive = _item(cdn, tmp_path, "uv-x.tar.gz", cdn.IMMUTABLE, b"uv")
    side = _item(cdn, tmp_path, "uv-x.tar.gz.sha256", cdn.IMMUTABLE,
                 f"{hashlib.sha256(b'uv').hexdigest()}  uv-x.tar.gz\n".encode())
    client = FakeClient(there={archive.key: b"uv", side.key: side.path.read_bytes()})
    cdn.upload([archive, side], client, retryable=(Flaky,))
    assert client.calls == [] and archive.key not in client.reads
    stale = FakeClient(there={side.key: b"0" * 64})
    with pytest.raises(SystemExit):
        cdn.upload([side], stale, retryable=(Flaky,))
    assert stale.calls == []


def test_each_kind_of_file_goes_up_with_its_content_type(cdn, tmp_path):
    """浏览器照 Content-Type 决定显示还是存下来：.dmg .exe 以前一律按 text/plain 发（spec §5）。
    固定的下载地址另带 Content-Disposition: attachment。"""
    types = {"AAAI4S_1.9.0_universal.dmg": "application/x-apple-diskimage",
             "AAAI4S_1.9.0_x64-setup.exe": "application/vnd.microsoft.portable-executable",
             "latest.json": "application/json", "AAAI4S.app.tar.gz": "application/gzip",
             "AAAI4S.app.tar.gz.sig": "text/plain; charset=utf-8",
             "install.ps1": "text/plain; charset=utf-8"}
    items = [_item(cdn, tmp_path, name, cdn.IMMUTABLE) for name in types]
    fixed = cdn.Item("ai4science/dist/desktop/AAAI4S.dmg", items[0].path, cdn.LATEST,
                     attachment=True)
    client = FakeClient()
    cdn.upload([*items, fixed], client, retryable=(Flaky,))
    sent = {key.rsplit("/", 1)[1]: headers for key, headers in client.headers.items()}
    assert {name: sent[name]["ContentType"] for name in types} == types
    assert sent["AAAI4S.dmg"]["ContentType"] == "application/x-apple-diskimage"
    assert [name for name, headers in sent.items() if "ContentDisposition" in headers] == [
        "AAAI4S.dmg"]
    assert sent["AAAI4S.dmg"]["ContentDisposition"] == "attachment"


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
