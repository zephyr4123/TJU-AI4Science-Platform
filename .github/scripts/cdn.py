# /// script
# requires-python = ">=3.12"
# dependencies = [
#     "cos-python-sdk-v5==1.9.44",
#     "tencentcloud-sdk-python-cdn==3.1.169",
# ]
# ///
"""cdn.py wheel vX.Y.Z —— 把一行命令与桌面 App 要取的东西传到腾讯云 CDN（外层 #277 #282）。

一行命令（`install/install.sh`）全程国内源：平台的 wheel、安装脚本、uv 的发布包都从我们自己的 CDN 取
（Claude Code 闭源不转发，平台装它时从 npmmirror 取）。发版流水线在 `make package` 之后跑这一步：

    ai4science/dist/<版本>/ai4sci-<版本>-py3-none-any.whl(.sha256)   不可变，长缓存
    ai4science/dist/<版本>/install.sh、install.ps1                     钉版本装（桌面 App 也用）
    ai4science/dist/uv/<uv 版本>/uv-<平台>.tar.gz|zip(.sha256)          uv 官方发布包的原样副本
    ai4science/dist/install.sh、install.ps1                            最新版；短缓存，传完刷 CDN
    ai4science/dist/platform.json(.sig)                                最新版与安装件的 sha256

<版本> 是 wheel 文件名里的 PEP 440 写法：tag `v1.9.0-rc.1` 出的是 `1.9.0rc1`（spec §3）。预发布只传
带版本号的，不动最新的那几份。uv 的版本照 uv.lock（平台依赖的那一版），从 GitHub 取、对它自己的
.sha256。凭据从环境变量来（TENCENTCLOUD_SECRET_ID / _KEY，CI 里是 secrets，只能写这个前缀、能刷 CDN
的子账号）；签名的 key 也是（TAURI_SIGNING_PRIVATE_KEY / _PASSWORD）。`--prefix` 换前缀先在测试目录
里真验一遍，`--dry-run` 只列不传、不签。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import runpy
import subprocess
import sys
import tempfile
import time
import tomllib
import urllib.request
from collections.abc import Callable
from pathlib import Path
from typing import NamedTuple

ROOT = Path(__file__).resolve().parents[2]
PACKAGES = ROOT / "dist"  # make package 出的包
# 后端要求的最低外壳版本，写进 platform.json（外层 #282）；PEP 723 的环境里没装平台，照文件读
MIN_DESKTOP = runpy.run_path(str(ROOT / "framework" / "desktop.py"))["MIN_DESKTOP"]
BUCKET = os.environ.get("COS_BUCKET", "zephyr-media-1322280257")
REGION = os.environ.get("COS_REGION", "ap-shanghai")
CDN = os.environ.get("CDN_BASE", "https://media.zephyrxiang.com")
PREFIX = "ai4science/dist"
UV_RELEASES = "https://github.com/astral-sh/uv/releases/download"
UV_ARCHIVES = ("aarch64-apple-darwin.tar.gz", "x86_64-apple-darwin.tar.gz",
               "x86_64-unknown-linux-gnu.tar.gz", "aarch64-unknown-linux-gnu.tar.gz",
               "x86_64-pc-windows-msvc.zip", "aarch64-pc-windows-msvc.zip")
IMMUTABLE = "public, max-age=31536000, immutable"
LATEST = "public, max-age=300"
TYPES = {".whl": "application/zip", ".gz": "application/gzip", ".zip": "application/zip"}
TEXT = "text/plain; charset=utf-8"
# 美国的 runner 往上海的桶分片上传，偶尔有分片重试到 SDK 的上限仍失败（1.8.0，外层 #281）；SDK 说
# 「please upload_file again」：再调一次从断点续传
UPLOAD_TRIES = 4
UPLOAD_WAIT_S = 10


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


def render(script: str, version: str, uv: str) -> str:
    text = (ROOT / "install" / script).read_text(encoding="utf-8")
    return text.replace("__VERSION__", version).replace("__UV_VERSION__", uv)


class Item(NamedTuple):
    """传一个对象：对象键、本地文件、Cache-Control。"""
    key: str
    path: Path
    cache: str


def official(version: str) -> bool:
    """正式版：只有 X.Y.Z（PEP 440 与 SemVer 的写法一样）；预发布不碰最新的那几份。"""
    return re.fullmatch(r"\d+\.\d+\.\d+", version) is not None


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
    """一份清单，先不可变的、最后最新的那几份；sha256 当场核对，不对就停。正式版再写 platform.json：
    外壳拿它判断有没有新版本、核安装脚本（spec §3），给了 sign 就签（--dry-run 不签）。"""
    wheel, version = built_wheel(tag)
    side = wheel.with_name(wheel.name + ".sha256")
    if side.read_text(encoding="utf-8").split()[0] != sha256(wheel):
        die(f"{side.name} 与 wheel 对不上")
    items = [Item(f"{prefix}/{version}/{wheel.name}", wheel, IMMUTABLE),
             Item(f"{prefix}/{version}/{side.name}", side, IMMUTABLE)]
    uv = uv_version()
    for name in UV_ARCHIVES:
        archive = fetch(f"{UV_RELEASES}/{uv}/uv-{name}", work / f"uv-{name}")
        check = fetch(f"{UV_RELEASES}/{uv}/uv-{name}.sha256", work / f"uv-{name}.sha256")
        if check.read_text(encoding="utf-8").split()[0] != sha256(archive):
            die(f"uv-{name} 与 GitHub 上的 .sha256 对不上")
        items += [Item(f"{prefix}/uv/{uv}/{archive.name}", archive, IMMUTABLE),
                  Item(f"{prefix}/uv/{uv}/{check.name}", check, IMMUTABLE)]
    pinned = {}
    for script in ("install.sh", "install.ps1"):
        pinned[script] = work / script
        pinned[script].write_text(render(script, version, uv), encoding="utf-8")
        items.append(Item(f"{prefix}/{version}/{script}", pinned[script], IMMUTABLE))
    if not official(version):
        return items
    items += [Item(f"{prefix}/{script}", path, LATEST) for script, path in pinned.items()]
    manifest = work / "platform.json"
    manifest.write_text(json.dumps({
        "version": version, "min_desktop": MIN_DESKTOP,
        "sha256": {"install.sh": sha256(pinned["install.sh"]),
                   "install.ps1": sha256(pinned["install.ps1"]), "wheel": sha256(wheel)},
    }, indent=2) + "\n", encoding="utf-8")
    items.append(Item(f"{prefix}/platform.json", manifest, LATEST))
    if sign:
        items.append(Item(f"{prefix}/platform.json.sig", sign(manifest), LATEST))
    return items


def tauri_sign(path: Path) -> Path:
    """用更新器那把 key 签（外壳用内置的公钥验，spec §3）：ui/desktop 钉的 tauri CLI，key 与口令从
    环境变量来。签名写在旁边的 <文件>.sig。"""
    if not os.environ.get("TAURI_SIGNING_PRIVATE_KEY"):
        die("缺 TAURI_SIGNING_PRIVATE_KEY（更新器的私钥，CI 里是 secrets）")
    subprocess.run(["npx", "--no-install", "tauri", "signer", "sign", str(path)],
                   cwd=ROOT / "ui" / "desktop", check=True)
    return path.with_name(path.name + ".sig")


def client_from_env():
    """COS 的 client 与它会抛的、值得再试一次的错。凭据从环境变量来。"""
    from qcloud_cos import CosConfig, CosS3Client
    from qcloud_cos.cos_exception import CosClientError, CosServiceError

    client = CosS3Client(CosConfig(Region=REGION, SecretId=os.environ["TENCENTCLOUD_SECRET_ID"],
                                   SecretKey=os.environ["TENCENTCLOUD_SECRET_KEY"]))
    return client, (CosClientError, CosServiceError)


def upload(items: list[Item], client, *, retryable: tuple[type[BaseException], ...]) -> None:
    """一个个传。带版本号的（不可变）桶里已经有、大小一样就跳过：重跑流水线只补没传成的；最新那两份
    每次都传。传失败照 SDK 的说法再调（从断点续传），试够了照样抛。"""
    for key, path, cache in items:
        if cache == IMMUTABLE and _already_there(client, key, path):
            print(f"skip {CDN}/{key}（桶里已有，大小一样）")
            continue
        for attempt in range(1, UPLOAD_TRIES + 1):
            try:
                client.upload_file(Bucket=BUCKET, Key=key, LocalFilePath=str(path),
                                   ACL="public-read", CacheControl=cache,
                                   ContentType=TYPES.get(path.suffix, TEXT))
                break
            except retryable as exc:
                if attempt == UPLOAD_TRIES:
                    raise
                print(f"retry {attempt}/{UPLOAD_TRIES - 1} {key}：{exc}", file=sys.stderr)
                time.sleep(UPLOAD_WAIT_S * attempt)
        print(f"ok {CDN}/{key}")


def _already_there(client, key: str, path: Path) -> bool:
    if not client.object_exists(Bucket=BUCKET, Key=key):
        return False
    return int(client.head_object(Bucket=BUCKET, Key=key)["Content-Length"]) == path.stat().st_size


def purge(urls: list[str]) -> None:
    from tencentcloud.cdn.v20180606 import cdn_client, models
    from tencentcloud.common import credential

    cred = credential.Credential(os.environ["TENCENTCLOUD_SECRET_ID"],
                                 os.environ["TENCENTCLOUD_SECRET_KEY"])
    req = models.PurgeUrlsCacheRequest()
    req.Urls = urls
    task = cdn_client.CdnClient(cred, "").PurgeUrlsCache(req).TaskId
    print(f"ok 刷新 {len(urls)} 个地址的缓存（任务 {task}）")


def cmd_wheel(args: argparse.Namespace) -> int:
    with tempfile.TemporaryDirectory() as tmp:
        items = plan(args.tag.removeprefix("v"), args.prefix.rstrip("/"), Path(tmp),
                     sign=None if args.dry_run else tauri_sign)
        if args.dry_run:
            for key, path, cache in items:
                print(f"{CDN}/{key}\t{path.stat().st_size}\t{cache}")
            return 0
        client, retryable = client_from_env()
        upload(items, client, retryable=retryable)
    latest = [f"{CDN}/{key}" for key, _, cache in items if cache == LATEST]
    if latest:
        purge(latest)
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="把一行命令与桌面 App 要取的东西传到腾讯云 CDN")
    sub = ap.add_subparsers(dest="cmd", required=True)
    wheel = sub.add_parser("wheel", help="平台的 wheel、安装脚本、uv 的发布包、platform.json")
    wheel.add_argument("tag", help="vX.Y.Z 或 vX.Y.Z-rc.N")
    wheel.add_argument("--prefix", default=PREFIX, help=f"对象键前缀，缺省 {PREFIX}")
    wheel.add_argument("--dry-run", action="store_true", help="只列要传什么，不签")
    wheel.set_defaults(run=cmd_wheel)
    args = ap.parse_args(argv)
    return args.run(args)


if __name__ == "__main__":
    sys.exit(main())
