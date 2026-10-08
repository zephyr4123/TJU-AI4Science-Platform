# /// script
# requires-python = ">=3.12"
# dependencies = [
#     "cos-python-sdk-v5==1.9.44",
#     "tencentcloud-sdk-python-cdn==3.1.169",
#     "cryptography==50.0.2",
# ]
# ///
"""cdn.py sign|wheel|desktop vX.Y.Z —— 把一行命令与桌面 App 要取的东西传到腾讯云 CDN
（外层 #277 #282）。

一行命令（`install/install.sh`）全程国内源：平台的 wheel、安装脚本、uv 的发布包都从我们自己的 CDN 取
（Claude Code 闭源不转发，平台装它时从 npmmirror 取）。发版流水线在 `make package` 之后跑这一步：

    ai4science/dist/<版本>/ai4sci-<版本>-py3-none-any.whl(.sha256)   不可变，长缓存
    ai4science/dist/<版本>/install.sh、install.ps1                     钉版本装（桌面 App 也用）
    ai4science/dist/<版本>/platform.json(.sig)                         这一版安装件的 sha256（签名）
    ai4science/dist/uv/<uv 版本>/uv-<平台>.tar.gz|zip(.sha256)          uv 官方发布包的原样副本
    ai4science/dist/install.sh、install.ps1                            最新版；短缓存，传完刷 CDN
    ai4science/dist/platform.json(.sig)                                最新版与安装件的 sha256

<版本> 是 wheel 文件名里的 PEP 440 写法：tag `v1.9.0-rc.1` 出的是 `1.9.0rc1`（spec §3）。预发布只传
带版本号的，不动最新的那几份；正式版也不往回换（CDN 上已经是更新的一版）。最新的 platform.json 要的
外壳（min_desktop）CDN 上还没有时也先不换，等 `desktop` 传完外壳再换：不然从官网下的旧外壳打不开。
uv 的版本照 uv.lock（平台依赖的那一版），从 GitHub 取、对它自己的 .sha256，每个平台的 sha256 写进
两份安装脚本。

签名与上传分两步（两步的环境里各只有自己那组密钥）：`sign` 在 --work 目录里备齐要传的东西、用更新器
的 key 签 platform.json；`wheel` 用同一个目录、只带 COS 的凭据传。重跑时桶里已有这一版的
platform.json 与签名，就用桶里那份签名（tauri 每次签都带新的时间戳）。

`desktop` 在桌面包构建完之后跑，传 tauri build 的产物（spec §7，<版本> 是 tag 的 SemVer 写法）：

    ai4science/dist/desktop/<版本>/AAAI4S_<版本>_universal.dmg         给人下载
    ai4science/dist/desktop/<版本>/AAAI4S.app.tar.gz(.sig)             Mac 外壳的更新
    ai4science/dist/desktop/<版本>/AAAI4S_<版本>_x64-setup.exe(.sig)   给人下载，也是 Windows 的更新
    ai4science/dist/desktop/AAAI4S.dmg、AAAI4S-setup.exe             固定的下载地址，正式版每次换
    ai4science/dist/desktop/latest.json                              更新器读的清单，外壳改过才改写

凭据从环境变量来（TENCENTCLOUD_SECRET_ID / _KEY，CI 里是 secrets，只能写这个前缀、能刷 CDN 的
子账号）；签名的 key 也是（TAURI_SIGNING_PRIVATE_KEY / _PASSWORD）。`--prefix` 换前缀先在测试目录
里真验一遍，`--dry-run` 只列不传、不签。依赖照 cdn.py.lock（`uv run --locked`）。
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import re
import runpy
import socket
import ssl
import subprocess
import sys
import tempfile
import time
import tomllib
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from datetime import UTC, datetime
from functools import partial
from pathlib import Path, PurePosixPath
from typing import NamedTuple

ROOT = Path(__file__).resolve().parents[2]
PACKAGES = ROOT / "dist"  # make package 出的包
# 后端要求的最低外壳版本，写进 platform.json（外层 #282）；PEP 723 的环境里没装平台，照文件读
MIN_DESKTOP = runpy.run_path(str(ROOT / "framework" / "desktop.py"))["MIN_DESKTOP"]
BUCKET = os.environ.get("COS_BUCKET", "zephyr-media-1322280257")
REGION = os.environ.get("COS_REGION", "ap-shanghai")
# 传包走 COS 全球加速域名（桶上已开，境外上传按量计费）：美国的 runner 走桶的默认域名往上海传，
# 24 MB 的 wheel 8 分半传不完，重试三次都失败（1.8.0 与 v1.9.0-rc.1，外层 #281）；
# 设成空串就走默认域名
ENDPOINT = os.environ.get("COS_ENDPOINT", "cos.accelerate.myqcloud.com")
CDN = os.environ.get("CDN_BASE", "https://media.zephyrxiang.com")
PREFIX = "ai4science/dist"
UV_RELEASES = "https://github.com/astral-sh/uv/releases/download"
UV_ARCHIVES = ("aarch64-apple-darwin.tar.gz", "x86_64-apple-darwin.tar.gz",
               "x86_64-unknown-linux-gnu.tar.gz", "aarch64-unknown-linux-gnu.tar.gz",
               "x86_64-pc-windows-msvc.zip", "aarch64-pc-windows-msvc.zip")
IMMUTABLE = "public, max-age=31536000, immutable"
LATEST = "public, max-age=300"
# Content-Type 照对象键的后缀；没列的（.sh .ps1 .sha256 .sig）是文本。浏览器照它决定显示还是存下来
TYPES = {".whl": "application/zip", ".gz": "application/gzip", ".zip": "application/zip",
         ".dmg": "application/x-apple-diskimage",
         ".exe": "application/vnd.microsoft.portable-executable", ".json": "application/json"}
TEXT = "text/plain; charset=utf-8"
# 每个对象传的时候记下 sha256：重跑时判断桶里那份是不是同一份（外层 #282）
META_SHA256 = "x-cos-meta-sha256"
# 分片重试到 SDK 的上限仍失败时 SDK 说「please upload_file again」：再调一次从断点续传（外层 #281）
UPLOAD_TRIES = 4
UPLOAD_WAIT_S = 10
# CDN 的证书剩不到这么多天就不发版：过期了一行命令的安装与外壳的更新都会断（spec §7）
CERT_DAYS = 30

# 桌面 App（外层 #282，spec §7）。外壳内置的更新器公钥在 tauri.conf.json（spec §3 冻结），
# platform.json 与外壳的更新包都用这一对 key 签
TAURI_CONF = ROOT / "ui" / "desktop" / "src-tauri" / "tauri.conf.json"
# tauri build 的产物按结尾认（不管 productName 写成什么）→ desktop/<版本>/ 里的名字；{v} 是 SemVer
SHELL_FILES = (("_{v}_universal.dmg", "AAAI4S_{v}_universal.dmg"),
               (".app.tar.gz", "AAAI4S.app.tar.gz"),
               (".app.tar.gz.sig", "AAAI4S.app.tar.gz.sig"),
               ("_{v}_x64-setup.exe", "AAAI4S_{v}_x64-setup.exe"),
               ("_{v}_x64-setup.exe.sig", "AAAI4S_{v}_x64-setup.exe.sig"))
# 固定的下载地址 ← 哪个包
FIXED = (("AAAI4S.dmg", "AAAI4S_{v}_universal.dmg"),
         ("AAAI4S-setup.exe", "AAAI4S_{v}_x64-setup.exe"))
# latest.json 的平台 → 哪个包：Mac 两个架构用同一个通用包
UPDATER = {"darwin-aarch64": "AAAI4S.app.tar.gz", "darwin-x86_64": "AAAI4S.app.tar.gz",
           "windows-x86_64": "AAAI4S_{v}_x64-setup.exe"}
# 外壳改没改看这几处（ADR-0005）：图标从品牌标生成，算外壳；外壳的 README 不算。路径清单只在这里
SHELL_PATHS = ("ui/desktop", "ui/web/public/favicon.svg", ":!ui/desktop/README.md")


def die(msg: str) -> None:
    print(f"cdn: {msg}", file=sys.stderr)
    sys.exit(1)


def uv_version() -> str:
    lock = tomllib.loads((ROOT / "uv.lock").read_text(encoding="utf-8"))
    return next(p["version"] for p in lock["package"] if p["name"] == "uv")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def fetch(url: str, dest: Path) -> Path:
    with urllib.request.urlopen(url, timeout=120) as resp:
        dest.write_bytes(resp.read())
    return dest


def render(script: str, version: str, uv: str, uv_sha256: dict[str, str]) -> str:
    """代入版本与每个平台 uv 发布包的 sha256（`<平台>=<sha256>`，空格分隔）：脚本由签名清单
    盖着，uv 也就在签名链里（外层 #282）。"""
    text = (ROOT / "install" / script).read_text(encoding="utf-8")
    pairs = " ".join(f"{triple}={digest}" for triple, digest in uv_sha256.items())
    return (text.replace("__VERSION__", version).replace("__UV_VERSION__", uv)
            .replace("__UV_SHA256__", pairs))


class Item(NamedTuple):
    """传一个对象：对象键、本地文件、Cache-Control；attachment 让浏览器存成文件（固定下载地址）。"""
    key: str
    path: Path
    cache: str
    attachment: bool = False


def official(version: str) -> bool:
    """正式版：只有 X.Y.Z（PEP 440 与 SemVer 的写法一样）；预发布不碰最新的那几份。"""
    return re.fullmatch(r"\d+\.\d+\.\d+", version) is not None


def older(version: str, than: str) -> bool:
    """两个正式版（X.Y.Z）比先后：最新的那几份只认正式版。"""
    return tuple(map(int, version.split("."))) < tuple(map(int, than.split(".")))


def built_wheel(tag: str) -> tuple[Path, str]:
    """make package 出的 wheel 与它的版本。版本从文件名取：rc 的 tag 是 SemVer（1.9.0-rc.1），
    setuptools-scm 把它规范成 PEP 440 的 1.9.0rc1，`ai4sci --version`、安装脚本、CDN 的目录都用这个
    写法（spec §3）。package.sh 对不上 tag 只警告（快照带 .devN），这里不认。"""
    wheels = sorted(PACKAGES.glob("ai4sci-*-py3-none-any.whl"))
    if len(wheels) != 1:
        die(f"{PACKAGES} 里应当正好一个 wheel，有 {len(wheels)} 个：先 make package VERSION={tag}")
    version = wheels[0].name.split("-")[1]
    if version != re.sub(r"-rc\.(\d+)$", r"rc\1", tag):
        die(f"出的是 {wheels[0].name}，不是 {tag} 的包（HEAD 不在 v{tag} 这个 tag 上）")
    return wheels[0], version


def plan(tag: str, prefix: str, work: Path, *,
         sign: Callable[[Path], Path] | None = None) -> list[Item]:
    """一份清单，先不可变的、最后最新的那几份；sha256 当场核对，不对就停。每一版都写一份带版本号
    的 `<ver>/platform.json`（外壳装那一版前照它核安装脚本），正式版再换最新的 `platform.json`
    （外壳拿它判断有没有新版本，spec §3）；给了 sign 就签（--dry-run 不签）。"""
    wheel, version = built_wheel(tag)
    side = wheel.with_name(wheel.name + ".sha256")
    if side.read_text(encoding="utf-8").split()[0] != sha256(wheel):
        die(f"{side.name} 与 wheel 对不上")
    items = [Item(f"{prefix}/{version}/{wheel.name}", wheel, IMMUTABLE),
             Item(f"{prefix}/{version}/{side.name}", side, IMMUTABLE)]
    uv = uv_version()
    uv_sha256 = {}
    for name in UV_ARCHIVES:
        archive, check = work / f"uv-{name}", work / f"uv-{name}.sha256"
        if not (archive.is_file() and check.is_file()):  # `sign` 在同一个目录里取过就不再取
            fetch(f"{UV_RELEASES}/{uv}/uv-{name}", archive)
            fetch(f"{UV_RELEASES}/{uv}/uv-{name}.sha256", check)
        if check.read_text(encoding="utf-8").split()[0] != sha256(archive):
            die(f"uv-{name} 与 GitHub 上的 .sha256 对不上")
        uv_sha256[name.removesuffix(".tar.gz").removesuffix(".zip")] = sha256(archive)
        items += [Item(f"{prefix}/uv/{uv}/{archive.name}", archive, IMMUTABLE),
                  Item(f"{prefix}/uv/{uv}/{check.name}", check, IMMUTABLE)]
    pinned = {}
    for script in ("install.sh", "install.ps1"):
        pinned[script] = work / script
        pinned[script].write_text(render(script, version, uv, uv_sha256), encoding="utf-8")
        items.append(Item(f"{prefix}/{version}/{script}", pinned[script], IMMUTABLE))
    manifest = work / "platform.json"
    manifest.write_text(json.dumps({
        "version": version, "min_desktop": MIN_DESKTOP,
        "sha256": {"install.sh": sha256(pinned["install.sh"]),
                   "install.ps1": sha256(pinned["install.ps1"]), "wheel": sha256(wheel)},
    }, indent=2) + "\n", encoding="utf-8")
    signature = sign(manifest) if sign else None
    # 每一版（rc 也是）都有一份带版本号的签名清单：预发布的外壳装它自己那一版时照它核脚本
    items.append(Item(f"{prefix}/{version}/platform.json", manifest, IMMUTABLE))
    if signature:
        items.append(Item(f"{prefix}/{version}/platform.json.sig", signature, IMMUTABLE))
    if not official(version):
        return items
    items += [Item(f"{prefix}/{script}", path, LATEST) for script, path in pinned.items()]
    items.append(Item(f"{prefix}/platform.json", manifest, LATEST))
    if signature:
        items.append(Item(f"{prefix}/platform.json.sig", signature, LATEST))
    return items


def tauri_sign(path: Path, pubkey: str) -> Path:
    """用更新器那把 key 签（外壳用内置的公钥验，spec §3）：ui/desktop 钉的 tauri CLI，key 与口令从
    环境变量来，签名写在旁边的 <文件>.sig。签完当场用外壳的公钥验一遍：secrets 里的 key 配错了，
    外壳会把 platform.json 当作取不到、再也不升级，没人看得见。"""
    if not os.environ.get("TAURI_SIGNING_PRIVATE_KEY"):
        die("缺 TAURI_SIGNING_PRIVATE_KEY（更新器的私钥，CI 里是 secrets）")
    subprocess.run(["npx", "--no-install", "tauri", "signer", "sign", str(path)],
                   cwd=ROOT / "ui" / "desktop", check=True)
    sig = path.with_name(path.name + ".sig")
    verify(path.read_bytes(), sig.read_text(encoding="utf-8"), pubkey)
    return sig


def signed_already(path: Path, pubkey: str) -> Path:
    """`sign` 那一步签好的：在旁边、用外壳的公钥验得过（备齐的东西与这次出的 platform.json 是
    同一份）。"""
    sig = path.with_name(path.name + ".sig")
    if not sig.is_file():
        die(f"没有 {sig}：先在同一个 --work 目录里跑 cdn.py sign")
    verify(path.read_bytes(), sig.read_text(encoding="utf-8"), pubkey)
    return sig


def settle_signature(items: list[Item], version: str, prefix: str, client) -> None:
    """重跑 wheel：这一版的 platform.json 已经在桶里（同一份）、签名也在，就用桶里那份签名，最新的
    那份也用它。tauri 每次签都带新的时间戳，新签的与桶里不可变的那份同名不同内容，重跑就永远
    失败。"""
    manifest = next(item for item in items if item.key == f"{prefix}/{version}/platform.json")
    sig = next(item for item in items if item.key == f"{prefix}/{version}/platform.json.sig")
    if not (client.object_exists(Bucket=BUCKET, Key=sig.key)
            and client.object_exists(Bucket=BUCKET, Key=manifest.key)
            and _bucket_sha256(client, manifest.key) == sha256(manifest.path)):
        return
    sig.path.write_bytes(_read(client, sig.key))
    print(f"skip 重签 {sig.key}（桶里已有这一版的清单与签名，用桶里那份）")


class Published(NamedTuple):
    """CDN 上最新的那几份现在是哪一版（没有是 None）：两份安装脚本、platform.json、外壳的
    latest.json。"""
    scripts: str | None
    manifest: str | None
    shell: str | None


def published(prefix: str) -> Published:
    def script_version(url: str) -> str | None:
        try:
            with urllib.request.urlopen(url, timeout=60) as resp:
                text = resp.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            if exc.code != 404:
                raise
            return None
        found = re.search(r'^VERSION="([^"]+)"$', text, re.M)
        return found.group(1) if found else None

    return Published(script_version(f"{CDN}/{prefix}/install.sh"),
                     latest_on_cdn(f"{CDN}/{prefix}/platform.json"),
                     latest_on_cdn(f"{CDN}/{prefix}/desktop/latest.json"))


def keep_latest(items: list[Item], version: str, now: Published,
                min_desktop: str = MIN_DESKTOP) -> tuple[list[Item], list[str]]:
    """正式版的「最新」那几份换不换，返回留下的与为什么：CDN 上已经是更新的一版就不往回换（回头
    重跑旧版的作业）；platform.json 要的外壳 CDN 上还没有（这一版抬了 min_desktop、或第一次发外壳）
    先不换，留给 `desktop` 传完外壳再换——不然从官网下的旧外壳卡在「先更新桌面 App」，又没有新的
    可更新。"""
    drop, why = set(), []
    scripts = {f"/{name}" for name in ("install.sh", "install.ps1")}
    manifests = {"/platform.json", "/platform.json.sig"}

    def latest(endings: set[str]) -> set[str]:
        return {item.key for item in items if item.cache == LATEST
                and any(item.key.endswith(ending) for ending in endings)}

    if now.scripts and official(now.scripts) and older(version, now.scripts):
        drop |= latest(scripts)
        why.append(f"CDN 上的安装脚本已经是 {now.scripts}，不换回 {version}")
    if now.manifest and older(version, now.manifest):
        drop |= latest(manifests)
        why.append(f"CDN 上的 platform.json 已经是 {now.manifest}，不换回 {version}")
    elif now.shell is None or older(now.shell, min_desktop):
        drop |= latest(manifests)
        why.append(f"这一版要外壳 ≥ {min_desktop}，CDN 上的外壳是 {now.shell or '（还没有）'}："
                   "最新的 platform.json 留给 desktop 传完外壳再换")
    return [item for item in items if item.key not in drop], why


def updater_pubkey(given: str | None) -> str:
    """外壳内置的更新器公钥：缺省读 tauri.conf.json；--pubkey 给了用它（拿测试的 key 先验一遍）。"""
    if given:
        return given
    if not TAURI_CONF.is_file():
        die(f"没有 {TAURI_CONF}：用 --pubkey 给更新器的公钥")
    return json.loads(TAURI_CONF.read_text(encoding="utf-8"))["plugins"]["updater"]["pubkey"]


def _b64(text: str) -> bytes:
    """更新器的 base64 不认换行、空格这类多出来的字符，这里也不认。"""
    return base64.b64decode(text, validate=True)


def verify(data: bytes, signature: str, pubkey: str) -> str:
    """照外壳的更新器验一份 tauri 的签名（minisign；签名与公钥都是 base64 包着的 minisign 文本，
    更新器里是 minisign-verify）。验过返回签名里的 trusted comment（全局签名也盖着它），验不过
    就停。"""
    from cryptography.exceptions import InvalidSignature
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

    try:
        _, key_line = _b64(pubkey).decode("utf-8").splitlines()
        _, sig_line, trusted_line, global_line = _b64(signature).decode("utf-8").splitlines()
        key, sig, global_sig = _b64(key_line), _b64(sig_line), _b64(global_line)
        public = Ed25519PublicKey.from_public_bytes(key[10:])
    except ValueError as exc:  # base64 不对、行数不对、公钥长度不对：更新器同样不认
        die(f"不是一份 tauri 的签名或公钥：{exc}")
    if (not trusted_line.startswith("trusted comment: ") or key[:2] != b"Ed"
            or sig[:2] not in (b"Ed", b"ED") or sig[2:10] != key[2:10]):
        die("签名不是这把公钥签的（key id 对不上）或格式不对")
    trusted = trusted_line.removeprefix("trusted comment: ")
    # ED 签的是内容的 BLAKE2b-512（tauri 签的都是这种），Ed 是旧式、签内容本身
    message = hashlib.blake2b(data).digest() if sig[:2] == b"ED" else data
    try:
        public.verify(sig[10:], message)
        public.verify(global_sig, sig[10:] + trusted.encode("utf-8"))
    except InvalidSignature:
        die("签名验不过：内容被改过，或不是这把 key 签的")
    return trusted


def signed_version(trusted: str) -> str | None:
    """trusted comment 里的版本：tauri 写成 Tab 分隔的 key:value（timestamp、file、version），
    更新器开了 requireSignedVersion 就拿它对清单里的版本。"""
    return next((field.removeprefix("version:") for field in trusted.split("\t")
                 if field.startswith("version:")), None)


def client_from_env():
    """COS 的 client 与它会抛的、值得再试一次的错。凭据从环境变量来。"""
    from qcloud_cos import CosConfig, CosS3Client
    from qcloud_cos.cos_exception import CosClientError, CosServiceError

    client = CosS3Client(CosConfig(Region=REGION, Endpoint=ENDPOINT or None,
                                   SecretId=os.environ["TENCENTCLOUD_SECRET_ID"],
                                   SecretKey=os.environ["TENCENTCLOUD_SECRET_KEY"]))
    return client, (CosClientError, CosServiceError)


def upload(items: list[Item], client, *, retryable: tuple[type[BaseException], ...]) -> None:
    """一个个传。不可变的（带版本号的）先看桶里那份：同一份（sha256）跳过，重跑流水线只补没传成的；
    同名不同内容让作业失败、不覆盖：边缘节点照一年的缓存发旧字节，包与签名就对不上了（spec §7）。
    最新的那几份每次都传。传失败照 SDK 的说法再调（从断点续传），试够了照样抛。"""
    for item in items:
        digest = sha256(item.path)
        if item.cache == IMMUTABLE and _already_there(client, item.key, digest):
            print(f"skip {CDN}/{item.key}（桶里已有同一份）")
            continue
        headers = {"CacheControl": item.cache, "Metadata": {META_SHA256: digest},
                   "ContentType": TYPES.get(PurePosixPath(item.key).suffix, TEXT)}
        if item.attachment:
            headers["ContentDisposition"] = "attachment"
        for attempt in range(1, UPLOAD_TRIES + 1):
            try:
                client.upload_file(Bucket=BUCKET, Key=item.key, LocalFilePath=str(item.path),
                                   ACL="public-read", **headers)
                break
            except retryable as exc:
                if attempt == UPLOAD_TRIES:
                    raise
                print(f"retry {attempt}/{UPLOAD_TRIES - 1} {item.key}：{exc}", file=sys.stderr)
                time.sleep(UPLOAD_WAIT_S * attempt)
        print(f"ok {CDN}/{item.key}")


def _already_there(client, key: str, digest: str) -> bool:
    if not client.object_exists(Bucket=BUCKET, Key=key):
        return False
    theirs = _bucket_sha256(client, key)
    if theirs != digest:
        die(f"{key} 桶里已有一份内容不同的（sha256 {theirs[:12]}…，这次 {digest[:12]}…）："
            "带版本号的不覆盖")
    return True


def _bucket_sha256(client, key: str) -> str:
    """桶里那份的 sha256：传的时候记在元数据里。1.9.0 以前传的没有：旁边有 .sha256 就读它（uv 的包
    几十 MB，不从上海取回美国的 runner），再没有就取回来算。"""
    meta = client.head_object(Bucket=BUCKET, Key=key)
    meta = {name.lower(): value for name, value in meta.items()}
    if META_SHA256 in meta:
        return meta[META_SHA256]
    side = key + ".sha256"
    if client.object_exists(Bucket=BUCKET, Key=side):
        return _read(client, side).decode("utf-8").split()[0]
    return hashlib.sha256(_read(client, key)).hexdigest()


def _read(client, key: str) -> bytes:
    return client.get_object(Bucket=BUCKET, Key=key)["Body"].get_raw_stream().read()


def purge(urls: list[str]) -> None:
    from tencentcloud.cdn.v20180606 import cdn_client, models
    from tencentcloud.common import credential

    cred = credential.Credential(os.environ["TENCENTCLOUD_SECRET_ID"],
                                 os.environ["TENCENTCLOUD_SECRET_KEY"])
    req = models.PurgeUrlsCacheRequest()
    req.Urls = urls
    task = cdn_client.CdnClient(cred, "").PurgeUrlsCache(req).TaskId
    print(f"ok 刷新 {len(urls)} 个地址的缓存（任务 {task}）")


def shell_files(artifacts: Path, v: str) -> dict[str, Path]:
    """下载下来的构建产物 → {desktop/<版本>/ 里的名字: 本地文件}。每样正好一个，少了多了都停。"""
    built = [path for path in artifacts.rglob("*") if path.is_file()]
    found = {}
    for ending, name in SHELL_FILES:
        hits = [path for path in built if path.name.endswith(ending.format(v=v))]
        if len(hits) != 1:
            die(f"{artifacts} 里以 {ending.format(v=v)} 结尾的应当正好一个，有 {len(hits)} 个")
        found[name.format(v=v)] = hits[0]
    return found


def latest_on_cdn(url: str) -> str | None:
    """CDN 上当前 latest.json 的版本，外壳改没改以它为基准；404 才算还没发过外壳，别的错误让作业
    失败（spec §7）。"""
    try:
        with urllib.request.urlopen(url, timeout=60) as resp:
            return json.loads(resp.read())["version"]
    except urllib.error.HTTPError as exc:
        if exc.code != 404:
            raise
        return None


def shell_changed(base: str | None, tag: str, repo: Path = ROOT) -> tuple[bool, str]:
    """要不要改写 latest.json、为什么：外壳从基准那一版到这个 tag 改过才往已装的人推（ADR-0005）。
    基准是 CDN 上那一版、不是上一个 tag：某一版外壳改了但桌面构建失败，下一版与上一个 tag 比没改，
    那次改动就永远推不出去。"""
    if base is None:
        return True, "CDN 上还没有 latest.json：第一次发外壳"
    diff = subprocess.run(["git", "diff", "--quiet", f"v{base}", tag, "--", *SHELL_PATHS], cwd=repo)
    if diff.returncode == 0:
        return False, f"从 CDN 上的 v{base} 到 {tag} 外壳没改（{' '.join(SHELL_PATHS)}）"
    if diff.returncode != 1:
        die(f"git diff v{base} {tag} 失败（退出码 {diff.returncode}）：v{base} 这个 tag 在不在？")
    return True, f"从 CDN 上的 v{base} 到 {tag} 外壳改过"


def latest_json(v: str, notes: str, url: str, files: dict[str, Path], now: datetime) -> dict:
    """更新器读的清单。url 是 desktop/<版本>/ 的地址；signature 是 .sig 的全文，不是路径。"""
    platforms = {}
    for platform, name in UPDATER.items():
        package = name.format(v=v)
        platforms[platform] = {"url": f"{url}/{package}",
                               "signature": files[f"{package}.sig"].read_text(encoding="utf-8")}
    return {"version": v, "notes": notes, "pub_date": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "platforms": platforms}


def head(url: str) -> tuple[int, int]:
    """CDN 上这个地址的状态码与长度（没有长度是 -1）。"""
    try:
        with urllib.request.urlopen(urllib.request.Request(url, method="HEAD"), timeout=60) as resp:
            return resp.status, int(resp.headers.get("Content-Length", -1))
    except urllib.error.HTTPError as exc:
        return exc.code, -1


def check_latest(manifest: dict, local: dict[str, Path], pubkey: str,
                 head: Callable[[str], tuple[int, int]]) -> None:
    """latest.json 传之前最后一道（spec §7）。更新器先整份校验再比版本，坏一条所有平台都更新失败：
    键齐；每个地址 HEAD 是 200、长度等于要发的那份；签名用外壳内置的公钥验得过；签名里的版本等于
    清单的版本（更新器开着 requireSignedVersion）。local：地址 → 与桶里一样的本地文件。"""
    platforms = manifest.get("platforms", {})
    missing = [key for key in ("version", "notes", "pub_date") if key not in manifest]
    missing += [key for key in UPDATER if not {"url", "signature"} <= set(platforms.get(key, {}))]
    if missing:
        die(f"latest.json 缺 {'、'.join(missing)}")
    for platform, entry in platforms.items():
        path = local[entry["url"]]
        status, length = head(entry["url"])
        if status != 200 or length != path.stat().st_size:
            die(f"{entry['url']}：HEAD {status}、长度 {length}，要发的那份 {path.stat().st_size}")
        signed = signed_version(verify(path.read_bytes(), entry["signature"], pubkey))
        if signed != manifest["version"]:
            die(f"{platform} 的签名是给 {signed} 签的，latest.json 写的是 {manifest['version']}")


def write_once(items: list[Item], client, *, retryable: tuple[type[BaseException], ...],
               work: Path) -> dict[str, Path]:
    """desktop/<版本>/ 只写一次（spec §7）：已经全在桶里就一个不传、用桶里那几份（重跑整条流水线
    重新出的包与签名跟桶里的不一样，latest.json 要照桶里的生成；不一样的才取回来）；不全就照不可变
    对象的规矩补（同一份跳过，同名不同内容失败）。返回 {名字: 与桶里一样的本地文件}。"""
    named = {PurePosixPath(item.key).name: item for item in items}
    if not all(client.object_exists(Bucket=BUCKET, Key=item.key) for item in items):
        upload(items, client, retryable=retryable)
        return {name: item.path for name, item in named.items()}
    print(f"skip {CDN}/{PurePosixPath(items[0].key).parent}/（已在桶里，用桶里那份）")
    same = {}
    for name, item in named.items():
        same[name] = item.path
        if _bucket_sha256(client, item.key) != sha256(item.path):
            same[name] = work / name
            client.download_file(Bucket=BUCKET, Key=item.key, DestFilePath=str(same[name]))
    return same


def publish_desktop(v: str, prefix: str, files: dict[str, Path], client, *,
                    retryable: tuple[type[BaseException], ...], work: Path, rewrite: bool,
                    notes: str, pubkey: str, head: Callable[[str], tuple[int, int]] = head,
                    now: datetime, shell_on_cdn: str | None = None) -> list[str]:
    """传桌面包，返回要刷缓存的地址。先 desktop/<版本>/，正式版再换固定的下载地址，外壳改过
    （rewrite）再传 latest.json（传前校验）：更新器读到新清单时包已经在了；最后把 wheel 那一步留下
    没换的最新 platform.json 换上。预发布、比 CDN 上的外壳（shell_on_cdn）旧的只传带版本号的。
    """
    base = f"{prefix}/desktop"
    versioned = [Item(f"{base}/{v}/{name}", path, IMMUTABLE) for name, path in files.items()]
    files = write_once(versioned, client, retryable=retryable, work=work)
    if not official(v) or (shell_on_cdn and older(v, shell_on_cdn)):
        return []
    fixed = [Item(f"{base}/{link}", files[name.format(v=v)], LATEST, attachment=True)
             for link, name in FIXED]
    upload(fixed, client, retryable=retryable)
    purged = [f"{CDN}/{item.key}" for item in fixed]
    if rewrite:
        url = f"{CDN}/{base}/{v}"
        manifest = latest_json(v, notes, url, files, now)
        local = {f"{url}/{name}": path for name, path in files.items()}
        check_latest(manifest, local, pubkey, head)
        path = work / "latest.json"
        path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        upload([Item(f"{base}/latest.json", path, LATEST)], client, retryable=retryable)
        purged.append(f"{CDN}/{base}/latest.json")
    shell = v if rewrite else shell_on_cdn
    return purged + promote_manifest(v, prefix, shell, client, retryable=retryable, work=work)


def promote_manifest(v: str, prefix: str, shell: str | None, client, *,
                     retryable: tuple[type[BaseException], ...], work: Path) -> list[str]:
    """最新的 platform.json 换成这一版的（`keep_latest` 让 wheel 那一步留下的）：CDN 上的外壳
    （shell）够这一版要的 min_desktop 了才换；已经是这一版或更新的不动。拷的是桶里 `<版本>/` 那
    两份。"""
    latest = f"{prefix}/platform.json"
    if client.object_exists(Bucket=BUCKET, Key=latest):
        current = json.loads(_read(client, latest))["version"]
        if not older(current, v):
            return []
    versioned = f"{prefix}/{v}/platform.json"
    if not client.object_exists(Bucket=BUCKET, Key=versioned):
        die(f"桶里没有 {versioned}：先跑这一版的 publish-wheel")
    wanted = json.loads(_read(client, versioned))["min_desktop"]
    if shell is None or older(shell, wanted):
        summary(f"最新的 platform.json 没换：{v} 要外壳 ≥ {wanted}，CDN 上的外壳是 {shell}")
        return []
    items = []
    for name in ("platform.json", "platform.json.sig"):
        local = work / f"latest-{name}"
        local.write_bytes(_read(client, f"{prefix}/{v}/{name}"))
        items.append(Item(f"{prefix}/{name}", local, LATEST))
    upload(items, client, retryable=retryable)
    summary(f"最新的 platform.json 换成 {v}（CDN 上的外壳 {shell} 够它要的 {wanted}）")
    return [f"{CDN}/{item.key}" for item in items]


def summary(line: str) -> None:
    """判定写进作业摘要（GitHub 的 job summary）；本地跑只打出来。"""
    print(line)
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8") as out:
            out.write(line + "\n")


def changelog_notes(v: str) -> str:
    """这一版的 Release Notes（与 GitHub Release 同一段），写进 latest.json。"""
    return subprocess.run([str(ROOT / ".github" / "scripts" / "changelog.sh"), "notes", v],
                          cwd=ROOT, stdout=subprocess.PIPE, encoding="utf-8",
                          check=True).stdout.strip()


def cert_not_after(host: str) -> str:
    context = ssl.create_default_context()
    with (socket.create_connection((host, 443), timeout=30) as sock,
          context.wrap_socket(sock, server_hostname=host) as tls):
        return tls.getpeercert()["notAfter"]


def check_cert(not_after: str, now: datetime) -> None:
    days = (ssl.cert_time_to_seconds(not_after) - now.timestamp()) / 86400
    if days < CERT_DAYS:
        die(f"{CDN} 的证书 {not_after} 到期，只剩 {days:.0f} 天（不到 {CERT_DAYS} 天）："
            "先换证书再发版")
    print(f"ok {CDN} 的证书 {not_after} 到期，还有 {days:.0f} 天")


def cmd_cert(args: argparse.Namespace) -> int:
    check_cert(cert_not_after(urllib.parse.urlsplit(CDN).hostname), datetime.now(UTC))
    return 0


def cmd_uv_version(args: argparse.Namespace) -> int:
    print(uv_version())
    return 0


def cmd_sign(args: argparse.Namespace) -> int:
    work = Path(args.work)
    work.mkdir(parents=True, exist_ok=True)
    plan(args.tag.removeprefix("v"), args.prefix.rstrip("/"), work,
         sign=partial(tauri_sign, pubkey=updater_pubkey(args.pubkey)))
    print(f"ok 备齐、签好：{work}")
    return 0


def cmd_wheel(args: argparse.Namespace) -> int:
    prefix = args.prefix.rstrip("/")
    if args.dry_run:
        with tempfile.TemporaryDirectory() as tmp:
            for item in plan(args.tag.removeprefix("v"), prefix, Path(tmp)):
                print(f"{CDN}/{item.key}\t{item.path.stat().st_size}\t{item.cache}")
        return 0
    if not args.work:
        die("要 --work：先在同一个目录里跑 cdn.py sign")
    work = Path(args.work)
    items = plan(args.tag.removeprefix("v"), prefix, work,
                 sign=partial(signed_already, pubkey=updater_pubkey(args.pubkey)))
    version = next(item.key for item in items if item.key.endswith(".whl")).split("/")[-2]
    client, retryable = client_from_env()
    settle_signature(items, version, prefix, client)
    if official(version):
        items, why = keep_latest(items, version, published(prefix))
        for line in why:
            summary(f"平台 {version}：{line}")
    upload(items, client, retryable=retryable)
    latest = [f"{CDN}/{item.key}" for item in items if item.cache == LATEST]
    if latest:
        purge(latest)
    return 0


def cmd_desktop(args: argparse.Namespace) -> int:
    v, prefix = args.tag.removeprefix("v"), args.prefix.rstrip("/")
    files = shell_files(Path(args.artifacts), v)
    base = latest_on_cdn(f"{CDN}/{prefix}/desktop/latest.json") if official(v) else None
    if not official(v):
        rewrite, reason = False, "预发布只传带版本号的，不碰 latest.json 与固定的下载地址"
    elif base and older(v, base):
        rewrite, reason = False, (f"比 CDN 上的外壳 {base} 旧（重跑旧版的作业）：只补 "
                                  f"desktop/{v}/，不碰固定的下载地址、latest.json 与最新的 "
                                  "platform.json")
    else:
        rewrite, reason = shell_changed(base, f"v{v}")
    summary(f"桌面 App {v}：{'改写' if rewrite else '不改写'} latest.json。{reason}")
    if args.dry_run:
        for name, path in files.items():
            print(f"{CDN}/{prefix}/desktop/{v}/{name}\t{path.stat().st_size}\t{IMMUTABLE}")
        return 0
    notes = changelog_notes(v) if rewrite else ""
    pubkey = updater_pubkey(args.pubkey) if rewrite else ""
    client, retryable = client_from_env()
    with tempfile.TemporaryDirectory() as tmp:
        purged = publish_desktop(v, prefix, files, client, retryable=retryable, work=Path(tmp),
                                 rewrite=rewrite, notes=notes, pubkey=pubkey, now=datetime.now(UTC),
                                 shell_on_cdn=base)
    if purged:
        purge(purged)
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="把一行命令与桌面 App 要取的东西传到腾讯云 CDN")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sign = sub.add_parser("sign", help="在 --work 目录里备齐 wheel 那一步要传的、签 platform.json")
    wheel = sub.add_parser("wheel", help="平台的 wheel、安装脚本、uv 的发布包、platform.json")
    for each in (sign, wheel):
        each.add_argument("tag", help="vX.Y.Z 或 vX.Y.Z-rc.N")
        each.add_argument("--prefix", default=PREFIX, help=f"对象键前缀，缺省 {PREFIX}")
        each.add_argument("--pubkey", help="更新器的公钥，缺省读 ui/desktop 的 tauri.conf.json")
    sign.add_argument("--work", required=True, help="备齐的东西放哪（wheel 用同一个）")
    sign.set_defaults(run=cmd_sign)
    wheel.add_argument("--work", help="sign 备齐、签好的目录")
    wheel.add_argument("--dry-run", action="store_true", help="只列要传什么，不签")
    wheel.set_defaults(run=cmd_wheel)
    desktop = sub.add_parser("desktop", help="桌面包：desktop/<版本>/、固定的下载地址、latest.json")
    desktop.add_argument("tag", help="vX.Y.Z 或 vX.Y.Z-rc.N")
    desktop.add_argument("--artifacts", required=True, help="tauri build 的产物所在的目录")
    desktop.add_argument("--prefix", default=PREFIX, help=f"对象键前缀，缺省 {PREFIX}")
    desktop.add_argument("--pubkey", help="更新器的公钥，缺省读 ui/desktop 的 tauri.conf.json")
    desktop.add_argument("--dry-run", action="store_true", help="只列要传什么、外壳改没改")
    desktop.set_defaults(run=cmd_desktop)
    sub.add_parser("cert", help=f"CDN 的证书剩不到 {CERT_DAYS} 天就失败").set_defaults(run=cmd_cert)
    sub.add_parser("uv-version", help="uv.lock 里 uv 的版本（桌面包的 sidecar 用）").set_defaults(
        run=cmd_uv_version)
    args = ap.parse_args(argv)
    return args.run(args)


if __name__ == "__main__":
    sys.exit(main())
