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
import tomllib
from dataclasses import replace
from pathlib import Path

import pytest

from backends import (
    AgentProbe,
    Chat,
    Link,
    Runner,
    Tuning,
    available_backends,
    get_backend,
    get_chat,
)
from backends import codex as cx
from backends import probe as probe_backend
from tests.fixtures.fake_cli import fake_cli

FIXTURE = Path(__file__).parent / "fixtures" / "codex_stream_sample.jsonl"


from framework import paths  # noqa: E402

# 真 CLI 的测试用平台家里那份私有目录（要先在平台里登录过，外层 #263）
LIVE_LINK = Link(home=paths.DEFAULT_HOME / "codex")


@pytest.fixture
def link(tmp_path, monkeypatch) -> Link:
    """平台家里 Codex 的私有目录指到 tmp，根上一份 auth.json（平台自己登录过）。"""
    root = tmp_path / "private-home"
    root.mkdir()
    (root / cx.AUTH_NAME).write_text("{}", encoding="utf-8")
    monkeypatch.setattr(cx, "USER_SKILLS", tmp_path / "no-user-skills")
    monkeypatch.setattr(cx, "ADMIN_SKILLS", tmp_path / "no-admin-skills")
    return Link(home=root)


@pytest.fixture
def home(link: Link) -> Path:
    """执行层那一层的 home。"""
    return cx.codex_home(link, "executor")


# --- 端口 ---------------------------------------------------------------------


def test_codex_is_a_registered_backend_with_both_ports(tmp_path):
    assert "codex" in available_backends()
    link = Link(home=tmp_path / "codex")
    runner, chat = get_backend("codex", link), get_chat("codex", link)
    assert isinstance(runner, Runner) and isinstance(chat, Chat)
    assert runner.name == "codex" and chat.name == "codex" and chat.cost_reporting == "turn"
    knobs = chat.knobs()
    assert knobs.model == "gpt-6.1-sol" and knobs.effort == "medium"
    assert [c.id for c in knobs.models] == ["gpt-6.1-sol", "gpt-6-astra", "gpt-6-luna",
                                            "gpt-5.6-terra"]
    assert [c.id for c in knobs.efforts] == ["low", "medium", "high", "xhigh"]
    with pytest.raises(ValueError, match="思考深度 'ultra' 不在清单上"):
        knobs.check(Tuning(effort="ultra"))  # sol / astra 另有 max、ultra，清单不收：luna 没有


# --- 私有 CODEX_HOME 与要关的 skill ------------------------------------------------


@pytest.mark.skipif(os.name == "nt", reason="Windows 上执行层是硬链接，下一条在两边都测")
def test_codex_home_shares_the_platform_login_between_layers(link: Link, home: Path, tmp_path):
    """外层 #263：登录是平台自己的（根上的 auth.json），执行层软链到它——一次登录两层用；
    不再软链用户的 ~/.codex。"""
    assert home == tmp_path / "private-home" / "executor"  # 一层一个 home（规则按 home 放）
    auth = home / cx.AUTH_NAME
    assert auth.is_symlink() and auth.readlink() == link.home / cx.AUTH_NAME
    assert cx.codex_home(link, "executor") == home  # 幂等
    # 协调层就是根：老对话的 rollout 在那儿，登录也在那儿
    assert cx.codex_home(link, "chat") == link.home
    assert not (link.home / cx.AUTH_NAME).is_symlink()
    with pytest.raises(AssertionError, match="层只有"):
        cx.codex_home(link, "probe")
    # 旧版本留下的软链（指到用户的 ~/.codex）：重连到平台自己的
    auth.unlink()
    auth.symlink_to(tmp_path / "old-user-codex" / cx.AUTH_NAME)
    assert cx.codex_home(link, "executor").joinpath(cx.AUTH_NAME).readlink() == \
        link.home / cx.AUTH_NAME
    # 执行层里出现一份普通文件的凭据：当场炸，不悄悄用
    auth.unlink()
    auth.write_text("{}", encoding="utf-8")
    with pytest.raises(AssertionError, match="不该有自己的凭据"):
        cx.codex_home(link, "executor")


def test_a_hardlinked_login_follows_the_root_through_logout_and_login(tmp_path):
    """Windows 上执行层的 auth.json 是根上那份的硬链接（软链要管理员，外层 #210）：Codex 刷新 token
    原地重写，两层同一份；登出删了根上那份、再登录是新文件，执行层要跟上，不能留着旧 token。"""
    real, auth = tmp_path / "auth.json", tmp_path / "executor" / "auth.json"
    auth.parent.mkdir()
    cx._hardlink_login(real, auth)  # 根上还没登录：执行层也没有
    assert not auth.exists()
    real.write_text('{"token": 1}', encoding="utf-8")
    cx._hardlink_login(real, auth)
    assert os.path.samefile(auth, real)
    with real.open("r+", encoding="utf-8") as f:  # 刷新 token：原地截断重写
        f.truncate(0)
        f.write('{"token": 2}')
    assert auth.read_text(encoding="utf-8") == '{"token": 2}'
    real.unlink()  # 登出再登录：根上换了一个新文件
    real.write_text('{"token": 3}', encoding="utf-8")
    cx._hardlink_login(real, auth)
    assert os.path.samefile(auth, real) and auth.read_text(encoding="utf-8") == '{"token": 3}'
    assert sorted(p.name for p in auth.parent.iterdir()) == ["auth.json"]


def test_login_and_logout_run_in_the_platform_codex_home(link: Link):
    argv, env = cx.login_command(link)
    assert argv[1:] == ["login"] and env["CODEX_HOME"] == str(link.home)
    argv, env = cx.logout_command(link)
    assert argv[1:] == ["logout"] and env["CODEX_HOME"] == str(link.home)


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


def test_runner_argv_is_ephemeral_sandboxed_and_lists_writable_roots(link: Link, home: Path,
                                                                    tmp_path):
    (home / "skills" / ".system" / "imagegen").mkdir(parents=True)
    (home / "skills" / ".system" / "imagegen" / "SKILL.md").write_text("", encoding="utf-8")
    cwd = tmp_path / "pack"
    (cwd / "harness").mkdir(parents=True)
    argv = cx.CodexRunner(link).build_argv(cwd, [cwd / "harness"], ("ai4sci skill",),
                                       Tuning(model="gpt-6-luna", effort="low"), home=home)
    assert argv[:2] == ["codex", "exec"] and argv[-1] == "-"  # prompt 走 stdin
    for flag in ("--json", "--ephemeral", "--skip-git-repo-check"):
        assert flag in argv
    assert "--ignore-rules" not in argv  # 规则要读：ai4sci 在沙箱外跑靠它
    rules = (home / "rules" / cx.RULES_NAME).read_text(encoding="utf-8")
    assert 'prefix_rule(pattern=["ai4sci", "skill"], decision="allow"' in rules
    assert argv[argv.index("-C") + 1] == str(cwd.resolve())
    assert argv[argv.index("-m") + 1] == "gpt-6-luna"
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


def test_chat_argv_opens_with_the_guide_and_resumes_by_thread_id(link: Link, home: Path,
                                                                  tmp_path):
    chat = cx.CodexChat(link)
    common = dict(system_prompt="你是研究助理。\n一条命令一行。", allowed_paths=[tmp_path],
                  bash_rules=("ai4sci", ".venv/bin/ai4sci"),
                  tuning=Tuning(model="gpt-5.6-terra", effort="high"), home=home)
    first = chat.build_argv(tmp_path, session_id=None, **common)
    second = chat.build_argv(tmp_path, session_id="01a0-thread", **common)
    assert "--ephemeral" not in first and "--ephemeral" not in second  # 续接要 rollout 落盘
    assert first[argv_index(first, "-C") + 1] == str(tmp_path.resolve())
    # 指南在私有 home 里按内容命名的 profile 里，`-p` 叠上去；不放命令行（Windows 一条命令行
    # 32767 个字符，外层 #210）
    profile = home / f"{first[argv_index(first, '-p') + 1]}.config.toml"
    guide = tomllib.loads(profile.read_text(encoding="utf-8"))["developer_instructions"]
    assert guide == common["system_prompt"] and "developer_instructions" not in _config(first)
    assert (home / cx.CONFIG_NAME).read_text(encoding="utf-8").startswith("#")  # 基础配置留空
    # resume 形态：没有 -C / --color / 指南，线程 id 在 prompt 的 `-` 前面
    assert second[:3] == ["codex", "exec", "resume"] and second[-2:] == ["01a0-thread", "-"]
    assert "-C" not in second and "--color" not in second and "-p" not in second
    rules = (home / "rules" / cx.RULES_NAME).read_text(encoding="utf-8")
    assert 'pattern=["ai4sci"]' in rules and 'pattern=[".venv/bin/ai4sci"]' in rules
    for argv in (first, second):
        config = _config(argv)
        assert config["sandbox_mode"] == '"workspace-write"'
        roots = tomllib.loads(f"r = {config['sandbox_workspace_write.writable_roots']}")["r"]
        assert str(tmp_path.resolve()) in roots
        assert argv[argv.index("-m") + 1] == "gpt-5.6-terra"
        assert config["model_reasoning_effort"] == '"high"'


def argv_index(argv: list[str], flag: str) -> int:
    return argv.index(flag)


def test_tool_guide_names_the_allowed_commands(link: Link):
    text = cx.CodexRunner(link).tool_guide(("ai4sci skill",))
    assert "## 工具怎么用" in text and "`ai4sci skill …`" in text and "apply_patch" in text
    assert "一条都不跑" in cx.tool_guide(())
    # 协调层那段：这家没有单独的读文件工具，看文件就是 shell 的只读命令；指南只在开线程时送到
    chat = cx.CodexChat(link)
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
        ("tool_result", ""), ("tool_use", "pdf.parse"), ("tool_result", "")]
    assert events[0].tool_input == {"changes": ["add harness/launcher.sh"]}
    assert events[2].tool_input == {"query": "site:arxiv.org 2609.01558", "action": "search"}
    assert events[3].text == "site:arxiv.org 2609.01558" and not events[3].is_error
    assert events[5].is_error and events[5].text == "no such file"


def test_parse_events_and_final_report():
    events, junk = cx.parse_events(FIXTURE.read_text(encoding="utf-8").splitlines(keepends=True))
    assert junk == [] and events[0]["type"] == "thread.started"
    assert cx.final_report(events).startswith("1. `pwd` succeeded")
    assert cx.final_report([]) == ""


# --- 假 CLI：run() 与 probe() 的整条路 ----------------------------------------------


def _fake_codex(directory: Path, *, logged_in: bool = True,
                version: str = "codex-cli 0.160.0") -> Path:
    """一个装成 codex 的程序：`--version`、`login status`、`exec`（读完 stdin、往 cwd 写一个文件、
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
    return Path(fake_cli(script, f"""import pathlib, sys
args = sys.argv[1:]
if args[:1] == ["--version"]:
    print({version!r})
    sys.exit(0)
if args[:1] == ["login"]:
    if {logged_in!r}:
        print("Logged in using ChatGPT", file=sys.stderr)
        sys.exit(0)
    print("Not logged in", file=sys.stderr)
    sys.exit(1)
sys.stdin.read()
pathlib.Path("out").mkdir(exist_ok=True)
pathlib.Path("out", "hello.txt").write_text("hello", encoding="utf-8")
print({stream!r})
print("some warning", file=sys.stderr)
"""))


def test_runner_run_reports_changed_files_report_and_nan_cost(link: Link, home: Path, tmp_path):
    cli = _fake_codex(tmp_path / "bin")
    cwd = tmp_path / "pack"
    (cwd / "out").mkdir(parents=True)
    result = cx.CodexRunner(replace(link, cli=str(cli))).run("写点东西", cwd, 30, [cwd / "out"],
                                                           ("ai4sci skill",),
                                                           tuning=Tuning(model="gpt-6-luna"))
    assert result.exit_code == 0 and not result.timed_out
    assert result.changed_files == ["out/hello.txt"]  # 框架自己的快照 diff，不信 CLI 自报
    assert result.report == "pong" and math.isnan(result.cost_usd) and result.duration_s > 0
    assert [e["type"] for e in result.events][-1] == "turn.completed"
    assert "some warning" in result.stdout_tail
    logs = sorted((cwd / ".ai4sci").glob("executor-*"))
    assert [p.suffix for p in logs] == [".jsonl", ".log"]  # 事件流与 stderr 各一份留档
    # Codex 的事件里不写模型：留档第一行由适配器记下这次用的哪个，首页按模型数花费才分得开
    # （外层 #256）
    events, _ = cx.parse_events(logs[0].read_text(encoding="utf-8").splitlines(keepends=True))
    assert cx.usage(events).model == "gpt-6-luna"


def test_probe_walks_the_four_questions(link: Link, home: Path, tmp_path):
    cli = _fake_codex(tmp_path / "bin")
    result = cx.probe(replace(link, cli=str(cli)))
    assert isinstance(result, AgentProbe) and result.ok and result.installed and result.logged_in
    assert result.version == "codex-cli 0.160.0" and result.spoke_s > 0
    # 报不出美元：照价目折算（外层 #266；订阅也按 API 公开价算，不是实扣）
    assert result.cost_usd == pytest.approx(5.4e-05)
    assert [n for n, _, _ in result.items] == ["装了没", "版本", "登录", "说话"]
    assert "按价目折算" in result.items[-1][2]
    doc = result.to_dict()
    assert doc["ok"] and doc["cost_usd"] == pytest.approx(5.4e-05)
    assert doc["items"][3]["name"] == "说话"

    stale = _fake_codex(tmp_path / "old", version="codex-cli 0.147.0")
    result = cx.probe(replace(link, cli=str(stale)))
    assert not result.ok and [ok for _, ok, _ in result.items] == [True, False]
    assert "要 ≥ 0.160.0" in result.items[1][2]

    logged_out = _fake_codex(tmp_path / "out", logged_in=False)
    result = cx.probe(replace(link, cli=str(logged_out)))
    assert not result.ok and not result.logged_in
    # 只报事实；人该敲哪一份 ai4sci 由框架补（外层 #274）
    assert result.items[2][2].endswith("平台里还没登录") and "ai4sci" not in result.items[2][2]

    missing = cx.probe(replace(link, cli=str(tmp_path / "nope" / "codex")))
    # 只报事实；装上它的命令由框架补（外层 #277）
    assert not missing.installed and not missing.ok and "找不到" in missing.items[0][2]


def test_probe_runs_every_codex_command_in_the_platform_home(link: Link, tmp_path, monkeypatch):
    """外层 #286：`codex --version` 也会在它的 home 里建 `tmp/`；自检第一句不带平台的 CODEX_HOME，
    就建到了用户的 `~/.codex`。假 codex 每次被起都往 `$CODEX_HOME`（没设就 `~/.codex`）里落一个
    文件。"""
    person = tmp_path / "person"
    monkeypatch.setenv("HOME", str(person))
    monkeypatch.setenv("USERPROFILE", str(person))
    monkeypatch.delenv("CODEX_HOME", raising=False)
    (tmp_path / "bin").mkdir()
    cli = Path(fake_cli(tmp_path / "bin" / "codex", """import os, pathlib, sys
home = pathlib.Path(os.environ.get("CODEX_HOME") or pathlib.Path.home() / ".codex")
(home / "tmp").mkdir(parents=True, exist_ok=True)
(home / "tmp" / sys.argv[1]).write_text("x", encoding="utf-8")
if sys.argv[1:2] == ["--version"]:
    print("codex-cli 0.160.0")
else:
    sys.exit(1)
"""))
    cx.probe(replace(link, cli=str(cli)))
    assert not (person / ".codex").exists(), "家外面多了 .codex"
    assert (link.home / "tmp" / "--version").is_file()


def test_probe_is_reachable_through_the_port(link: Link, home: Path, monkeypatch, tmp_path):
    """`backends.probe("codex")` 调的是模块级 `probe()`：形状对不上要在端口那层炸。"""
    cli = _fake_codex(tmp_path / "bin")
    real = cx.probe
    monkeypatch.setattr(cx, "probe", lambda lk: real(replace(lk, cli=str(cli))))
    assert probe_backend("codex", link).ok
    monkeypatch.setattr(cx, "probe", lambda lk: "nope")
    with pytest.raises(AssertionError, match="没有返回 AgentProbe"):
        probe_backend("codex", link)


# --- 真 CLI ---------------------------------------------------------------------


@pytest.mark.skipif(os.environ.get("AI4SCI_LIVE") != "1", reason="真 codex CLI，AI4SCI_LIVE=1 才跑")
def test_live_probe_runner_and_two_turn_chat(tmp_path: Path, monkeypatch):
    del monkeypatch
    result = cx.probe(LIVE_LINK)  # 平台家里自己的登录（外层 #263）
    assert result.ok, result.items
    ws = tmp_path / "ws"
    (ws / "out").mkdir(parents=True)
    ask = "Write the single word hello into out/hello.txt, then reply exactly: wrote"
    run = cx.CodexRunner(LIVE_LINK).run(ask, ws, 180, [ws / "out"], ("ai4sci skill",),
                               tuning=Tuning(model="gpt-6-luna", effort="low"))
    assert run.exit_code == 0 and run.changed_files == ["out/hello.txt"] and run.report == "wrote"
    chat = cx.CodexChat(LIVE_LINK)
    common = dict(allowed_paths=[ws], bash_rules=("ai4sci",),
                  tuning=Tuning(effort="low"))  # 模型用起点那款（6.1 Sol），真打一遍它的 slug
    first = list(chat.turn("Remember the word: kiwi. Reply only: ok", ws, 180, session_id=None,
                           system_prompt="你是海盗，每句结尾加 arr。", **common))
    sid = first[0].session_id
    assert first[0].kind == "init" and sid and first[-1].kind == "done"
    second = list(chat.turn("What was the word? Reply with just the word.", ws, 180,
                            session_id=sid, system_prompt="", **common))
    assert second[-1].kind == "done" and "kiwi" in second[-1].text.lower()
    assert all(e.session_id == sid for e in second)


# --- 用量（外层 #256：首页的花费）---------------------------------------------------

from backends import read_usage  # noqa: E402

# 本机一轮真实对话的 turn.completed（PINN 项目）；一次会话里可以有几轮，按轮加
_DONE = {"type": "turn.completed",
         "usage": {"input_tokens": 849491, "cached_input_tokens": 787456,
                   "cache_write_input_tokens": 0, "output_tokens": 5816,
                   "reasoning_output_tokens": 1217}}


def test_usage_sums_turns_and_reports_no_dollars():
    """订阅报不出美元：美元是 NaN（未知），不是 0；token 照算，模型事件里没有就是 None。"""
    got = cx.usage([{"type": "thread.started", "thread_id": "t"}, _DONE, _DONE])
    assert (got.input_tokens, got.cached_tokens, got.output_tokens) == (2 * 849491, 2 * 787456,
                                                                        2 * 5816)
    assert got.model is None
    assert math.isnan(got.cost_usd)


def test_prices_cover_every_listed_model_and_split_cached_tokens():
    """订阅报不出成本，首页照定价表折算：清单上每一款都有价；命中缓存的那部分按缓存价算。"""
    from backends import Usage, prices
    table = prices("codex")
    listed = {c.id for p in cx.PROVIDERS.values() for c in p.models}
    assert set(table) == set(cx.PRICED) and listed <= set(table)  # 每个供应商的每款都有价
    sol = table["gpt-6.1-sol"]
    assert sol.title == "GPT-6.1 Sol"
    got = sol.cost(Usage(input_tokens=1_000_000, cached_tokens=800_000, output_tokens=10_000))
    assert got == pytest.approx(0.2 * sol.input + 0.8 * sol.cached + 0.01 * sol.output)


def test_usage_is_unknown_when_no_turn_completed():
    assert cx.usage([{"type": "thread.started", "thread_id": "t"}, {"type": "turn.failed"}]) is None


def test_read_usage_tells_codex_events_apart():
    name, got = read_usage([_DONE])
    assert name == "codex" and got.output_tokens == 5816


# --- 供应商（外层 #266）---------------------------------------------------------
def test_third_party_providers_ride_a_responses_provider_block_with_a_model_catalog(link, tmp_path,
                                                                                   monkeypatch):
    """照 cc-switch 的预设：写一个 `model_providers.ai4sci`（地址、Responses、key 从哪个变量读）
    并选它，DeepSeek 再给模型说明；key 只放进这一个进程的环境，shell 里同名的去掉。"""
    deepseek = Link(home=link.home, provider="deepseek", key="sk-ds")
    argv = cx.CodexRunner(deepseek).build_argv(tmp_path, [tmp_path])
    configs = [argv[i + 1] for i, a in enumerate(argv) if a == "-c"]
    assert 'model_provider="ai4sci"' in configs
    block = next(c for c in configs if c.startswith("model_providers.ai4sci="))
    assert 'base_url="https://api.deepseek.com"' in block and 'wire_api="responses"' in block
    assert 'env_key="AI4SCI_PROVIDER_KEY"' in block
    assert 'shell_environment_policy.exclude=["AI4SCI_PROVIDER_KEY"]' in configs  # agent 看不见
    catalog = next(c for c in configs if c.startswith("model_catalog_json="))
    assert catalog.endswith('codex-deepseek.json"')
    assert argv[argv.index("-m") + 1] == "deepseek-flash"
    assert 'model_reasoning_effort="high"' in configs  # 它的思考档只有 low / high / max
    # DeepSeek 的 Responses API 忽略 web_search（官方配置也关掉）：照实关掉，不发一个被忽略的设置
    assert 'web_search="disabled"' in configs and 'web_search="live"' not in configs
    monkeypatch.setenv(cx.PROVIDER_KEY_ENV, "from-shell")
    assert cx.build_env(1.0, link.home, deepseek)[cx.PROVIDER_KEY_ENV] == "sk-ds"
    assert cx.PROVIDER_KEY_ENV not in cx.build_env(1.0, link.home, link)  # 官方登录不带
    official = cx.CodexRunner(link).build_argv(tmp_path, [tmp_path])
    assert not any("model_provider" in a for a in official)
    assert 'web_search="live"' in official
    kimi = cx.CodexRunner(Link(home=link.home, provider="kimi", key="sk")).build_argv(tmp_path,
                                                                                       [tmp_path])
    assert 'web_search="live"' in kimi  # Kimi 的 Responses API 有服务端搜索


def test_third_party_effort_lists_match_the_model_catalogs():
    """档位表是唯一真相，随包的模型说明要和它对得上（外层 #266）：每家第三方的档位、起点与
    模型说明里每款模型的 supported_reasoning_levels / default_reasoning_level 一致，清单上的模型
    说明里都有。起点照各家官方缺省：DeepSeek high，Kimi max。"""
    for name, path in cx.CATALOGS.items():
        provider = cx.PROVIDERS[name]
        models = {m["slug"]: m for m in json.loads(path.read_text(encoding="utf-8"))["models"]}
        assert {c.id for c in provider.models} <= set(models), name
        for slug in (c.id for c in provider.models):
            levels = [lv["effort"] for lv in models[slug]["supported_reasoning_levels"]]
            assert levels == [c.id for c in provider.efforts], slug
            assert models[slug]["default_reasoning_level"] == provider.effort, slug
    assert (cx.PROVIDERS["deepseek"].effort, cx.PROVIDERS["kimi"].effort) == ("high", "max")


def test_web_search_is_registered_per_provider_from_the_official_docs():
    """能不能联网照官方文档一家一家登记（外层 #271）：DeepSeek 的 Responses API 忽略内置工具；
    Kimi 的有服务端搜索；自定义不知道。不登记就构造不出来，免得新加的一家默认「能联网」。"""
    from backends import Provider

    assert {name: p.web_search for name, p in cx.PROVIDERS.items()} == {
        "official": True, "openai": True, "deepseek": False, "kimi": True}
    custom = Link(home=Path("/h"), provider="custom", base_url="https://llm.lab", models=("m1",))
    assert cx.provider(custom).web_search is None
    with pytest.raises(TypeError, match="web_search"):
        Provider("x", "X", (), (), "m", "e")


def test_codex_with_a_missing_key_says_so_instead_of_starting(link, tmp_path):
    events = list(cx.CodexChat(Link(home=link.home, provider="kimi", cli="/nonexistent"))
                  .turn("hi", tmp_path, 5, session_id=None, system_prompt="", allowed_paths=[],
                        bash_rules=()))
    assert [e.kind for e in events] == ["error"] and "Kimi 的 key 还没填" in events[0].text
