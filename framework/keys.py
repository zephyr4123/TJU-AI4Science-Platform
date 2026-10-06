"""平台的 key：家里 `keys.yaml` 的唯一读写点（外层 #263 / #265）。

主人 2026-10-06：key 不走环境变量——要照顾花 10 块钱跑通的人，在设置页粘贴就能用；也要能一把清除，
所以和平台别的私有东西一起放在家里。文件只有本人能读（0600），读到别人也能读就当场收紧、记一行日志。

一个名字一把 key：供应商（`deepseek`、`kimi`、`anthropic`、`openai`）、`openalex`（文献检索的额度，
纲领 P-27）、自定义供应商 `custom.<家>`。值只在这里读，交给要用的那一个子进程（适配器）或请求头
（OpenAlex）；页面上只有末四位（`masked`），接口从不把整把 key 吐回去。不读用户 shell 里的环境变量：
同名的变量设了也不认，不然平台的家清了、key 还在别处起作用。
"""

from __future__ import annotations

import logging
import re
import stat
from pathlib import Path

import yaml

from framework import files, paths

LOGGER = logging.getLogger("ai4sci.keys")
NAME_RE = re.compile(r"[a-z0-9][a-z0-9_.-]*")
MODE = 0o600
TAIL = 4


class KeysInvalid(ValueError):
    """名字或值不合规矩、文件不合形状：一句话给人看。"""


def path() -> Path:
    return paths.keys_file()


def load() -> dict[str, str]:
    """整份读出来；没有文件是空的。别人也能读就先收紧权限。"""
    file = path()
    if not file.is_file():
        return {}
    if stat.S_IMODE(file.stat().st_mode) & 0o077:
        file.chmod(MODE)
        LOGGER.warning("keys_file_tightened path=%s", file)
    try:
        raw = yaml.safe_load(file.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        raise KeysInvalid(f"{file}: 不是合法 YAML：{exc}") from exc
    if not isinstance(raw, dict):
        raise KeysInvalid(f"{file}: 顶层要是键值对（名字: key）")
    return {str(k): str(v) for k, v in raw.items() if v is not None}


def get(name: str) -> str | None:
    """一把 key；没有是 None。"""
    return load().get(name)


def put(name: str, value: str) -> None:
    """存一把（换掉同名的）。粘贴带进来的首尾空白去掉。"""
    if not NAME_RE.fullmatch(name):
        raise KeysInvalid(f"名字只认小写英文、数字、点、下划线、连字符：{name!r}")
    value = value.strip()
    if not value:
        raise KeysInvalid(f"{name} 的 key 是空的")
    found = load()
    found[name] = value
    _save(found)
    LOGGER.info("key_saved name=%s", name)


def remove(name: str) -> None:
    """删一把；本来就没有也算删了。"""
    found = load()
    if found.pop(name, None) is not None:
        _save(found)
        LOGGER.info("key_removed name=%s", name)


def tail(value: str) -> str:
    """给人看的末四位；太短的一位都不露。"""
    return f"…{value[-TAIL:]}" if len(value) > 2 * TAIL else "…"


def masked() -> dict[str, str]:
    """页面看的那份：名字 → 末四位。"""
    return {name: tail(value) for name, value in load().items()}


def _save(found: dict[str, str]) -> None:
    header = ("# ai4sci 的 key（外层 #263）：只有本人能读，在设置页填；清除平台的家时一起删。\n"
              "# 名字: key。别提交、别贴给人。\n")
    files.write_atomic(path(), header + yaml.safe_dump(found, allow_unicode=True, sort_keys=True),
                       mode=MODE)
