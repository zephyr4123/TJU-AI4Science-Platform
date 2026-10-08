"""设置那一整份里的助理状态（外层 #282）：页面只在 `needs_key` 时弹「填 DeepSeek 的 key」，
`cannot_talk` 只显示原因，`unchecked` 时页面在后台探一次。状态只从对话用的那家的 last_check 来：
算力自检没过、执行层那家没通都不许让页面弹 key 框（审查里点名的误弹）。

说话失败的原文取自真 CLI（2026-10-07，一把假的 DeepSeek key）：Codex 0.160.0 与
Claude Code 2.1.292。
"""

from __future__ import annotations

import pytest

from backends import AgentProbe
from compute import Probe
from framework import agents, computes, keys
from framework.chat import settings

INSTALLED = ("装了没", True, "/x")
VERSION = ("版本", True, "2.1.292 (Claude Code)")
KEY_IN = ("登录", True, "DeepSeek 的 key 已填")
CODEX_401 = ("退出码 1：Reconnecting... 1/5 (unexpected status 401 Unauthorized: Authentication "
             "Fails, Your api key: ****0000 is invalid (request_id: 84507a4b), url: "
             "https://api.deepseek.com/responses)")
CLAUDE_401 = ("退出码 1：Failed to authenticate. API Error: 401 Authentication Fails, Your api "
              "key: ****0000 is invalid (request_id: e70671ed)")


def _checked(name: str, *items: tuple[str, bool, str]) -> None:
    agents.record_check(name, AgentProbe(items=list(items), installed=True))


def test_never_checked_is_unchecked():
    got = settings.snapshot()["assistant"]
    assert got == {"agent": "claude_code", "provider": "official", "state": "unchecked",
                   "reason": None, "checked_at": None}


def test_a_chat_agent_that_spoke_is_ready():
    _checked("claude_code", INSTALLED, VERSION, KEY_IN, ("说话", True, "pong，1.2 秒"))
    got = settings.snapshot()["assistant"]
    assert got["state"] == "ready" and got["reason"] is None
    assert got["checked_at"] == agents.load().get("claude_code").last_check["at"]


@pytest.mark.parametrize("failed, reason", [
    (("登录", False, "DeepSeek 的 key 还没填：设置 → AI 里粘贴"),
     "DeepSeek 的 key 还没填：设置 → AI 里粘贴"),
    (("说话", False, CLAUDE_401), "DeepSeek 不认这把 key：换一把再试"),
    (("说话", False, CODEX_401), "DeepSeek 不认这把 key：换一把再试"),
])
def test_a_missing_or_rejected_key_needs_a_key(failed, reason):
    agents.use("claude_code", provider="deepseek")
    if failed[0] != "登录":
        keys.put("deepseek", "sk-bad")
    items = [INSTALLED, VERSION, failed] if failed[0] == "登录" else [INSTALLED, VERSION, KEY_IN,
                                                                     failed]
    _checked("claude_code", *items)
    got = settings.snapshot()["assistant"]
    assert (got["provider"], got["state"], got["reason"]) == ("deepseek", "needs_key", reason)


@pytest.mark.parametrize("note, reason", [
    ("退出码 1：API Error: 402 Insufficient Balance",
     "DeepSeek 余额不足：去 platform.deepseek.com 充值"),
    ("120 秒没回话", "120 秒没回话"),
    ("退出码 1：API Error: 429 rate_limit_error", "退出码 1：API Error: 429 rate_limit_error"),
    ("退出码 1：getaddrinfo ENOTFOUND api.deepseek.com",
     "退出码 1：getaddrinfo ENOTFOUND api.deepseek.com"),
    ("退出码 1：model 'm4010' not found", "退出码 1：model 'm4010' not found"),
])
def test_a_key_that_got_through_but_could_not_talk_is_not_asked_again(note, reason):
    """余额不足、超时、限流、断网：key 是对的，再弹「填 key」只会让人换一把好 key（审查 ②）。"""
    agents.use("claude_code", provider="deepseek")
    keys.put("deepseek", "sk-good")
    _checked("claude_code", INSTALLED, VERSION, KEY_IN, ("说话", False, note))
    got = settings.snapshot()["assistant"]
    assert (got["state"], got["reason"]) == ("cannot_talk", reason)


def test_an_uninstalled_cli_cannot_talk_with_the_probes_own_words():
    _checked("claude_code", ("装了没", False, "找不到 `claude`，终端里跑 `ai4sci setup` 装上"))
    got = settings.snapshot()["assistant"]
    assert (got["state"], got["reason"]) == ("cannot_talk",
                                             "找不到 `claude`，终端里跑 `ai4sci setup` 装上")


def test_only_the_chat_agent_counts_not_the_executor_or_the_computes():
    """算力自检没过（AutoDL 关机）、执行层那家没通，都不让页面弹 key 框（审查 ①）。"""
    _checked("claude_code", INSTALLED, VERSION, KEY_IN, ("说话", True, "pong"))
    agents.use("codex", roles=("executor",))
    _checked("codex", INSTALLED, ("登录", False, "平台里还没登录"))
    computes.add("box", "ssh", {"host": "10.0.0.9", "user": "me", "key": "~/.ssh/k", "root": "/r"})
    computes.record_check("box", Probe(items=[("连得上", False, "超时")]))
    snap = settings.snapshot()
    assert settings.problems(snap) == ["agent:codex", "compute:box"]
    assert snap["assistant"]["state"] == "ready"


def test_changing_or_removing_the_key_drops_the_old_verdict():
    """上次自检的结论是对着那把 key 下的（外层 #282 审查）：在设置里换了 key 不该还说「不认这把
    key」，删了 key 不该还说「就绪」、等下一轮对话才报缺 key。"""
    agents.use("claude_code", provider="deepseek")
    keys.put("deepseek", "sk-bad")
    _checked("claude_code", INSTALLED, VERSION, KEY_IN, ("说话", False, CLAUDE_401))
    assert settings.snapshot()["assistant"]["state"] == "needs_key"
    assert settings.put_key("deepseek", "sk-good")["assistant"]["state"] == "unchecked"
    _checked("claude_code", INSTALLED, VERSION, KEY_IN, ("说话", True, "pong"))
    assert settings.snapshot()["assistant"]["state"] == "ready"
    got = settings.remove_key("deepseek")["assistant"]
    assert (got["state"], got["reason"]) == ("needs_key",
                                             "DeepSeek 的 key 还没填：设置 → AI 里粘贴")


def test_a_custom_endpoint_moved_elsewhere_is_checked_again():
    agents.use("claude_code", provider="custom", base_url="https://a.example/v1", models=("m1",))
    _checked("claude_code", INSTALLED, VERSION, KEY_IN, ("说话", True, "pong"))
    agents.use("claude_code", base_url="https://b.example/v1")
    assert agents.load().get("claude_code").last_check is None


@pytest.mark.parametrize("provider, key, failed, reason", [
    ("kimi", "kimi", ("说话", False, CLAUDE_401), "Kimi 不认这把 key：设置 → AI 里换一把"),
    ("kimi", None, ("登录", False, "Kimi 的 key 还没填"), "Kimi 的 key 还没填：设置 → AI 里粘贴"),
])
def test_another_key_provider_is_not_offered_the_deepseek_dialog(provider, key, failed, reason):
    """「填 DeepSeek 的 key」那扇窗试通会把两家都切到 DeepSeek：助理用的是 Kimi 这类别的要 key 的
    供应商时不弹它（needs_key），原因说去设置里改（外层 #282 审查）。"""
    agents.use("claude_code", provider=provider)
    if key:
        keys.put(key, "sk-bad")
    _checked("claude_code", INSTALLED, VERSION, KEY_IN, failed)
    got = settings.snapshot()["assistant"]
    assert (got["state"], got["reason"]) == ("cannot_talk", reason)


def test_the_subscription_never_signed_in_is_offered_deepseek_but_an_expired_one_is_not():
    """官方订阅没 key：第一次打开还没登录过，填一把 DeepSeek 的 key 最快（needs_key）；登录过期说话
    时 401，是去终端重新登录，不是填 DeepSeek 的 key（外层 #282 审查）。"""
    _checked("claude_code", INSTALLED, VERSION, ("登录", False, "平台里还没登录"))
    assert settings.snapshot()["assistant"]["state"] == "needs_key"
    _checked("claude_code", INSTALLED, VERSION, ("登录", True, "已登录"),
             ("说话", False, "退出码 1：API Error: 401 OAuth token has expired. Please run /login"))
    got = settings.snapshot()["assistant"]
    assert got["state"] == "cannot_talk"
    login = agents.login_hint("claude_code")
    assert got["reason"] == f"Claude 订阅：登录过期了，终端里运行 {login}"
