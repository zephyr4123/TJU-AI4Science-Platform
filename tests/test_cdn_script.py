"""发版往 CDN 传包（`.github/scripts/cdn.py`，外层 #277 #281 #282）。

1.8.0 的流水线在美国的 runner 上往上海的桶分片上传，有分片失败就整个放弃（SDK 说「please upload_file
again」）。这里用假 client 证明：失败了照 SDK 的说法再调、试够了照样抛；带版本号的（不可变）桶里已有
同一份（sha256）就跳过，重跑只补没传成的，同名不同内容让作业失败；每种文件带对的 Content-Type。
版本从 wheel 文件名取（rc 是 PEP 440 的写法），正式版写 platform.json。

桌面包（spec §7）：签名照外壳的更新器验（用 tauri CLI 签的真签名），latest.json 传之前的校验各有
反例；外壳改没改在一个带 tag 的临时 git 仓里判；CDN 证书的剩余天数注入日期判。桶、CDN 的 HEAD 都是
替身，不连网。
"""

from __future__ import annotations

import base64
import copy
import hashlib
import http.server
import importlib.util
import io
import json
import re
import subprocess
import threading
import urllib.error
from datetime import UTC, datetime
from pathlib import Path

import pytest

from framework import desktop

SCRIPT = Path(__file__).resolve().parents[1] / ".github" / "scripts" / "cdn.py"
# tauri CLI 2.12.1 用一把只为测试生成的 key 签的（`tauri signer sign --app-version 1.9.0`）：
# 证明 cdn.py 验的就是外壳的更新器认的那种签名，不是自己造的格式
TEST_PUBKEY = ("dW50cnVzdGVkIGNvbW1lbnQ6IG1pbmlzaWduIHB1YmxpYyBrZXk6IEUyMEJDMEZCOUJCMEQ5RkYKUldU"
               "LzJiQ2IrOEFMNGh0TFo0SkpTNzFlWjBPYkY1ZXF0SHBnVWFxVjQ0R2xXWHVTei9QUzdMd2oK")
SIGNED = b"AAAI4S 1.9.0 shell bundle\n"
SIGNATURE = ("dW50cnVzdGVkIGNvbW1lbnQ6IHNpZ25hdHVyZSBmcm9tIHRhdXJpIHNlY3JldCBrZXkKUlVULzJiQ2Ir"
             "OEFMNG5CdTVVUEhaaFhTS3lYaGIzSTBqQ2w1K3Vsd2UrdktuUjJkSDZaSWNPTTVkVDUvaVlScWVtTUsz"
             "OExnaVFvbFFvemttdnRQSXZyMmVlbzFpdE5NY2c0PQp0cnVzdGVkIGNvbW1lbnQ6IHRpbWVzdGFtcDox"
             "NzkxMzcxNjk1CWZpbGU6YnVuZGxlLmJpbgl2ZXJzaW9uOjEuOS4wCjNuT1AvaEVEc0JCd1JhajlkbFFl"
             "WldVOHlXTHNTYXZPSWdMOVkreTMxODBMQW1CQ2ZzdmV2cU5hZks5aXgvdnk1SHV2SUFRc0tLVGhTQ1NS"
             "dkJOTUNBPT0K")


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

    def download_file(self, Bucket, Key, DestFilePath):  # noqa: N803
        self.reads.append(Key)
        Path(DestFilePath).write_bytes(self.objects[Key][0])

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
        text = path.read_text(encoding="utf-8")
        assert "__VERSION__" not in text and "__UV_SHA256__" not in text, name
        assert by_key[f"ai4science/dist/{name}"].path == path  # 最新的那份就是这一版的
        # 脚本由签名清单盖着，uv 的发布包靠写在脚本里的 sha256 也进了签名链（外层 #282 审查）
        for archive in cdn.UV_ARCHIVES:
            triple = archive.removesuffix(".tar.gz").removesuffix(".zip")
            uv = by_key[f"ai4science/dist/uv/{cdn.uv_version()}/uv-{archive}"].path
            assert f"{triple}={_sha(uv)}" in text, (name, triple)
    assert [(i.key, i.cache) for i in items[-2:]] == [
        ("ai4science/dist/platform.json", cdn.LATEST),
        ("ai4science/dist/platform.json.sig", cdn.LATEST)]


def test_every_release_has_a_signed_manifest_of_its_own(cdn, packaged, tmp_path):
    """预发布的外壳装它自己那一版：最新的 platform.json 不动（rc），它就照 `<ver>/platform.json` 核
    安装脚本，所以 rc 也要有一份、签过、不可变；不写最新的那份。"""
    packaged("1.9.0rc1")
    work = tmp_path / "work"
    work.mkdir()

    def sign(path: Path) -> Path:
        sig = path.with_name(path.name + ".sig")
        sig.write_text("签名", encoding="utf-8")
        return sig

    by_key = {item.key: item for item in cdn.plan("1.9.0rc1", "ai4science/dist", work, sign=sign)}
    for name in ("platform.json", "platform.json.sig"):
        assert by_key[f"ai4science/dist/1.9.0rc1/{name}"].cache == cdn.IMMUTABLE
        assert f"ai4science/dist/{name}" not in by_key
    manifest = json.loads(by_key["ai4science/dist/1.9.0rc1/platform.json"].path.read_text(
        encoding="utf-8"))
    assert manifest["version"] == "1.9.0rc1"
    assert manifest["sha256"]["install.sh"] == _sha(
        by_key["ai4science/dist/1.9.0rc1/install.sh"].path)


def test_a_signature_from_the_tauri_cli_verifies_like_the_updater_does(cdn):
    trusted = cdn.verify(SIGNED, SIGNATURE, TEST_PUBKEY)
    assert cdn.signed_version(trusted) == "1.9.0"


def _edited(signature: str, old: str, new: str) -> str:
    text = base64.b64decode(signature).decode().replace(old, new)
    return base64.b64encode(text.encode()).decode()


def test_a_signature_does_not_verify_other_bytes_an_edited_comment_or_another_key(cdn, capsys):
    """更新器拿 latest.json 里的签名验下到的包、外壳拿内置的公钥验 platform.json：这几样验不过的
    都得在发版时就拦下，不然已装的外壳全部更新失败。trusted comment 里的版本也在全局签名底下，
    改不得；签名后面多一个换行，更新器的 base64 不认。"""
    key_line = base64.b64decode(TEST_PUBKEY).decode().splitlines()[1]
    other_id = base64.b64encode(b"Ed" + b"\0" * 8 + base64.b64decode(key_line)[10:]).decode()
    for data, signature, pubkey in (
            (SIGNED + b"!", SIGNATURE, TEST_PUBKEY),
            (SIGNED, _edited(SIGNATURE, "version:1.9.0", "version:1.9.1"), TEST_PUBKEY),
            (SIGNED, SIGNATURE, _edited(TEST_PUBKEY, key_line, other_id)),
            (SIGNED, SIGNATURE + "\n", TEST_PUBKEY)):
        with pytest.raises(SystemExit):
            cdn.verify(data, signature, pubkey)
    assert capsys.readouterr().err.count("cdn: ") == 4


def test_a_certificate_with_less_than_30_days_left_stops_the_release(cdn, capsys):
    """CDN 的证书 2026-11-22 到期：过期了一行命令的安装与外壳的更新都会断（spec §7），发布作业第一步
    就查。"""
    not_after = "Nov 22 13:59:59 2026 GMT"
    cdn.check_cert(not_after, datetime(2026, 10, 7, tzinfo=UTC))
    with pytest.raises(SystemExit):
        cdn.check_cert(not_after, datetime(2026, 10, 24, tzinfo=UTC))
    assert "Nov 22" in capsys.readouterr().err


def test_the_uv_version_for_the_desktop_build_comes_from_uv_lock(cdn, capsys):
    """桌面构建的 uv sidecar 照 uv.lock 的版本取（release.yml 调这个）。"""
    assert cdn.main(["uv-version"]) == 0
    assert capsys.readouterr().out.strip() == cdn.uv_version()


def _shell_build(where: Path, v: str = "1.9.0") -> dict[str, Path]:
    """tauri build 出的五样，已是 CDN 上的名字；两个更新包的内容就是测试签名签过的那几个字节。"""
    where.mkdir(parents=True, exist_ok=True)
    bodies = {f"AAAI4S_{v}_universal.dmg": b"dmg", "AAAI4S.app.tar.gz": SIGNED,
              "AAAI4S.app.tar.gz.sig": SIGNATURE.encode(), f"AAAI4S_{v}_x64-setup.exe": SIGNED,
              f"AAAI4S_{v}_x64-setup.exe.sig": SIGNATURE.encode()}
    for name, body in bodies.items():
        (where / name).write_bytes(body)
    return {name: where / name for name in bodies}


def _publish(cdn, client, where: Path, v: str, *, rewrite: bool, files=None):
    """传一遍桌面包；CDN 回源到假桶，HEAD 照桶里那份答。"""
    def head(url: str) -> tuple[int, int]:
        found = client.objects.get(url.removeprefix(f"{cdn.CDN}/"))
        return (200, len(found[0])) if found else (404, -1)

    work = where / "work"
    work.mkdir(parents=True)
    return cdn.publish_desktop(v, "ai4science/dist", files or _shell_build(where / "build", v),
                               client, retryable=(Flaky,), work=work, rewrite=rewrite,
                               notes="这一版的说明", pubkey=TEST_PUBKEY, head=head,
                               now=datetime(2026, 10, 20, 8, tzinfo=UTC))


def test_the_build_outputs_are_found_by_their_endings_whatever_the_product_name(
        cdn, tmp_path, capsys):
    """download-artifact 按构建分目录放；tauri 出的名字跟 productName 走，CDN 上的名字是定的（spec
    §7）。少一样、多一样（缓存里留下的旧包）都停，不猜。"""
    mac = tmp_path / "desktop-macos-latest" / "universal-apple-darwin" / "release" / "bundle"
    win = tmp_path / "desktop-windows-latest" / "release" / "bundle" / "nsis"
    built = [mac / "dmg" / "Aaai4s_1.9.0_universal.dmg", mac / "macos" / "Aaai4s.app.tar.gz",
             mac / "macos" / "Aaai4s.app.tar.gz.sig", win / "Aaai4s_1.9.0_x64-setup.exe",
             win / "Aaai4s_1.9.0_x64-setup.exe.sig"]
    for path in built:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(path.name.encode())
    found = cdn.shell_files(tmp_path, "1.9.0")
    assert {name: path.name for name, path in found.items()} == {
        "AAAI4S_1.9.0_universal.dmg": "Aaai4s_1.9.0_universal.dmg",
        "AAAI4S.app.tar.gz": "Aaai4s.app.tar.gz", "AAAI4S.app.tar.gz.sig": "Aaai4s.app.tar.gz.sig",
        "AAAI4S_1.9.0_x64-setup.exe": "Aaai4s_1.9.0_x64-setup.exe",
        "AAAI4S_1.9.0_x64-setup.exe.sig": "Aaai4s_1.9.0_x64-setup.exe.sig"}
    (mac / "Old.app.tar.gz").write_bytes(b"old")
    with pytest.raises(SystemExit):
        cdn.shell_files(tmp_path, "1.9.0")
    (mac / "Old.app.tar.gz").unlink()
    built[3].unlink()
    with pytest.raises(SystemExit):
        cdn.shell_files(tmp_path, "1.9.0")
    assert "_1.9.0_x64-setup.exe" in capsys.readouterr().err


def test_an_official_shell_goes_up_version_dir_first_then_the_links_then_latest_json(
        cdn, tmp_path):
    """desktop/<版本>/ → 固定下载地址（短缓存、按附件下载）→ latest.json 最后传（spec §7）：更新器
    读到新清单时包已经在了。两个 Mac 架构共用一个通用包；签名是 .sig 的全文。"""
    client = FakeClient()
    purged = _publish(cdn, client, tmp_path, "1.9.0", rewrite=True)
    base = "ai4science/dist/desktop"
    assert client.calls == [*(f"{base}/1.9.0/{name}" for name in _shell_build(tmp_path / "x")),
                            f"{base}/AAAI4S.dmg", f"{base}/AAAI4S-setup.exe", f"{base}/latest.json"]
    for link in ("AAAI4S.dmg", "AAAI4S-setup.exe"):
        assert client.headers[f"{base}/{link}"]["ContentDisposition"] == "attachment"
        assert client.headers[f"{base}/{link}"]["CacheControl"] == cdn.LATEST
    manifest = json.loads(client.objects[f"{base}/latest.json"][0])
    url = f"{cdn.CDN}/{base}/1.9.0"
    mac = {"url": f"{url}/AAAI4S.app.tar.gz", "signature": SIGNATURE}
    windows = {"url": f"{url}/AAAI4S_1.9.0_x64-setup.exe", "signature": SIGNATURE}
    assert manifest == {"version": "1.9.0", "notes": "这一版的说明",
                        "pub_date": "2026-10-20T08:00:00Z",
                        "platforms": {"darwin-aarch64": mac, "darwin-x86_64": mac,
                                      "windows-x86_64": windows}}
    assert purged == [f"{cdn.CDN}/{base}/{name}"
                      for name in ("AAAI4S.dmg", "AAAI4S-setup.exe", "latest.json")]


def test_an_unchanged_shell_keeps_latest_json_and_an_rc_only_puts_up_its_version_dir(
        cdn, tmp_path):
    """外壳没改不往已装的人推，固定下载地址照样换成这一版；rc 不碰 latest.json 与固定下载地址。"""
    client = FakeClient()
    _publish(cdn, client, tmp_path / "same", "1.9.0", rewrite=False)
    assert client.calls[5:] == ["ai4science/dist/desktop/AAAI4S.dmg",
                                "ai4science/dist/desktop/AAAI4S-setup.exe"]
    rc = FakeClient()
    assert _publish(cdn, rc, tmp_path / "rc", "1.9.0-rc.1", rewrite=True) == []
    assert len(rc.calls) == 5
    assert all(key.startswith("ai4science/dist/desktop/1.9.0-rc.1/") for key in rc.calls)


def test_a_rerun_after_a_rebuild_keeps_the_version_dir_already_in_the_bucket(cdn, tmp_path):
    """重跑整个流水线会重新出包，字节与签名都和桶里那份不一样：desktop/<版本>/ 只写一次，固定下载
    地址与 latest.json 照桶里那份来（spec §7）。只取回不一样的那几份：几十 MB 的包从上海取回美国的
    runner，能不取就不取。"""
    client = FakeClient()
    _publish(cdn, client, tmp_path / "first", "1.9.0", rewrite=False)
    rebuilt = _shell_build(tmp_path / "rebuilt")
    rebuilt["AAAI4S_1.9.0_universal.dmg"].write_bytes(b"rebuilt dmg")
    rebuilt["AAAI4S.app.tar.gz.sig"].write_text("rebuilt", encoding="utf-8")
    client.calls.clear()
    _publish(cdn, client, tmp_path / "second", "1.9.0", rewrite=True, files=rebuilt)
    base = "ai4science/dist/desktop"
    assert client.calls == [f"{base}/AAAI4S.dmg", f"{base}/AAAI4S-setup.exe", f"{base}/latest.json"]
    assert client.reads == [f"{base}/1.9.0/AAAI4S_1.9.0_universal.dmg",
                            f"{base}/1.9.0/AAAI4S.app.tar.gz.sig"]
    assert client.objects[f"{base}/AAAI4S.dmg"][0] == b"dmg"
    manifest = json.loads(client.objects[f"{base}/latest.json"][0])
    assert manifest["platforms"]["darwin-aarch64"]["signature"] == SIGNATURE


def test_latest_json_is_checked_before_it_goes_up(cdn, tmp_path, capsys):
    """更新器先整份校验再比版本，坏一条所有平台都更新失败（spec §7）：键不齐、签名验不过、签名里的
    版本不是清单的版本、CDN 上取不到或长度不对，都在传之前拦下。"""
    files = _shell_build(tmp_path)
    url = f"{cdn.CDN}/ai4science/dist/desktop/1.9.0"
    local = {f"{url}/{name}": path for name, path in files.items()}

    def head(target: str) -> tuple[int, int]:
        return 200, local[target].stat().st_size

    manifest = cdn.latest_json("1.9.0", "说明", url, files, datetime(2026, 10, 20, tzinfo=UTC))
    cdn.check_latest(manifest, local, TEST_PUBKEY, head)
    no_date = {key: value for key, value in manifest.items() if key != "pub_date"}
    no_windows = copy.deepcopy(manifest)
    del no_windows["platforms"]["windows-x86_64"]
    bad_signature = copy.deepcopy(manifest)
    bad_signature["platforms"]["windows-x86_64"]["signature"] = _edited(
        SIGNATURE, "version:1.9.0", "version:1.9.1")
    other_version = {**manifest, "version": "1.9.1"}
    cases = [(no_date, head), (no_windows, head), (bad_signature, head), (other_version, head),
             (manifest, lambda target: (200, head(target)[1] - 1)),
             (manifest, lambda target: (404, -1))]
    for broken, answer in cases:
        with pytest.raises(SystemExit):
            cdn.check_latest(broken, local, TEST_PUBKEY, answer)
    assert capsys.readouterr().err.count("cdn: ") == len(cases)


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t",
                    "-c", "commit.gpgsign=false", "-c", "tag.gpgsign=false", *args],
                   cwd=repo, check=True, capture_output=True)


def test_latest_json_is_rewritten_only_when_the_shell_changed_since_the_version_on_the_cdn(
        cdn, tmp_path, capsys):
    """外壳改过才往已装的人推（ADR-0005）。基准是 CDN 上那一版、不是上一个 tag：1.8.2 换了图标
    但那一版桌面构建失败，1.8.3 与上一个 tag 比没改，这次改动就永远推不出去。图标从品牌标生成，
    算外壳；外壳的 README 不算。"""
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    for tag, changes in (("v1.8.0", {"ui/desktop/src-tauri/main.rs": "1",
                                     "ui/web/public/favicon.svg": "A", "framework/x.py": "1"}),
                         ("v1.8.1", {"ui/desktop/README.md": "文档", "framework/x.py": "2"}),
                         ("v1.8.2", {"ui/web/public/favicon.svg": "三色的 A"}),
                         ("v1.8.3", {"framework/x.py": "3"}),
                         ("v1.8.4", {"ui/desktop/src-tauri/main.rs": "2"})):
        for name, text in changes.items():
            (repo / name).parent.mkdir(parents=True, exist_ok=True)
            (repo / name).write_text(text, encoding="utf-8")
        _git(repo, "add", "-A")
        _git(repo, "commit", "-qm", tag)
        _git(repo, "tag", tag)
    assert cdn.shell_changed(None, "v1.8.0", repo)[0]
    assert not cdn.shell_changed("1.8.0", "v1.8.1", repo)[0]
    assert cdn.shell_changed("1.8.0", "v1.8.3", repo)[0]
    assert not cdn.shell_changed("1.8.2", "v1.8.3", repo)[0]
    assert cdn.shell_changed("1.8.3", "v1.8.4", repo)[0]
    assert not cdn.shell_changed("1.8.4", "v1.8.4", repo)[0]  # 同一版重跑
    with pytest.raises(SystemExit):
        cdn.shell_changed("0.1.0", "v1.8.4", repo)
    assert "v0.1.0" in capsys.readouterr().err


@pytest.fixture
def site():
    """本机一个 HTTP 服务：路径 → (状态码, 内容)，没登记的 404。"""
    pages: dict[str, tuple[int, bytes]] = {}

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802  http.server 的写法
            status, body = pages.get(self.path, (404, b""))
            self.send_response(status)
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *_):
            pass

    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield pages, f"http://127.0.0.1:{server.server_port}"
    server.shutdown()


def test_the_base_is_what_the_cdn_serves_and_only_a_404_means_the_first_time(cdn, site):
    """CDN 一时出错当成「第一次」，就会把 latest.json 改写成没改过外壳的这一版、白推一次
    （spec §7）。"""
    pages, url = site
    pages["/latest.json"] = (200, b'{"version": "1.9.0"}')
    pages["/broken.json"] = (502, b"")
    assert cdn.latest_on_cdn(f"{url}/latest.json") == "1.9.0"
    assert cdn.latest_on_cdn(f"{url}/missing.json") is None
    with pytest.raises(urllib.error.HTTPError):
        cdn.latest_on_cdn(f"{url}/broken.json")


def test_an_rc_dry_run_lists_its_version_dir_and_writes_the_decision_to_the_job_summary(
        cdn, tmp_path, monkeypatch, capsys):
    build = tmp_path / "artifacts"
    _shell_build(build, "1.9.0-rc.1")
    summary = tmp_path / "summary.md"
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))
    assert cdn.main(["desktop", "v1.9.0-rc.1", "--artifacts", str(build), "--dry-run"]) == 0
    listed = re.findall(r"ai4science/dist/desktop/\S+", capsys.readouterr().out)
    assert listed == [f"ai4science/dist/desktop/1.9.0-rc.1/{name}" for name in
                      _shell_build(tmp_path / "x", "1.9.0-rc.1")]
    assert "latest.json" in summary.read_text(encoding="utf-8")
