"""Codex 适配器（外层 #131）：
夹具 `fixtures/codex_stream_sample.jsonl` 是 2026-09-22 本机 spike 真实录下的一段
`codex exec --json`（codex-cli 0.147.0：跑了五条命令、写了一个文件、报了网络不通）。
不连网的用例只吃夹具、
tmp_path 与一个假的 `codex` 脚本；真 CLI 的冒烟 `AI4SCI_LIVE=1` 才跑。
"""

from __future__ import annotations

import json
import math
import os
import stat
import tomllib
from pathlib import Path

import pytest

from backends import AgentProbe, Chat, Runner, Tuning, available_backends, get_backend, get_chat
from backends import codex as cx
from backends import probe as probe_backend

FIXTURE = Path(__file__).parent / "fixtures" / "codex_stream_sample.jsonl"


@pytest.fixture
def home(tmp_path, monkeypatch) -> Path:
    """私有 CODEX_HOME 指到 tmp；「真的」~/.codex 也伪造一份，auth.json 在里面。"""
    real = tmp_path / "real-codex"
    real.mkdir()
    (real / cx.AUTH_NAME).write_text("{}", encoding="utf-8")
    monkeypatch.setenv(cx.REAL_HOME_ENV, str(real))
    monkeypatch.setenv(cx.HOME_ENV, str(tmp_path / "private-home"))
    monkeypatch.setattr(cx, "USER_SKILLS", tmp_path / "no-user-skills")
    monkeypatch.setattr(cx, "ADMIN_SKILLS", tmp_path / "no-admin-skills")
    return cx.codex_home("executor")


# --- 端口 ---------------------------------------------------------------------


def test_codex_is_a_registered_backend_with_both_ports():
    assert "codex" in available_backends()
    runner, chat = get_backend("codex"), get_chat("codex")
    assert isinstance(runner, Runner) and isinstance(chat, Chat)
    assert runner.name == "codex" and chat.name == "codex" and chat.cost_reporting == "turn"
    knobs = chat.knobs()
    assert knobs.model == "gpt-5.6-terra" and knobs.effort == "medium"
    assert [c.id for c in knobs.efforts] == ["low", "medium", "high", "xhigh"]
    with pytest.raises(ValueError, match="思考深度 'ultra' 不在清单上"):
        knobs.check(Tuning(effort="ultra"))  # sol / terra 另有 max、ultra，清单不收：luna 没有


# --- 私有 CODEX_HOME 与要关的 skill ------------------------------------------------


def test_codex_home_symlinks_the_real_auth_and_never_copies_it(home: Path, tmp_path, monkeypatch):
    assert home == tmp_path / "private-home" / "executor"  # 一层一个 home（规则按 home 放）
    link = home / cx.AUTH_NAME
    assert link.is_symlink() and link.readlink() == tmp_path / "real-codex" / cx.AUTH_NAME
    assert cx.codex_home("executor") == home  # 幂等
    # 协调层就是根：老对话的 rollout 在那儿
    assert cx.codex_home("chat") == tmp_path / "private-home"
    assert (tmp_path / "private-home" / cx.AUTH_NAME).is_symlink()
    with pytest.raises(AssertionError, match="层只有"):
        cx.codex_home("probe")
    # 真 home 换了地方：软链跟着改
    other = tmp_path / "other-codex"
    other.mkdir()
    monkeypatch.setenv(cx.REAL_HOME_ENV, str(other))
    assert cx.codex_home("executor").joinpath(cx.AUTH_NAME).readlink() == other / cx.AUTH_NAME
    # 私有 home 里出现一份普通文件的凭据副本：当场炸，不悄悄用
    link.unlink()
    link.write_text("{}", encoding="utf-8")
    with pytest.raises(AssertionError, match="不该有凭据副本"):
        cx.codex_home("executor")


def test_skill_off_paths_lists_every_skill_md_under_the_scanned_roots(home: Path, tmp_path):
    system = home / "skills" / ".system"
    for name in ("imagegen", "skill-creator"):
        (system / name).mkdir(parents=True)
        (system / name / "SKILL.md").write_text("---\nname: x\n---\n", encoding="utf-8")
    (system / "not-a-skill").mkdir()
    cwd = tmp_path / "ws" / "deep"
    repo = tmp_path / "ws" / ".agents" / "skills" / "mine"
    repo.mkdir(parents=True)
    (repo / "SKILL.md").write_text("", encoding="utf-8")
    cwd.mkdir(parents=True)
    found = cx.skill_off_paths(home, cwd)
    assert system / "imagegen" / "SKILL.md" in found
    assert system / "skill-creator" / "SKILL.md" in found
    assert repo / "SKILL.md" in found  # cwd 往上每级的 .agents/skills
    assert all(p.name == "SKILL.md" for p in found)
    assert not [p for p in found if "not-a-skill" in str(p)]


def test_toml_str_is_a_valid_basic_string_for_guides():
    guide = "你是研究助理。\n规则：一条命令一行 \"ai4sci …\"，反斜杠 \\ 与 DEL \x7f 也行。"
    encoded = cx.toml_str(guide)
    assert tomllib.loads(f"x = {encoded}")["x"] == guide


def test_parse_version():
    assert cx.parse_version("codex-cli 0.147.0\n") == (0, 147, 0)
    assert cx.parse_version("0.155.1") == (0, 155, 1)
    assert cx.parse_version("") is None and cx.parse_version("codex-cli nope") is None


# --- argv 组装 -------------------------------------------------------------------


def _config(argv: list[str]) -> dict[str, str]:
    """`-c key=value` 那一串拆成表。"""
    pairs = [argv[i + 1] for i, a in enumerate(argv) if a == "-c"]
    return dict(p.split("=", 1) for p in pairs)


def test_runner_argv_is_ephemeral_sandboxed_and_lists_writable_roots(home: Path, tmp_path):
    (home / "skills" / ".system" / "imagegen").mkdir(parents=True)
    (home / "skills" / ".system" / "imagegen" / "SKILL.md").write_text("", encoding="utf-8")
    cwd = tmp_path / "pack"
    (cwd / "harness").mkdir(parents=True)
    argv = cx.CodexRunner().build_argv(cwd, [cwd / "harness"], ("ai4sci skill",),
                                       Tuning(model="gpt-5.6-luna", effort="low"), home=home)
    assert argv[:2] == ["codex", "exec"] and argv[-1] == "-"  # prompt 走 stdin
    for flag in ("--json", "--ephemeral", "--skip-git-repo-check", "--ignore-user-config"):
        assert flag in argv
    assert "--ignore-rules" not in argv  # 规则要读：ai4sci 在沙箱外跑靠它
    rules = (home / "rules" / cx.RULES_NAME).read_text(encoding="utf-8")
    assert 'prefix_rule(pattern=["ai4sci", "skill"], decision="allow"' in rules
    assert argv[argv.index("-C") + 1] == str(cwd.resolve())
    assert argv[argv.index("-m") + 1] == "gpt-5.6-luna"
    config = _config(argv)
    assert config["approval_policy"] == '"never"' and config["project_doc_max_bytes"] == "0"
    assert config["web_search"] == '"live"' and config["sandbox_mode"] == '"workspace-write"'
    assert "sandbox_workspace_write.network_access" not in config  # 联网的都走沙箱外的 ai4sci
    assert config["model_reasoning_effort"] == '"low"'
    roots = tomllib.loads(f"r = {config['sandbox_workspace_write.writable_roots']}")["r"]
    assert roots == [str((cwd / "harness").resolve())]  # 只许改的目录，不加平台的目录
    off = tomllib.loads(f"s = {config['skills.config']}")["s"]
    assert off == [{"path": str(home / "skills" / ".system" / "imagegen" / "SKILL.md"),
                    "enabled": False}]
    assert "developer_instructions" not in config  # 执行层的提示整段走 stdin，没有指南
    assert "--dangerously-bypass-approvals-and-sandbox" not in argv and "--yolo" not in argv


def test_chat_argv_opens_with_the_guide_and_resumes_by_thread_id(home: Path, tmp_path):
    chat = cx.CodexChat()
    common = dict(system_prompt="你是研究助理。\n一条命令一行。", allowed_paths=[tmp_path],
                  bash_rules=("ai4sci", ".venv/bin/ai4sci"),
                  tuning=Tuning(model="gpt-5.5", effort="high"), home=home)
    first = chat.build_argv(tmp_path, session_id=None, **common)
    second = chat.build_argv(tmp_path, session_id="01a0-thread", **common)
    assert "--ephemeral" not in first and "--ephemeral" not in second  # 续接要 rollout 落盘
    assert first[argv_index(first, "-C") + 1] == str(tmp_path.resolve())
    guide = tomllib.loads(f"d = {_config(first)['developer_instructions']}")["d"]
    assert guide == common["system_prompt"]
    # resume 形态：没有 -C / --color / developer_instructions，线程 id 在 prompt 的 `-` 前面
    assert second[:3] == ["codex", "exec", "resume"] and second[-2:] == ["01a0-thread", "-"]
    assert "-C" not in second and "--color" not in second
    assert "developer_instructions" not in _config(second)
    rules = (home / "rules" / cx.RULES_NAME).read_text(encoding="utf-8")
    assert 'pattern=["ai4sci"]' in rules and 'pattern=[".venv/bin/ai4sci"]' in rules
    for argv in (first, second):
        config = _config(argv)
        assert config["sandbox_mode"] == '"workspace-write"'
        assert str(tmp_path.resolve()) in config["sandbox_workspace_write.writable_roots"]
        assert argv[argv.index("-m") + 1] == "gpt-5.5"
        assert config["model_reasoning_effort"] == '"high"'


def argv_index(argv: list[str], flag: str) -> int:
    return argv.index(flag)


def test_codex_home_ignores_an_inherited_codex_home_that_is_itself(home: Path, tmp_path,
                                                                    monkeypatch):
    """助理 --detach 起的作业跑在上一层会话的 shell 里，
    环境里的 CODEX_HOME 是我们给那一层的私有 home：
    照它算「真的」就把 auth.json 软链指向自己（实测 401）。指到自己的不算数，退回 ~/.codex；已经指向
    自己的死链也要重连。"""
    chat_home = tmp_path / "private-home"
    monkeypatch.setenv(cx.REAL_HOME_ENV, str(chat_home))  # 上一层（协调层）留下的
    fake_home = tmp_path / "fake-user-home"
    (fake_home / ".codex").mkdir(parents=True)
    (fake_home / ".codex" / cx.AUTH_NAME).write_text("{}", encoding="utf-8")
    monkeypatch.setattr(Path, "home", staticmethod(lambda: fake_home))
    link = home / cx.AUTH_NAME
    link.unlink()
    link.symlink_to(link)  # 演练里留下的死链：auth.json -> auth.json
    assert cx.codex_home("executor") == home
    assert link.readlink() == fake_home / ".codex" / cx.AUTH_NAME  # 私有根下的一律不算
    assert link.is_file()


def test_tool_guide_names_the_allowed_commands():
    text = cx.CodexRunner().tool_guide(("ai4sci skill",))
    assert "## 工具怎么用" in text and "`ai4sci skill …`" in text and "apply_patch" in text
    assert "一条都不跑" in cx.tool_guide(())
    # 协调层那段：这家没有单独的读文件工具，看文件就是 shell 的只读命令；指南只在开线程时送到
    chat = cx.CodexChat()
    assert chat.guide_channel == "thread"
    text = chat.tool_guide(("ai4sci",))
    assert "ls、cat" in text and "`ai4sci …`" in text and "不算「运行动作」" in text


# --- 事件翻译 --------------------------------------------------------------------


def test_translator_maps_the_real_stream(home: Path):
    lines = FIXTURE.read_text(encoding="utf-8").splitlines(keepends=True)
    translator = cx.Translator(started=0.0)
    events = [e for line in lines for e in translator.feed(line)]
    kinds = [e.kind for e in events]
    assert kinds[0] == "init" and events[0].session_id == "01a0c6fb-fe16-7241-8627-b96d25ae6cfb"
    assert kinds[-1] == "done" and translator.finished
    # 五条命令各一对 tool_use / tool_result，外加一条非致命的 item 错误也算 tool_result
    assert kinds.count("tool_use") == 5 and kinds.count("tool_result") == 6
    shell = next(e for e in events if e.kind == "tool_use")
    assert shell.tool == "shell" and shell.tool_input["command"].startswith("/bin/zsh -lc")
    results = [e for e in events if e.kind == "tool_result"]
    assert results[0].is_error and "Skill descriptions" in results[0].text  # item.type=error 留一行
    assert "AI4SCI_CHAT_ID=chat-spike" in results[1].text and not results[1].is_error
    done = events[-1]
    assert math.isnan(done.cost_usd) and done.exit_code == 0
    assert done.text.startswith("1. `pwd` succeeded")
    assert done.raw["usage"]["input_tokens"] == 126147
    assert all(e.session_id == events[0].session_id for e in events)


def test_translator_reports_one_error_for_error_plus_turn_failed():
    lines = [
        '{"type":"thread.started","thread_id":"t1"}\n',
        '{"type":"turn.started"}\n',
        '{"type":"error","message":"The \'gpt-nope\' model is not supported"}\n',
        '{"type":"turn.failed","error":{"message":"The \'gpt-nope\' model is not supported"}}\n',
    ]
    translator = cx.Translator(started=0.0)
    events = [e for line in lines for e in translator.feed(line)]
    assert [e.kind for e in events] == ["init", "error"]
    assert events[1].is_error and events[1].exit_code == 1 and "gpt-nope" in events[1].text
    assert translator.finished
    # 只有顶层 error、流就断了（被中断）：finished 仍是 False，fatal 留着给收尾用
    cut = cx.Translator(started=0.0)
    for line in lines[:3]:
        cut.feed(line)
    assert not cut.finished and cut.fatal == "The 'gpt-nope' model is not supported"


def test_translator_maps_file_change_web_search_and_mcp():
    raw = [
        {"type": "item.completed", "item": {"id": "i1", "type": "file_change",
                                            "status": "completed",
                                            "changes": [{"path": "harness/launcher.sh",
                                                         "kind": "add"}]}},
        {"type": "item.started", "item": {"id": "exec-1", "type": "web_search", "query": "",
                                          "action": {"type": "other"}}},
        {"type": "item.completed", "item": {"id": "exec-1", "type": "web_search",
                                            "query": "site:arxiv.org 2609.01558",
                                            "action": {"type": "search",
                                                       "query": "site:arxiv.org 2609.01558"}}},
        {"type": "item.started", "item": {"id": "i3", "type": "mcp_tool_call", "server": "pdf",
                                          "tool": "parse", "arguments": {"path": "a.pdf"},
                                          "status": "in_progress"}},
        {"type": "item.completed", "item": {"id": "i3", "type": "mcp_tool_call", "server": "pdf",
                                            "tool": "parse", "arguments": {"path": "a.pdf"},
                                            "status": "failed",
                                            "error": {"message": "no such file"}}},
        {"type": "item.updated", "item": {"id": "i4", "type": "todo_list", "items": []}},
        {"type": "item.completed", "item": {"id": "i5", "type": "reasoning", "text": "thinking"}},
    ]
    lines = [json.dumps(e) + "\n" for e in raw] + ["not json\n"]
    translator = cx.Translator(started=0.0)
    events = [e for line in lines for e in translator.feed(line)]
    assert [(e.kind, e.tool) for e in events] == [
        ("tool_use", "apply_patch"), ("tool_result", ""), ("tool_use", "web_search"),
        ("tool_use", "pdf.parse"), ("tool_result", "")]
    assert events[0].tool_input == {"changes": ["add harness/launcher.sh"]}
    assert events[2].tool_input == {"query": "site:arxiv.org 2609.01558", "action": "search"}
    assert events[4].is_error and events[4].text == "no such file"


def test_parse_events_and_final_report():
    events, junk = cx.parse_events(FIXTURE.read_text(encoding="utf-8").splitlines(keepends=True))
    assert junk == [] and events[0]["type"] == "thread.started"
    assert cx.final_report(events).startswith("1. `pwd` succeeded")
    assert cx.final_report([]) == ""


# --- 假 CLI：run() 与 probe() 的整条路 ----------------------------------------------


def _fake_codex(directory: Path, *, logged_in: bool = True,
                version: str = "codex-cli 0.147.0") -> Path:
    """一个装成 codex 的脚本：`--version`、`login status`、`exec`（读完 stdin、往 cwd 写一个文件、
    吐事件，JSON 一行一个）。"""
    directory.mkdir(parents=True, exist_ok=True)
    script = directory / "codex"
    events = [
        {"type": "thread.started", "thread_id": "fake-thread"},
        {"type": "turn.started"},
        {"type": "item.started", "item": {"id": "item_0", "type": "command_execution",
                                          "command": "pwd", "aggregated_output": "",
                                          "exit_code": None, "status": "in_progress"}},
        {"type": "item.completed", "item": {"id": "item_0", "type": "command_execution",
                                            "command": "pwd", "aggregated_output": "/tmp",
                                            "exit_code": 0, "status": "completed"}},
        {"type": "item.completed", "item": {"id": "item_1", "type": "agent_message",
                                            "text": "pong"}},
        {"type": "turn.completed", "usage": {"input_tokens": 12, "cached_input_tokens": 0,
                                             "cache_write_input_tokens": 0, "output_tokens": 3,
                                             "reasoning_output_tokens": 0}},
    ]
    stream = "\n".join(json.dumps(e) for e in events)
    script.write_text(f"""#!/bin/sh
if [ "$1" = "--version" ]; then echo "{version}"; exit 0; fi
if [ "$1" = "login" ]; then
  if [ "{int(logged_in)}" = "1" ]; then echo "Logged in using ChatGPT" >&2; exit 0; fi
  echo "Not logged in" >&2; exit 1
fi
cat > /dev/null
mkdir -p out && printf hello > out/hello.txt
cat <<'EOF'
{stream}
EOF
echo "some warning" >&2
""", encoding="utf-8")
    script.chmod(script.stat().st_mode | stat.S_IXUSR)
    return script


def test_runner_run_reports_changed_files_report_and_nan_cost(home: Path, tmp_path):
    cli = _fake_codex(tmp_path / "bin")
    cwd = tmp_path / "pack"
    (cwd / "out").mkdir(parents=True)
    result = cx.CodexRunner(cli=str(cli)).run("写点东西", cwd, 30, [cwd / "out"], ("ai4sci skill",),
                                            tuning=Tuning(model="gpt-5.6-luna"))
    assert result.exit_code == 0 and not result.timed_out
    assert result.changed_files == ["out/hello.txt"]  # 框架自己的快照 diff，不信 CLI 自报
    assert result.report == "pong" and math.isnan(result.cost_usd) and result.duration_s > 0
    assert [e["type"] for e in result.events][-1] == "turn.completed"
    assert "some warning" in result.stdout_tail
    logs = sorted((cwd / ".ai4sci").glob("executor-*"))
    assert [p.suffix for p in logs] == [".jsonl", ".log"]  # 事件流与 stderr 各一份留档


def test_probe_walks_the_four_questions(home: Path, tmp_path):
    cli = _fake_codex(tmp_path / "bin")
    result = cx.probe(cli=str(cli))
    assert isinstance(result, AgentProbe) and result.ok and result.installed and result.logged_in
    assert result.version == "codex-cli 0.147.0" and result.spoke_s > 0
    assert math.isnan(result.cost_usd)
    assert [n for n, _, _ in result.items] == ["装了没", "版本", "登录", "说话"]
    assert "15 tokens" in result.items[-1][2]
    doc = result.to_dict()
    assert doc["ok"] and doc["cost_usd"] is None and doc["items"][3]["name"] == "说话"

    stale = _fake_codex(tmp_path / "old", version="codex-cli 0.140.2")
    result = cx.probe(cli=str(stale))
    assert not result.ok and [ok for _, ok, _ in result.items] == [True, False]
    assert "要 ≥ 0.147.0" in result.items[1][2]

    logged_out = _fake_codex(tmp_path / "out", logged_in=False)
    result = cx.probe(cli=str(logged_out))
    assert not result.ok and not result.logged_in and "codex login" in result.items[2][2]

    missing = cx.probe(cli=str(tmp_path / "nope" / "codex"))
    assert not missing.installed and not missing.ok and "装 Codex CLI" in missing.items[0][2]


def test_probe_is_reachable_through_the_port(home: Path, monkeypatch, tmp_path):
    """`backends.probe("codex")` 调的是模块级 `probe()`：形状对不上要在端口那层炸。"""
    cli = _fake_codex(tmp_path / "bin")
    real = cx.probe
    monkeypatch.setattr(cx, "probe", lambda: real(cli=str(cli)))
    assert probe_backend("codex").ok
    monkeypatch.setattr(cx, "probe", lambda: "nope")
    with pytest.raises(AssertionError, match="没有返回 AgentProbe"):
        probe_backend("codex")


# --- 真 CLI ---------------------------------------------------------------------


@pytest.mark.skipif(os.environ.get("AI4SCI_LIVE") != "1", reason="真 codex CLI，AI4SCI_LIVE=1 才跑")
def test_live_probe_runner_and_two_turn_chat(tmp_path: Path, monkeypatch):
    monkeypatch.delenv(cx.REAL_HOME_ENV, raising=False)  # 用本机真的 ~/.codex 登录态
    result = cx.probe()
    assert result.ok, result.items
    ws = tmp_path / "ws"
    (ws / "out").mkdir(parents=True)
    ask = "Write the single word hello into out/hello.txt, then reply exactly: wrote"
    run = cx.CodexRunner().run(ask, ws, 180, [ws / "out"], ("ai4sci skill",),
                               tuning=Tuning(model="gpt-5.6-luna", effort="low"))
    assert run.exit_code == 0 and run.changed_files == ["out/hello.txt"] and run.report == "wrote"
    chat = cx.CodexChat()
    common = dict(allowed_paths=[ws], bash_rules=("ai4sci",),
                  tuning=Tuning(model="gpt-5.6-luna", effort="low"))
    first = list(chat.turn("Remember the word: kiwi. Reply only: ok", ws, 180, session_id=None,
                           system_prompt="你是海盗，每句结尾加 arr。", **common))
    sid = first[0].session_id
    assert first[0].kind == "init" and sid and first[-1].kind == "done"
    second = list(chat.turn("What was the word? Reply with just the word.", ws, 180,
                            session_id=sid, system_prompt="", **common))
    assert second[-1].kind == "done" and "kiwi" in second[-1].text.lower()
    assert all(e.session_id == sid for e in second)
