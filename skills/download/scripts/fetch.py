# /// script
# requires-python = ">=3.12"
# dependencies = [
#     "huggingface-hub>=0.30",
# ]
# ///
"""把材料拉到工作区（skill `download`，契约在 SKILL.md）：git 仓库 / 单个文件 / Hugging Face 仓库。

裸命令包一层：git 走系统的 git，文件走标准库，HF 走 huggingface_hub。没有智能——该拉什么是调用方
（研究助理和研究者）定的；这里只保证三件事：落在说好的目录、不覆盖已有的、留一张收据
（来源、commit / sha256、多少文件多少字节、许可证文件在不在）。收据一行 JSON 到 stdout，同一份写进
`<out>/.ai4sci-download.json`，之后哪颗能力拿到这个目录都知道它从哪来。

退出码：0 成；2 参数不对、目录已存在、git 不在；3 网络或远端的错；4 校验不过（sha256、commit）。
token 只读环境变量 HF_TOKEN，绝不收参数（密钥不进 argv）。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

EXIT_OK = 0
EXIT_USAGE = 2
EXIT_NETWORK = 3
EXIT_MISMATCH = 4

RECEIPT_NAME = ".ai4sci-download.json"
MATERIALS_DIRNAME = "materials"
LICENSE_NAMES = ("LICENSE", "LICENSE.md", "LICENSE.txt", "COPYING", "LICENCE")
_CHUNK = 1 << 20


def _fail(code: int, message: str) -> None:
    print(f"download: {message}", file=sys.stderr)
    raise SystemExit(code)


def _prepare_out(out: str | None, default_name: str) -> Path:
    """落盘目录：给了 --out 用它，不给就是 materials/<缺省名>；已存在就退 2，不覆盖。"""
    target = Path(out) if out else Path(MATERIALS_DIRNAME) / default_name
    if target.exists():
        _fail(EXIT_USAGE, f"目录已存在，不覆盖：{target}（换个 --out，或删掉再拉）")
    target.parent.mkdir(parents=True, exist_ok=True)
    return target


def _tally(directory: Path) -> tuple[int, int]:
    files = bytes_ = 0
    for path in directory.rglob("*"):
        if path.is_file() and ".git" not in path.relative_to(directory).parts:
            files += 1
            bytes_ += path.stat().st_size
    return files, bytes_


def _license(directory: Path) -> str | None:
    for name in LICENSE_NAMES:
        if (directory / name).is_file():
            return name
    return None


def _receipt(out: Path, doc: dict) -> None:
    receipt = {**doc, "out": str(out)}
    (out / RECEIPT_NAME).write_text(json.dumps(receipt, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(receipt, ensure_ascii=False))


def _git(args: list[str], *, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=False)


def cmd_git(args: argparse.Namespace) -> int:
    if shutil.which("git") is None:
        _fail(EXIT_USAGE, "系统里没有 git")
    default = args.url.rstrip("/").rsplit("/", 1)[-1].removesuffix(".git") or "repo"
    out = _prepare_out(args.out, default)
    clone = _git(["clone", "--quiet", args.url, str(out)])
    if clone.returncode != 0:
        shutil.rmtree(out, ignore_errors=True)
        _fail(EXIT_NETWORK, f"clone 失败：{clone.stderr.strip()[-800:]}")
    if args.commit:
        checkout = _git(["checkout", "--quiet", "--detach", args.commit], cwd=out)
        if checkout.returncode != 0:
            shutil.rmtree(out, ignore_errors=True)
            _fail(EXIT_MISMATCH,
                  f"commit {args.commit!r} 不在这个仓库里：{checkout.stderr.strip()[-400:]}")
    head = _git(["rev-parse", "HEAD"], cwd=out).stdout.strip()
    files, bytes_ = _tally(out)
    _receipt(out, {"kind": "git", "source": args.url, "commit": head, "files": files,
                   "bytes": bytes_, "license": _license(out)})
    return EXIT_OK


def cmd_file(args: argparse.Namespace) -> int:
    name = args.name or args.url.rstrip("/").rsplit("/", 1)[-1].split("?", 1)[0] or "download"
    out = _prepare_out(args.out, Path(name).stem)
    out.mkdir()
    target = out / name
    digest = hashlib.sha256()
    size = 0
    try:
        with urllib.request.urlopen(args.url, timeout=60) as resp, target.open("wb") as fh:
            while chunk := resp.read(_CHUNK):
                fh.write(chunk)
                digest.update(chunk)
                size += len(chunk)
    except (urllib.error.URLError, OSError, ValueError) as exc:
        shutil.rmtree(out, ignore_errors=True)
        _fail(EXIT_NETWORK, f"下载失败：{exc}")
    sha = digest.hexdigest()
    if args.sha256 and sha != args.sha256.lower():
        shutil.rmtree(out, ignore_errors=True)
        _fail(EXIT_MISMATCH, f"sha256 对不上：期望 {args.sha256}，实际 {sha}；文件已删")
    _receipt(out, {"kind": "file", "source": args.url, "sha256": sha, "bytes": size,
                   "file": name})
    return EXIT_OK


def cmd_hf(args: argparse.Namespace) -> int:
    try:
        import huggingface_hub
    except ImportError as exc:
        _fail(EXIT_USAGE, f"huggingface_hub 不在脚本环境里（{exc}）：起服务的人跑 make skills 预热")
        raise AssertionError("不可达") from exc
    out = _prepare_out(args.out, args.repo.rsplit("/", 1)[-1])
    token = os.environ.get("HF_TOKEN") or os.environ.get("HUGGING_FACE_HUB_TOKEN")
    try:
        info = huggingface_hub.HfApi(token=token).repo_info(
            args.repo, repo_type=args.type, revision=args.revision)
        huggingface_hub.snapshot_download(
            args.repo, repo_type=args.type, revision=info.sha, local_dir=str(out), token=token)
    except huggingface_hub.errors.HfHubHTTPError as exc:  # 401 / 403 / 404 都在这
        shutil.rmtree(out, ignore_errors=True)
        _fail(EXIT_NETWORK, f"Hugging Face 拒绝或找不到 {args.repo}（{args.type}）：{exc}")
    except OSError as exc:
        shutil.rmtree(out, ignore_errors=True)
        _fail(EXIT_NETWORK, f"下载失败：{exc}")
    files, bytes_ = _tally(out)
    _receipt(out, {"kind": "hf", "source": args.repo, "type": args.type, "commit": info.sha,
                   "files": files, "bytes": bytes_, "license": _license(out)})
    return EXIT_OK


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="ai4sci skill run download",
        description="把材料拉到工作区：git 仓库 / 单个文件 / Hugging Face 仓库；只下载、留收据。")
    sub = parser.add_subparsers(dest="kind", required=True)
    git = sub.add_parser("git", help="clone 一个 git 仓库，可切到指定 commit")
    git.add_argument("url")
    git.add_argument("--commit", default="", help="sha 或 tag；不给就是默认分支最新")
    git.add_argument("--out", default=None, help="落到哪个目录；缺省 materials/<仓库名>")
    git.set_defaults(func=cmd_git)
    file = sub.add_parser("file", help="下载一个文件，可校验 sha256")
    file.add_argument("url")
    file.add_argument("--sha256", default="", help="期望的 sha256（十六进制）；给了就校验")
    file.add_argument("--name", default="", help="落盘的文件名；缺省用链接末尾那段")
    file.add_argument("--out", default=None, help="落到哪个目录；缺省 materials/<文件名>")
    file.set_defaults(func=cmd_file)
    hf = sub.add_parser("hf", help="拉 Hugging Face 上的数据集或模型（私有的读 HF_TOKEN）")
    hf.add_argument("repo", help="<org>/<name>")
    hf.add_argument("--type", default="model", choices=("model", "dataset"))
    hf.add_argument("--revision", default=None, help="分支、tag 或 commit；缺省 main")
    hf.add_argument("--out", default=None, help="落到哪个目录；缺省 materials/<name>")
    hf.set_defaults(func=cmd_hf)
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
