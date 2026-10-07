"""平台的 key（外层 #263 / #265）：家里的 keys.yaml，只有本人能读；页面只见末四位；不读环境变量。"""

from __future__ import annotations

import os
import stat
import subprocess

import pytest

from framework import keys, paths


def _only_the_owner_can_read(file) -> bool:
    """POSIX 看权限位 0600；Windows 看 ACL：不继承、只有一条（本人）。"""
    if os.name != "nt":
        return stat.S_IMODE(file.stat().st_mode) == 0o600
    acl = subprocess.run(["icacls", str(file)], capture_output=True, check=True).stdout
    return acl.count(b":(") == 1 and b"(I)" not in acl


def test_keys_round_trip_in_the_home_and_only_the_owner_can_read_them():
    assert keys.load() == {}
    keys.put("deepseek", " sk-abcdef0123456789 ")
    keys.put("openalex", "oa-key-1234")
    file = paths.keys_file()
    assert _only_the_owner_can_read(file)
    assert keys.get("deepseek") == "sk-abcdef0123456789"  # 粘贴带的空白去掉
    assert keys.load() == {"deepseek": "sk-abcdef0123456789", "openalex": "oa-key-1234"}
    keys.remove("openalex")
    assert keys.get("openalex") is None
    keys.remove("openalex")  # 幂等


def test_the_page_only_ever_sees_the_last_four():
    keys.put("deepseek", "sk-abcdef0123456789")
    assert keys.masked() == {"deepseek": "…6789"}
    assert keys.tail("abc") == "…"  # 太短的不露


@pytest.mark.skipif(os.name == "nt", reason="Windows 上靠写的时候设的 ACL，读时不看权限位")
def test_a_file_someone_else_can_read_is_tightened_on_read(caplog):
    keys.put("kimi", "sk-kimi-0000")
    paths.keys_file().chmod(0o644)
    assert keys.get("kimi") == "sk-kimi-0000"
    assert stat.S_IMODE(paths.keys_file().stat().st_mode) == 0o600
    assert "keys_file_tightened" in caplog.text


def test_bad_names_values_and_shapes_are_refused(monkeypatch):
    with pytest.raises(keys.KeysInvalid, match="名字"):
        keys.put("Deep Seek", "x")
    with pytest.raises(keys.KeysInvalid, match="空"):
        keys.put("deepseek", "   ")
    paths.keys_file().write_text("- a\n- b\n", encoding="utf-8")
    with pytest.raises(keys.KeysInvalid, match="键值对"):
        keys.load()
    # 环境变量里有同名的也不读：key 只在家里（外层 #263）
    paths.keys_file().write_text("{}\n", encoding="utf-8")
    monkeypatch.setenv("OPENALEX_API_KEY", "from-shell")
    assert keys.get("openalex") is None
