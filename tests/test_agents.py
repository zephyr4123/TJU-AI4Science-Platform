"""按人的底座清单 `agents.yaml`（纲领 P-25）：读写点只在 `framework/agents.py`。
文件不在就是每家用起点；
值要在那家清单上，不在整份报错；两层各用哪家；自检结果记回。清单由注入的 `knobs` 报（测试里是假的）
。
"""

from __future__ import annotations

import pytest
import yaml

from backends import AgentProbe, BackendNotFound, Choice, Knobs, Tuning
from framework import agents

FAKE = {
    "claude_code": Knobs(models=(Choice("a", "甲"), Choice("b", "乙")),
                         efforts=(Choice("low", "低"), Choice("high", "高")),
                         model="a", effort="low"),
    "codex": Knobs(models=(Choice("g1", "G1"),), efforts=(Choice("medium", "中"),),
                   model="g1", effort="medium"),
}


def fake_knobs(name: str) -> Knobs:
    try:
        return FAKE[name]
    except KeyError:
        raise BackendNotFound(name) from None


def test_missing_file_means_every_backend_at_its_start_and_claude_for_both_roles(tmp_path):
    assert not agents.path().exists()
    registry = agents.load(fake_knobs)
    assert set(registry.entries) == {"claude_code", "codex"}
    assert registry.get("codex").tuning == Tuning(model="g1", effort="medium")
    assert registry.chat == registry.executor == "claude_code"
    assert agents.role_backend("executor", fake_knobs) == "claude_code"
    assert agents.tuning_for("claude_code", fake_knobs) == Tuning(model="a", effort="low")
    with pytest.raises(BackendNotFound, match="没有叫 'nope' 的 agent；有：claude_code, codex"):
        registry.get("nope")


def test_use_writes_roles_and_defaults_and_checks_them_against_the_list():
    entry = agents.use("codex", roles=("executor",), knobs=fake_knobs)
    assert entry.model == "g1" and agents.path().is_file()
    entry = agents.use("claude_code", model="b", knobs=fake_knobs)
    assert entry.model == "b" and entry.effort == "low"
    registry = agents.load(fake_knobs)
    assert registry.executor == "codex" and registry.chat == "claude_code"
    assert registry.get("claude_code").tuning == Tuning(model="b", effort="low")
    with pytest.raises(ValueError, match="模型 'zz' 不在清单上；可选：a, b"):
        agents.use("claude_code", model="zz", knobs=fake_knobs)
    assert agents.load(fake_knobs).get("claude_code").model == "b"  # 没写坏
    with pytest.raises(AssertionError, match="role 只认"):
        agents.use("codex", roles=("boss",), knobs=fake_knobs)
    doc = yaml.safe_load(agents.path().read_text(encoding="utf-8"))
    assert doc == {"chat": "claude_code", "executor": "codex",
                   "agents": {"claude_code": {"provider": "official", "model": "b",
                                              "effort": "low"},
                              "codex": {"provider": "official", "model": "g1",
                                        "effort": "medium"}}}


@pytest.mark.parametrize("text, why", [
    ("chat: nope\n", "chat = 'nope' 不是一家适配器"),
    ("agents:\n  gemini: {model: x}\n", "没有这家适配器"),
    ("agents:\n  claude_code: {model: zz}\n", "模型 'zz' 不在清单上"),
    ("agents:\n  claude_code: {model: 3}\n", "model 与 effort 要是字符串"),
    ("agents:\n  claude_code: [1]\n", "要是键值对"),
    ("agents:\n  claude_code: {provider: groq}\n", "Claude Code 没有叫 'groq' 的供应商"),
    ("agents:\n  codex: {provider: custom}\n", "自定义供应商要填地址和至少一个模型名"),
    ("- a\n", "顶层要是键值对"),
    ("a: [\n", "不是合法 YAML"),
])
def test_bad_file_fails_whole_not_half(text, why):
    agents.path().parent.mkdir(parents=True, exist_ok=True)
    agents.path().write_text(text, encoding="utf-8")
    with pytest.raises(agents.AgentsInvalid, match=why):
        agents.load(fake_knobs)


def test_record_check_keeps_the_probe_with_a_timestamp():
    probe = AgentProbe(items=[("装了没", True, "/usr/bin/x"), ("登录", False, "没登录")],
                       installed=True, version="1.0.0")
    entry = agents.record_check("codex", probe, fake_knobs)
    assert entry.last_check["ok"] is False and entry.last_check["version"] == "1.0.0"
    assert entry.last_check["at"].startswith("20") and entry.last_check["cost_usd"] is None
    reloaded = agents.load(fake_knobs).get("codex")
    assert reloaded.last_check["items"][1] == {"name": "登录", "ok": False, "note": "没登录"}
    assert reloaded.summary().endswith("\tofficial\tg1\tmedium\t检查未过")
    assert agents.load(fake_knobs).get("claude_code").summary().endswith("\t未检查")


def test_real_knobs_come_from_the_adapters():
    registry = agents.load()
    assert registry.get("claude_code").tuning == Tuning(model="sonnet", effort="medium")
    assert registry.get("codex").tuning == Tuning(model="gpt-6.1-sol", effort="medium")
    assert registry.get("codex").title == "Codex"


def test_switching_provider_brings_its_own_models_and_the_link_its_key():
    """外层 #266：模型跟着供应商走——换成 DeepSeek，模型回到它的起点，Opus 选不了；Link 带上家里那把
    key，没填就是 None（适配器起会话时说清楚）。"""
    from framework import keys

    entry = agents.use("claude_code", provider="deepseek")
    assert (entry.provider, entry.model, entry.effort) == ("deepseek", "deepseek-flash", "medium")
    assert [c.id for c in agents.knobs_of("claude_code").models] == ["deepseek-flash",
                                                                     "deepseek-v4-pro"]
    with pytest.raises(ValueError, match="模型 'opus' 不在清单上"):
        agents.use("claude_code", model="opus")
    assert agents.link("claude_code").key is None
    keys.put("deepseek", "sk-deepseek-0000")
    link = agents.link("claude_code")
    assert (link.provider, link.key) == ("deepseek", "sk-deepseek-0000")
    assert agents.link("claude_code", provider="official").key is None  # 老对话照它记的接
    entry = agents.use("claude_code", provider="official")
    assert (entry.provider, entry.model) == ("official", "sonnet")


def test_custom_provider_takes_an_address_and_model_names():
    entry = agents.use("codex", provider="custom", base_url=" https://llm.lab/v1 ",
                       models=("qwen3-coder", " "))
    assert (entry.provider, entry.base_url, entry.models, entry.model) == \
        ("custom", "https://llm.lab/v1", ("qwen3-coder",), "qwen3-coder")
    doc = yaml.safe_load(agents.path().read_text(encoding="utf-8"))["agents"]["codex"]
    assert doc["base_url"] == "https://llm.lab/v1" and doc["models"] == ["qwen3-coder"]
    assert agents.link("codex").base_url == "https://llm.lab/v1"
