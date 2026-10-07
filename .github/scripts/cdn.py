# /// script
# requires-python = ">=3.12"
# dependencies = [
#     "cos-python-sdk-v5==1.9.44",
#     "tencentcloud-sdk-python-cdn==3.1.169",
# ]
# ///
"""cdn.py X.Y.Z —— 把一行命令要取的东西传到腾讯云 CDN（外层 #277）。

一行命令（`install/install.sh`）全程国内源：平台的 wheel、安装脚本、uv 的发布包都从我们自己的 CDN 取
（Claude Code 闭源不转发，平台装它时从 npmmirror 取）。发版流水线在 `make package` 之后跑这一步：

    ai4science/dist/<版本>/ai4sci-<版本>-py3-none-any.whl(.sha256)   不可变，长缓存
    ai4science/dist/<版本>/install.sh                                  钉版本装
    ai4science/dist/uv/<uv 版本>/uv-<平台>.tar.gz|zip(.sha256)          uv 官方发布包的原样副本
    ai4science/dist/install.sh、install.ps1                            最新版；短缓存，传完刷 CDN

预发布（-rc.N）只传带版本号的，不动最新那两份。uv 的版本照 uv.lock（平台依赖的那一版），从 GitHub
取、对它自己的 .sha256。凭据从环境变量来（TENCENTCLOUD_SECRET_ID / _KEY，CI 里是 secrets，只能写
这个前缀、能刷 CDN 的子账号）；`--prefix` 换前缀先在测试目录里真验一遍，`--dry-run` 只列不传。
"""

from __future__ import annotations

import argparse
import hashlib
import os
import re
import sys
import tempfile
import tomllib
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
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


def plan(version: str, prefix: str, work: Path) -> list[tuple[str, Path, str]]:
    """（对象键、本地文件、Cache-Control）一份清单；sha256 当场核对，不对就停。"""
    items: list[tuple[str, Path, str]] = []
    wheel = ROOT / "dist" / f"ai4sci-{version}-py3-none-any.whl"
    if not wheel.is_file():
        die(f"没有 {wheel}：先 make package VERSION={version}")
    side = wheel.with_name(wheel.name + ".sha256")
    if side.read_text(encoding="utf-8").split()[0] != sha256(wheel):
        die(f"{side.name} 与 wheel 对不上")
    items += [(f"{prefix}/{version}/{wheel.name}", wheel, IMMUTABLE),
              (f"{prefix}/{version}/{side.name}", side, IMMUTABLE)]
    uv = uv_version()
    for name in UV_ARCHIVES:
        archive = fetch(f"{UV_RELEASES}/{uv}/uv-{name}", work / f"uv-{name}")
        check = fetch(f"{UV_RELEASES}/{uv}/uv-{name}.sha256", work / f"uv-{name}.sha256")
        if check.read_text(encoding="utf-8").split()[0] != sha256(archive):
            die(f"uv-{name} 与 GitHub 上的 .sha256 对不上")
        items += [(f"{prefix}/uv/{uv}/{archive.name}", archive, IMMUTABLE),
                  (f"{prefix}/uv/{uv}/{check.name}", check, IMMUTABLE)]
    pinned = work / "install.sh"
    pinned.write_text(render("install.sh", version, uv), encoding="utf-8")
    items.append((f"{prefix}/{version}/install.sh", pinned, IMMUTABLE))
    if not re.search(r"-rc\.\d+$", version):  # 预发布不动最新那两份
        items.append((f"{prefix}/install.sh", pinned, LATEST))
        latest_ps1 = work / "install.ps1"
        latest_ps1.write_text(render("install.ps1", version, uv), encoding="utf-8")
        items.append((f"{prefix}/install.ps1", latest_ps1, LATEST))
    return items


def upload(items: list[tuple[str, Path, str]]) -> None:
    from qcloud_cos import CosConfig, CosS3Client

    client = CosS3Client(CosConfig(Region=REGION, SecretId=os.environ["TENCENTCLOUD_SECRET_ID"],
                                   SecretKey=os.environ["TENCENTCLOUD_SECRET_KEY"]))
    for key, path, cache in items:
        client.upload_file(Bucket=BUCKET, Key=key, LocalFilePath=str(path), ACL="public-read",
                           CacheControl=cache, ContentType=TYPES.get(path.suffix, TEXT))
        print(f"ok {CDN}/{key}")


def purge(urls: list[str]) -> None:
    from tencentcloud.cdn.v20180606 import cdn_client, models
    from tencentcloud.common import credential

    cred = credential.Credential(os.environ["TENCENTCLOUD_SECRET_ID"],
                                 os.environ["TENCENTCLOUD_SECRET_KEY"])
    req = models.PurgeUrlsCacheRequest()
    req.Urls = urls
    task = cdn_client.CdnClient(cred, "").PurgeUrlsCache(req).TaskId
    print(f"ok 刷新 {len(urls)} 个地址的缓存（任务 {task}）")


def main() -> int:
    ap = argparse.ArgumentParser(description="把一行命令要取的东西传到腾讯云 CDN（外层 #277）")
    ap.add_argument("version", help="X.Y.Z 或 X.Y.Z-rc.N")
    ap.add_argument("--prefix", default=PREFIX, help=f"对象键前缀，缺省 {PREFIX}；先验可换测试目录")
    ap.add_argument("--dry-run", action="store_true", help="只列要传什么")
    args = ap.parse_args()
    version = args.version.removeprefix("v")
    with tempfile.TemporaryDirectory() as tmp:
        items = plan(version, args.prefix.rstrip("/"), Path(tmp))
        if args.dry_run:
            for key, path, cache in items:
                print(f"{CDN}/{key}\t{path.stat().st_size}\t{cache}")
            return 0
        upload(items)
    latest = [f"{CDN}/{key}" for key, _, cache in items if cache == LATEST]
    if latest:
        purge(latest)
    return 0


if __name__ == "__main__":
    sys.exit(main())
