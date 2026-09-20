"""按人的算力清单：`~/.config/ai4sci/computes.yaml` 的唯一读写点（纲领 P-23 算力归人）。

一份文件列出「我有哪几台机器」，永远不进 git、不进工作区、不进数据根——同一台服务器不同的人、
同一个人不同的服务器都有，只能按人隔离。`AI4SCI_COMPUTES` 可指向别处（测试、多套配置）。
出厂自带 `local`（本机），删不掉、也不用写进文件。

一条记录只有 kind 与连接参数：`ssh` 是 host / port / user / key（密钥**路径**）/ root（远端根），
没有 password 这个字段——只认密钥，`_FORBIDDEN` 断言守着。上一次探测的结果（`last_check`）
也记在这里：产出的 meta 记机器出处（主机名、GPU）时不用再连一次。

agent 面前只有名字：`ai4sci show computes` 给名字与状态，`--compute <名字>` 选，
`instance(name)` 把记录翻成适配器；名字对不上抛 ComputeNotFound，绝不静默退回本机（P-7）。
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

from compute import Compute, ComputeNotFound, Probe, get_compute

PATH_ENV = "AI4SCI_COMPUTES"
DEFAULT_PATH = Path.home() / ".config" / "ai4sci" / "computes.yaml"
LOCAL = "local"
KINDS = ("local", "ssh")
# 每种算力允许的连接参数；这里没有的键一律拒（password 这类进不来）
PARAMS = {"local": (), "ssh": ("host", "port", "user", "key", "root")}
REQUIRED = {"local": (), "ssh": ("host", "user", "key", "root")}
_FORBIDDEN = ("password", "passwd", "pass", "secret", "token")
DEFAULT_SSH_PORT = 22


class ComputesInvalid(ValueError):
    """文件不合形状：问题一行一条。"""


@dataclass
class Entry:
    name: str
    kind: str
    params: dict[str, Any] = field(default_factory=dict)
    last_check: dict[str, Any] | None = None

    def label(self) -> dict[str, Any]:
        """写进产出 meta 的出处：名字、种类、主机名、GPU（上次探测记的）。"""
        check = self.last_check or {}
        return {"name": self.name, "kind": self.kind,
                "hostname": check.get("hostname", ""), "gpu": check.get("gpu", "")}

    def summary(self) -> str:
        """`show computes` 的一行：名字、种类、去向、GPU、上次探测过没过。"""
        where = (f"{self.params.get('user')}@{self.params.get('host')}:"
                 f"{self.params.get('port', DEFAULT_SSH_PORT)}") if self.kind == "ssh" else "本机"
        check = self.last_check
        state = "未探测" if not check else ("可用" if check.get("ok") else "探测未过")
        gpu = (check or {}).get("gpu") or "无 GPU"
        return f"{self.name}\t{self.kind}\t{where}\t{gpu}\t{state}"


@dataclass
class Registry:
    entries: dict[str, Entry]
    default: str = LOCAL

    def get(self, name: str) -> Entry:
        try:
            return self.entries[name]
        except KeyError:
            raise ComputeNotFound(
                f"没有叫 {name!r} 的算力；有：{', '.join(self.entries)}"
                f"（接一台：ai4sci compute add）") from None


def path() -> Path:
    raw = os.environ.get(PATH_ENV)
    return Path(raw).expanduser() if raw else DEFAULT_PATH


def load() -> Registry:
    """读文件；不存在就只有 local。形状不对整份报错，不带着半份清单往下走。"""
    registry = Registry(entries={LOCAL: Entry(LOCAL, "local")})
    file = path()
    if not file.is_file():
        return registry
    try:
        raw = yaml.safe_load(file.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        raise ComputesInvalid(f"{file}: 不是合法 YAML：{exc}") from exc
    if not isinstance(raw, dict):
        raise ComputesInvalid(f"{file}: 顶层要是键值对")
    problems: list[str] = []
    for name, doc in (raw.get("computes") or {}).items():
        entry, why = _parse_entry(str(name), doc)
        if entry is None:
            problems.append(f"{file}: computes.{name}: {why}")
            continue
        if name == LOCAL and entry.kind != "local":
            problems.append(f"{file}: computes.local 只能是 local")
            continue
        registry.entries[str(name)] = entry
    default = raw.get("default", LOCAL)
    if default not in registry.entries:
        problems.append(f"{file}: default {default!r} 不在清单里")
    else:
        registry.default = str(default)
    if problems:
        raise ComputesInvalid("\n".join(problems))
    return registry


def save(registry: Registry) -> Path:
    """写回（local 不写，它是出厂的）；目录不在就建。"""
    file = path()
    file.parent.mkdir(parents=True, exist_ok=True)
    doc: dict[str, Any] = {"computes": {}, "default": registry.default}
    for name, entry in registry.entries.items():
        if name == LOCAL:
            continue
        item: dict[str, Any] = {"kind": entry.kind, **entry.params}
        if entry.last_check:
            item["last_check"] = entry.last_check
        doc["computes"][name] = item
    header = ("# ai4sci 的算力清单（纲领 P-23）：按人、不进 git；只有 SSH、只认密钥。\n"
              "# 由 ai4sci compute add / check / remove 维护；手改也行：kind + 连接参数。\n")
    text = header + yaml.safe_dump(doc, allow_unicode=True, sort_keys=False)
    file.write_text(text, encoding="utf-8")
    return file


def _parse_entry(name: str, doc: Any) -> tuple[Entry | None, str]:
    if not isinstance(doc, dict):
        return None, "要是键值对"
    kind = doc.get("kind")
    if kind not in KINDS:
        return None, f"kind 只认 {KINDS}，得到 {kind!r}"
    params = {k: v for k, v in doc.items() if k not in ("kind", "last_check")}
    bad = [k for k in params if any(word in str(k).lower() for word in _FORBIDDEN)]
    if bad:
        return None, f"不收密码这类字段：{bad}（只认密钥：key 写密钥路径）"
    extra = sorted(set(params) - set(PARAMS[kind]))
    if extra:
        return None, f"{kind} 只认 {list(PARAMS[kind])}，多了 {extra}"
    missing = [k for k in REQUIRED[kind] if not params.get(k)]
    if missing:
        return None, f"{kind} 缺 {missing}"
    if kind == "ssh":
        params.setdefault("port", DEFAULT_SSH_PORT)
        if not isinstance(params["port"], int) or not 0 < params["port"] < 65536:
            return None, f"port 要是端口号，得到 {params['port']!r}"
    check = doc.get("last_check")
    if check is not None and not isinstance(check, dict):
        return None, "last_check 要是键值对"
    return Entry(name=name, kind=kind, params=params, last_check=check), ""


def instance(name: str, registry: Registry | None = None) -> Compute:
    """名字 → 适配器。"""
    entry = (registry or load()).get(name)
    return get_compute(entry.kind, **entry.params)


def default_name() -> str:
    return load().default


def add(name: str, kind: str, params: dict[str, Any]) -> Entry:
    """加（同名覆盖——AutoDL 关机重开端口会变）；不探测，探测由调用方做完再 `record_check`。"""
    if name == LOCAL:
        raise ComputesInvalid("local 是出厂自带的，不用加")
    entry, why = _parse_entry(name, {"kind": kind, **params})
    if entry is None:
        raise ComputesInvalid(f"{name}: {why}")
    registry = load()
    registry.entries[name] = entry
    save(registry)
    return entry


def remove(name: str) -> None:
    if name == LOCAL:
        raise ComputesInvalid("local 是出厂自带的，删不掉")
    registry = load()
    registry.get(name)
    del registry.entries[name]
    if registry.default == name:
        registry.default = LOCAL
    save(registry)


def set_default(name: str) -> None:
    registry = load()
    registry.get(name)
    registry.default = name
    save(registry)


def record_check(name: str, probe: Probe) -> Entry:
    """探测结果记回文件（local 不落盘，每次现探）。"""
    registry = load()
    entry = registry.get(name)
    entry.last_check = {**probe.to_dict(), "at": datetime.now(UTC).isoformat(timespec="seconds")}
    if name != LOCAL:
        save(registry)
    return entry
