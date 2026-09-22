"""`ai4sci compute add <名字> --ssh user@host[:port] --key <密钥路径> [--root <远端目录>]
| check <名字> | list | remove <名字> | default <名字>`：接机器（纲领 P-23 算力归人）。

在 cli 层。清单在按人的 `~/.config/ai4sci/computes.yaml`（`framework.computes`）；只有 SSH、只认
密钥。
`add` 写进文件后就地探测（连接、Python、uv 缺就装、GPU、磁盘、rsync）并一行一项打出来；探测不过
也只是报告、记录照留，退出码说探测过没过。助理能跑这几条：人只给 ssh 那一行与密钥路径，
主机、端口、密钥路径都不是秘密。`list` 与 `ai4sci show computes` 是同一份。
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from compute import ComputeNotFound, Probe
from framework import computes
from framework.cli._common import EXIT_INVALID, EXIT_OK, EXIT_USAGE

_SSH_RE = re.compile(r"^(?P<user>[A-Za-z0-9._-]+)@(?P<host>[A-Za-z0-9.-]+)(?::(?P<port>\d{1,5}))?$")
DEFAULT_ROOT = "~/ai4sci"


def add_and_check(name: str, ssh: str, key: str, root: str = DEFAULT_ROOT,
                  default: bool = False) -> tuple[computes.Entry, Probe]:
    """接一台机器：ssh 那一行拆开、密钥要在、写进清单、就地探测、记回。CLI 与页面「设置」共用；
    参数不对是 ValueError（ComputesInvalid 也是），调用方各自翻成退出码或 400。"""
    match = _SSH_RE.match(ssh)
    if not match:
        raise ValueError(f"--ssh 要写成 user@host 或 user@host:port，得到 {ssh!r}")
    key_path = Path(key).expanduser()
    if not key_path.is_file():
        raise ValueError(f"密钥文件不存在：{key_path}"
                         "（只认密钥，不收密码；先把公钥贴到那台机器上）")
    params = {"host": match["host"], "user": match["user"],
              "port": int(match["port"] or computes.DEFAULT_SSH_PORT),
              "key": str(key_path), "root": root or DEFAULT_ROOT}
    entry = computes.add(name, "ssh", params)
    probe = computes.instance(entry.name).check()
    computes.record_check(entry.name, probe)
    if default:
        computes.set_default(entry.name)
    return entry, probe


def cmd_add(args: argparse.Namespace) -> int:
    try:
        entry, probe = add_and_check(args.name, args.ssh, args.key, args.root, args.default)
    except ValueError as exc:  # 含 ComputesInvalid
        print(str(exc), file=sys.stderr)
        return EXIT_USAGE
    _print_probe(probe)
    state = "可用" if probe.ok else "探测没过，记录留着"
    print(f"ok {entry.name}\t{state}\t写入 {computes.path()}"
          + ("\tdefault" if args.default else ""))
    return EXIT_OK if probe.ok else EXIT_INVALID


def cmd_check(args: argparse.Namespace) -> int:
    try:
        probe = computes.instance(args.name).check()
    except (ComputeNotFound, computes.ComputesInvalid) as exc:
        print(str(exc), file=sys.stderr)
        return EXIT_USAGE
    computes.record_check(args.name, probe)
    _print_probe(probe)
    print(f"ok {args.name}\t{'可用' if probe.ok else '探测没过'}")
    return EXIT_OK if probe.ok else EXIT_INVALID


def cmd_list(args: argparse.Namespace) -> int:
    try:
        registry = computes.load()
    except computes.ComputesInvalid as exc:
        print(str(exc), file=sys.stderr)
        return EXIT_INVALID
    for entry in registry.entries.values():
        star = "\t(缺省)" if entry.name == registry.default else ""
        print(entry.summary() + star)
    return EXIT_OK


def cmd_remove(args: argparse.Namespace) -> int:
    try:
        computes.remove(args.name)
    except (ComputeNotFound, computes.ComputesInvalid) as exc:
        print(str(exc), file=sys.stderr)
        return EXIT_USAGE
    print(f"ok {args.name}\tremoved")
    return EXIT_OK


def cmd_default(args: argparse.Namespace) -> int:
    try:
        computes.set_default(args.name)
    except (ComputeNotFound, computes.ComputesInvalid) as exc:
        print(str(exc), file=sys.stderr)
        return EXIT_USAGE
    print(f"ok {args.name}\tdefault")
    return EXIT_OK


def _print_probe(probe: Probe) -> None:
    for name, ok, note in probe.items:
        print(f"  {'✓' if ok else '✗'} {name}\t{note}")


def add_parser(groups: argparse._SubParsersAction) -> None:
    group = groups.add_parser("compute", help="算力：接一台机器、探一遍、清单、删、设缺省")
    actions = group.add_subparsers(dest="action", required=True)
    adding = actions.add_parser("add", help="接一台能 ssh 上去的机器：写进清单并就地探测")
    adding.add_argument("name", help="给它起的名字（之后 --compute 用），小写英文数字连字符")
    adding.add_argument("--ssh", required=True, help="user@host 或 user@host:port")
    adding.add_argument("--key", required=True, help="本机私钥路径（只认密钥，不收密码）")
    adding.add_argument("--root", default=DEFAULT_ROOT,
                        help=f"远端放任务的根目录，缺省 {DEFAULT_ROOT}"
                             "（AutoDL 建议 /root/autodl-tmp/ai4sci）")
    adding.add_argument("--default", action="store_true", help="接上就设成缺省算力")
    adding.set_defaults(func=cmd_add)
    checking = actions.add_parser("check", help="再探一遍（关机重开、换了端口之后）")
    checking.add_argument("name")
    checking.set_defaults(func=cmd_check)
    listing = actions.add_parser("list", help="清单：名字、种类、去向、GPU、状态")
    listing.set_defaults(func=cmd_list)
    removing = actions.add_parser("remove", help="删一条")
    removing.add_argument("name")
    removing.set_defaults(func=cmd_remove)
    defaulting = actions.add_parser("default", help="设缺省算力（--compute 不给时用它）")
    defaulting.add_argument("name")
    defaulting.set_defaults(func=cmd_default)
