"""Claude Code 执行层适配器的单测。

夹具 `fixtures/claude_stream_sample.jsonl` 是 R-1 spike 里真实录下来的一段 stream-json
（外层 issue #20）：一次「改 harness 被拒、在 code/ 下 Write 被放行」的调用。
不连网的用例全部只吃这段夹具与 tmp_path，删掉 tasks/ 与 domains/ 照样过（P-5）。
"""

from __future__ import annotations

import json
import math
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

from backends import BackendNotFound, Link, Runner, RunResult, available_backends, get_backend
from backends._snapshot import diff, snapshot
from backends.claude_code import (
    WEB_TOOLS,
    ClaudeCodeRunner,
    build_env,
    final_metrics,
    kill_tree,
    parse_events,
)
from framework import paths

# 测试里的私有目录：只拼 argv、环境的用不着它真在；真 CLI 的测试用平台家里那份（要先在平台里登录过）
HOME = Path("/nonexistent/ai4sci-home/claude_code")
LINK = Link(home=HOME)
LIVE_LINK = Link(home=paths.DEFAULT_HOME / "claude_code")

FIXTURE = Path(__file__).parent / "fixtures" / "claude_stream_sample.jsonl"


@pytest.fixture
def sample_events() -> list[dict]:
    events, junk = parse_events(FIXTURE.read_text(encoding="utf-8").splitlines(keepends=True))
    assert junk == [], "夹具应当每行都是合法 JSON"
    return events


# --- 端口 -----------------------------------------------------------------


def test_get_backend_returns_runner_shaped_object():
    runner = get_backend("claude_code", LINK)
    assert isinstance(runner, Runner)


def test_backend_not_found_lists_available_names():
    with pytest.raises(BackendNotFound) as excinfo:
        get_backend("nope", LINK)
    # 报错必须把可用名字带上，否则调用方只能去翻源码
    assert "claude_code" in str(excinfo.value) and "codex" in str(excinfo.value)
    assert available_backends() == ["claude_code", "codex"]
    # 名字贴在适配器上（P-25 按名字查设置）
    assert get_backend("claude_code", LINK).name == "claude_code"


# --- argv 组装 ------------------------------------------------------------


def test_argv_turns_allowed_paths_into_absolute_tool_rules(tmp_path: Path):
    code = tmp_path / "code"
    code.mkdir()
    argv = ClaudeCodeRunner(LINK).build_argv("改点东西", tmp_path, [code])
    rules = argv[argv.index("--allowedTools") + 1 : argv.index("--max-turns")]
    # `//` 前缀是实测结论：单个 `/` 会被当成项目根相对路径，规则不生效
    assert f"Edit(//{str(code).lstrip('/')}/**)" in rules
    assert f"Write(//{str(code).lstrip('/')}/**)" in rules
    assert f"Read(//{str(tmp_path).lstrip('/')}/**)" in rules
    # 没给 bash_rules 就一条 Bash 规则都不该有：Bash 是绕开路径白名单的口子
    assert not [r for r in rules if r.startswith("Bash(")]
    # 端口给的是与 CLI 无关的命令前缀，这家翻成 `Bash(<前缀> *)`
    with_skill = ClaudeCodeRunner(LINK).build_argv("改点东西", tmp_path, [code], ("ai4sci skill",))
    assert "Bash(ai4sci skill *)" in with_skill[with_skill.index("--allowedTools"):]
    assert "ai4sci skill" not in with_skill  # 裸前缀不进 argv


def test_runner_argv_takes_per_session_turn_and_budget_limits(tmp_path: Path):
    """外层 #122：读别人整个仓库再写壳的会话要比缺省的 30 轮多；能力给的上限进 argv，不给用缺省。"""
    argv = ClaudeCodeRunner(LINK).build_argv("hi", tmp_path, [tmp_path], max_turns=80,
                                         max_budget_usd=6.0)
    assert argv[argv.index("--max-turns") + 1] == "80"
    assert argv[argv.index("--max-budget-usd") + 1] == "6.0"
    default = ClaudeCodeRunner(LINK).build_argv("hi", tmp_path, [tmp_path])
    assert default[default.index("--max-turns") + 1] == "30"


def test_argv_grants_the_clis_own_web_tools_on_both_layers(tmp_path: Path):
    """主人 2026-09-20：联网只用 CLI 自带的工具。实测 dontAsk 下 WebSearch 不在白名单就被拒，
    拒绝信息还教 agent「用别的工具试」，它于是拿 curl 硬凑；两层的白名单都要带上。"""
    from backends.claude_code import ClaudeCodeChat

    assert WEB_TOOLS == ("WebSearch", "WebFetch")
    runner = ClaudeCodeRunner(LINK).build_argv("hi", tmp_path, [tmp_path])
    chat = ClaudeCodeChat(LINK).build_argv("hi", tmp_path, session_id=None, system_prompt="",
                                       allowed_paths=[], bash_rules=())
    for argv in (runner, chat):
        rules = argv[argv.index("--allowedTools") + 1:argv.index("--max-turns")]
        assert all(tool in rules for tool in WEB_TOOLS), rules


def test_runner_uses_the_same_env_as_chat_so_bare_ai4sci_resolves(monkeypatch, tmp_path: Path):
    """执行层要跑 `ai4sci skill …`（纲领 P-22）：venv 的 bin 在 PATH 上、后台关掉、Bash 超时对齐。
    断言 Popen 收到的就是 build_env 的结果，而不是继承的裸环境。"""
    seen: dict = {}

    class FakeProc:
        pid = os.getpid()
        returncode = 0
        stdout = iter(())
        stderr = iter(())

        def wait(self, timeout=None):
            return 0

    def fake_popen(argv, **kw):
        seen["env"] = kw["env"]
        return FakeProc()

    monkeypatch.setattr(subprocess, "Popen", fake_popen)
    monkeypatch.setenv("PATH", "/usr/bin")
    with pytest.raises(RuntimeError, match="没有 result 事件"):
        ClaudeCodeRunner(LINK).run("hi", tmp_path, 7.0, [tmp_path])
    env = seen["env"]
    assert env["PATH"].endswith(str(Path(sys.executable).parent))
    assert env["CLAUDE_CODE_DISABLE_BACKGROUND_TASKS"] == "1"
    assert env["BASH_MAX_TIMEOUT_MS"] == "7000"


def test_argv_carries_isolation_flags_and_never_bypasses_permissions(tmp_path: Path):
    argv = ClaudeCodeRunner(LINK).build_argv("hi", tmp_path, [tmp_path])
    for flag in ("--no-session-persistence", "--strict-mcp-config", "--disable-slash-commands",
                 "--setting-sources", "--output-format", "stream-json", "--verbose"):
        assert flag in argv
    # `--setting-sources` 的值必须是空串：它是不加载 CLAUDE.md / hook / plugin 的承重位
    assert argv[argv.index("--setting-sources") + 1] == ""
    assert argv[argv.index("--permission-mode") + 1] == "dontAsk"
    assert "--dangerously-skip-permissions" not in argv
    assert "bypassPermissions" not in argv


def test_env_config_has_read_points_and_defaults(tmp_path: Path, monkeypatch):
    from backends import Tuning

    argv = ClaudeCodeRunner(LINK).build_argv("hi", tmp_path, [tmp_path])
    assert argv[argv.index("--max-turns") + 1] == "30"
    assert argv[argv.index("--max-budget-usd") + 1] == "2.0"
    # 模型与深度永远显式传（P-25：从不让 CLI 自己猜）：没给用起点 sonnet / medium
    assert argv[argv.index("--model") + 1] == "sonnet"
    assert argv[argv.index("--effort") + 1] == "medium"
    import backends.claude_code as module
    source = Path(module.__file__).read_text(encoding="utf-8")
    assert "AI4SCI_EXECUTOR_MODEL" not in source  # 环境变量退役了（P-25：模型从按人的设置来）

    monkeypatch.setenv("AI4SCI_EXECUTOR_MAX_TURNS", "7")
    monkeypatch.setenv("AI4SCI_EXECUTOR_MAX_BUDGET_USD", "0.5")
    argv = ClaudeCodeRunner(LINK).build_argv("hi", tmp_path, [tmp_path],
                                             tuning=Tuning(model="opus"))
    assert argv[argv.index("--max-turns") + 1] == "7"
    assert argv[argv.index("--max-budget-usd") + 1] == "0.5"
    assert argv[argv.index("--model") + 1] == "opus"
    with pytest.raises(ValueError, match="模型 'gpt' 不在清单上"):
        ClaudeCodeRunner(LINK).build_argv("hi", tmp_path, [tmp_path], tuning=Tuning(model="gpt"))


@pytest.mark.parametrize("value", ["0", "-3"])
def test_env_config_rejects_nonsense_instead_of_falling_back(tmp_path: Path, monkeypatch, value):
    monkeypatch.setenv("AI4SCI_EXECUTOR_MAX_TURNS", value)
    with pytest.raises(AssertionError):
        ClaudeCodeRunner(LINK).build_argv("hi", tmp_path, [tmp_path])


# --- 事件解析 --------------------------------------------------------------


def test_parse_events_keeps_non_json_lines_instead_of_swallowing():
    events, junk = parse_events(['{"type":"result"}\n', "Warning: no stdin data\n", "\n"])
    assert events == [{"type": "result"}]
    assert junk == ["Warning: no stdin data\n"]


def test_sample_stream_carries_permission_denial_and_tool_paths(sample_events: list[dict]):
    kinds = {(e.get("type"), e.get("subtype")) for e in sample_events}
    assert ("system", "init") in kinds
    assert ("system", "permission_denied") in kinds
    assert ("result", "success") in kinds

    denied = [e for e in sample_events if e.get("subtype") == "permission_denied"]
    assert [e["tool_name"] for e in denied] == ["Edit"]  # 改 harness 的那一次被拒

    touched = [c["input"]["file_path"] for e in sample_events if e.get("type") == "assistant"
               for c in e["message"]["content"]
               if c.get("type") == "tool_use" and c["name"] in ("Write", "Edit")]
    assert any(p.endswith("/code/note.txt") for p in touched)


def test_isolation_is_visible_in_init_event(sample_events: list[dict]):
    init = next(e for e in sample_events if e.get("subtype") == "init")
    # 隔离生效的机器判据：没有 MCP、没有 skill、没有 plugin、没有 slash command
    assert init["mcp_servers"] == []
    assert init["skills"] == []
    assert init["plugins"] == []
    assert init["slash_commands"] == []
    assert init["permissionMode"] == "dontAsk"


def test_final_metrics_reads_cost_and_duration_from_result(sample_events: list[dict]):
    cost, duration_s = final_metrics(sample_events, timed_out=False, wall_s=99.0)
    assert cost == pytest.approx(0.1188655)
    assert duration_s == pytest.approx(32.248)


def test_final_metrics_raises_rather_than_reporting_zero():
    with pytest.raises(RuntimeError, match="result"):
        final_metrics([{"type": "system", "subtype": "init"}], timed_out=False, wall_s=12.0)


def test_final_metrics_reports_nan_when_process_died_without_result():
    # 被外部 kill -9（真跑第 10 轮）或 CLI 自己崩了：没有 result 事件，成本未知不是 0，
    # 也不该把整个内环炸掉——那是执行层这一轮失败，由 loop 记账
    cost, duration_s = final_metrics([], timed_out=False, wall_s=20.0, exit_code=-9)
    assert math.isnan(cost) and duration_s == 20.0


def test_final_metrics_reports_nan_when_killed_on_timeout():
    # 超时被杀时 result 事件根本没发出来，成本只能是"未知"；填 0 会让预算统计静默偏低
    cost, duration_s = final_metrics([], timed_out=True, wall_s=20.0)
    assert math.isnan(cost)
    assert duration_s == 20.0


# --- 快照 diff -------------------------------------------------------------


def test_snapshot_diff_catches_add_modify_delete_and_ignores_bookkeeping(tmp_path: Path):
    (tmp_path / "code").mkdir()
    (tmp_path / "code" / "keep.py").write_text("a", encoding="utf-8")
    (tmp_path / "code" / "gone.py").write_text("b", encoding="utf-8")
    (tmp_path / "harness").mkdir()
    (tmp_path / "harness" / "evaluate.py").write_text("score", encoding="utf-8")
    before = snapshot(tmp_path)

    (tmp_path / "code" / "keep.py").write_text("a2", encoding="utf-8")
    (tmp_path / "code" / "gone.py").unlink()
    (tmp_path / "code" / "new.py").write_text("c", encoding="utf-8")
    # .git 与 .ai4sci 是记账用的，不该被报成执行层的改动
    (tmp_path / ".git").mkdir()
    (tmp_path / ".git" / "HEAD").write_text("ref", encoding="utf-8")
    (tmp_path / ".ai4sci").mkdir()
    (tmp_path / ".ai4sci" / "executor-x.jsonl").write_text("{}", encoding="utf-8")

    assert diff(before, snapshot(tmp_path)) == ["code/gone.py", "code/keep.py", "code/new.py"]


def test_snapshot_skips_symlinks(tmp_path: Path):
    (tmp_path / "real.txt").write_text("x", encoding="utf-8")
    (tmp_path / "dangling").symlink_to(tmp_path / "nope.txt")
    assert sorted(snapshot(tmp_path)) == ["real.txt"]


# --- 进程组清理 ------------------------------------------------------------


def test_kill_tree_reaches_children_in_their_own_process_group(tmp_path: Path):
    """复刻实测的孤儿形态：CLI 的 Bash 工具把子进程起在**另一个**进程组里。

    只 killpg(自己那组) 时 R-1 实测留下过 PPID=1 的孤儿 sleep；这里用 setsid 造同样的形状。
    """
    marker = tmp_path / "child.pid"
    script = (f"import os,sys,time,subprocess;"
              f"p=subprocess.Popen([sys.executable,'-c','import time;time.sleep(60)'],"
              f"start_new_session=True);"
              f"open({str(marker)!r},'w').write(str(p.pid));time.sleep(60)")
    parent = subprocess.Popen([sys.executable, "-c", script], start_new_session=True)
    deadline = time.monotonic() + 10
    while not marker.exists() and time.monotonic() < deadline:
        time.sleep(0.05)
    assert marker.exists(), "子进程没起来，测试前提不成立"
    child_pid = int(marker.read_text())
    assert os.getpgid(child_pid) != os.getpgid(parent.pid), "测试前提：子进程自成一组"

    kill_tree(parent.pid)
    parent.wait(timeout=10)
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        try:
            os.kill(child_pid, 0)
        except ProcessLookupError:
            break
        time.sleep(0.05)
    else:
        pytest.fail(f"孤儿进程 {child_pid} 还活着")


# --- 真 CLI 冒烟（默认 skip）-----------------------------------------------


@pytest.mark.skipif(os.environ.get("AI4SCI_LIVE") != "1", reason="需要真 claude CLI 与网络")
def test_live_smoke_writes_only_inside_allowed_path(tmp_path: Path):
    code = tmp_path / "code"
    code.mkdir()
    (code / "main.py").write_text("VALUE = 1\n", encoding="utf-8")
    harness = tmp_path / "harness"
    harness.mkdir()
    (harness / "evaluate.py").write_text("SCORE = 0.5\n", encoding="utf-8")

    result: RunResult = get_backend("claude_code", LIVE_LINK).run(
        prompt=f"在 {code}/ 下新建文件 hello.txt，内容写一行 ai4sci。直接做，不要问。",
        cwd=tmp_path, timeout_s=180.0, allowed_paths=[code],
    )
    assert result.timed_out is False
    assert result.exit_code == 0
    assert result.changed_files == ["code/hello.txt"]
    assert result.cost_usd > 0
    assert result.duration_s > 0
    # 事件流落盘取证，不进 prompt（P-9）
    logs = sorted((tmp_path / ".ai4sci").glob("executor-*.jsonl"))
    assert len(logs) == 1
    assert json.loads(logs[0].read_text(encoding="utf-8").splitlines()[0])["type"] == "system"


def test_run_drains_stderr_instead_of_deadlocking(tmp_path: Path):
    """stderr 灌满管道缓冲区也不能卡住：CLI 往 stderr 打 Warning 是实测行为。

    用一个假 CLI 顶替 claude：往 stderr 狂写 1 MB，再往 stdout 吐一条合法 result 事件。
    只读 stdout 的实现会在这里等到超时。
    """
    fake = tmp_path / "fake-claude"
    fake.write_text(
        "#!/usr/bin/env python3\n"
        "import sys, json\n"
        "sys.stderr.write('W' * (1 << 20))\n"
        "print(json.dumps({'type': 'result', 'total_cost_usd': 0.01, 'duration_ms': 5}))\n",
        encoding="utf-8",
    )
    fake.chmod(0o755)
    cwd = tmp_path / "work"
    cwd.mkdir()
    runner = ClaudeCodeRunner(LINK, cli=str(fake))
    result = runner.run("noop", cwd=cwd, timeout_s=10.0, allowed_paths=[cwd])
    assert result.timed_out is False
    assert result.cost_usd == 0.01
    assert result.stdout_tail.endswith("W" * 100)
    assert list((cwd / ".ai4sci").glob("executor-*.stderr.log"))


# --- 协调层：Chat 端口与适配器 ---------------------------------------------
from backends import Chat, ChatEvent, get_chat  # noqa: E402
from backends.claude_code import ISOLATION_ARGS, ClaudeCodeChat, _translate  # noqa: E402

CHAT_FIXTURE = Path(__file__).parent / "fixtures" / "claude_chat_sample.jsonl"
SID = "d1fc75c5-dec5-427a-88f9-e9f810e42c89"


def test_get_chat_returns_chat_shaped_object():
    assert isinstance(get_chat("claude_code", LINK), Chat)
    with pytest.raises(BackendNotFound):
        get_chat("nope", LINK)


def test_chat_env_forbids_background_tasks_and_aligns_bash_timeout(monkeypatch):
    """外层 #57：长命令不许被 CLI 挪到后台，Bash 超时抬到本轮超时，杀它的只能是我们的定时器。"""
    monkeypatch.setenv("KEEP_ME", "1")
    env = build_env(900.0, LINK)
    assert env["CLAUDE_CODE_DISABLE_BACKGROUND_TASKS"] == "1"
    assert env["BASH_DEFAULT_TIMEOUT_MS"] == env["BASH_MAX_TIMEOUT_MS"] == "900000"
    assert env["KEEP_ME"] == "1"  # 继承本进程环境（AI4SCI_EXECUTOR_MODEL 等要传给协调 agent）


def test_sessions_do_not_carry_the_persons_auto_memory():
    """外层 #222：`--setting-sources ""` 挡不住 CLI 的自动记忆，会话所在仓库的 MEMORY.md
    整段进上下文（实测一次筛选会话多读 7700 token、多花三成）。两层会话都关。"""
    assert build_env(1.0, LINK)["CLAUDE_CODE_DISABLE_AUTO_MEMORY"] == "1"
    assert build_env(1.0, LINK, "chat-1")["CLAUDE_CODE_DISABLE_AUTO_MEMORY"] == "1"


def test_sessions_live_in_the_platform_home_not_the_persons_claude_dir(tmp_path: Path):
    """外层 #263：配置目录指到平台家里这家的私有目录——会话记录、平台自己的登录都在那里，
    用户的 `~/.claude` 一个字节不写；删对话也只删那里的。"""
    home = tmp_path / "claude_code"
    assert build_env(1.0, Link(home=home))["CLAUDE_CONFIG_DIR"] == str(home)
    chat = ClaudeCodeChat(Link(home=home))
    cwd = tmp_path / "my_ws"
    encoded = str(cwd.resolve()).replace("/", "-").replace("_", "-")  # CLI 把下划线也换掉
    session = home / "projects" / encoded / f"{SID}.jsonl"
    session.parent.mkdir(parents=True)
    session.write_text("{}\n", encoding="utf-8")
    (home / "session-env" / SID).mkdir(parents=True)
    chat.forget(SID, cwd)
    assert not session.exists() and not (home / "session-env" / SID).exists()
    chat.forget(SID, cwd)  # 幂等


def test_login_and_logout_run_in_the_platform_home(tmp_path: Path):
    """官方订阅在平台里单独登录：CLI 在私有配置目录下不认用户本机的登录（2026-10-06 实测）。"""
    from backends.claude_code import login_command, logout_command

    link = Link(home=tmp_path / "claude_code")
    argv, env = login_command(link)
    assert argv[1:] == ["auth", "login", "--claudeai"]
    assert env["CLAUDE_CONFIG_DIR"] == str(link.home)
    argv, env = logout_command(link)
    assert argv[1:] == ["auth", "logout"] and env["CLAUDE_CONFIG_DIR"] == str(link.home)


def test_chat_env_puts_this_venvs_bin_on_path_so_bare_ai4sci_resolves(monkeypatch):
    """纲领 P-14：agent 敲裸 `ai4sci`，服务把自己 venv 的 bin 追加到 PATH 末尾（不遮系统命令）。

    断言的是结果不是表达式：这个 PATH 下 `which ai4sci` 要找得到。第一版拿解释器 resolve() 后的
    目录当 bin，venv 的 python 是软链，解析出去就是系统 bin，真跑时 agent 报 command not found。"""
    import shutil
    import sys

    monkeypatch.setenv("PATH", "/usr/bin")
    env = build_env(1.0, LINK)
    assert env["PATH"].startswith(f"/usr/bin{os.pathsep}")  # 追加在后，系统命令在前
    assert shutil.which("ai4sci", path=env["PATH"]) == str(Path(sys.executable).parent / "ai4sci")
    monkeypatch.delenv("PATH")
    assert build_env(1.0, LINK)["PATH"] == str(Path(sys.executable).parent)


def test_translate_turns_text_deltas_into_delta_events_and_ignores_thinking():
    """外层 #65：stream_event 里只有 text_delta 是给人看的；thinking / signature 不翻。"""
    from backends.claude_code import _translate

    piece = _translate(json.dumps({"type": "stream_event", "session_id": "s", "event": {
        "type": "content_block_delta", "index": 0,
        "delta": {"type": "text_delta", "text": "光合"}}}))
    assert piece is not None and piece.kind == "delta" and piece.text == "光合"
    assert piece.session_id == "s"
    for delta in ({"type": "thinking_delta", "thinking": "…"}, {"type": "signature_delta"},
                  {"type": "text_delta", "text": ""}):
        assert _translate(json.dumps({"type": "stream_event", "event": {
            "type": "content_block_delta", "delta": delta}})) is None
    stop = {"type": "stream_event", "event": {"type": "message_stop"}}
    assert _translate(json.dumps(stop)) is None


def test_chat_argv_asks_for_partial_messages(tmp_path: Path):
    argv = ClaudeCodeChat(LINK).build_argv("hi", tmp_path, session_id=None, system_prompt="",
                                       allowed_paths=[], bash_rules=())
    assert "--include-partial-messages" in argv


def test_chat_argv_adds_readable_dirs_without_write_rules(tmp_path: Path):
    """纲领 P-16：研究助理看得见库（--add-dir 让 Read 在 dontAsk 下不被拒），但库不进写的白名单。"""
    library = tmp_path / "workflows"
    library.mkdir()
    argv = ClaudeCodeChat(LINK).build_argv("hi", tmp_path / "ws", session_id=None, system_prompt="",
                                       allowed_paths=[tmp_path / "ws" / "flows"], bash_rules=(),
                                       readable_paths=[library])
    assert argv[argv.index("--add-dir") + 1] == str(library.resolve())
    rules = argv[argv.index("--allowedTools") + 1:argv.index("--max-turns")]
    assert f"Read(//{library.resolve().as_posix().lstrip('/')}/**)" in rules
    assert not any(r.startswith(("Edit(", "Write(")) and "workflows" in r for r in rules)
    plain = ClaudeCodeChat(LINK).build_argv("hi", tmp_path, session_id=None, system_prompt="",
                                        allowed_paths=[], bash_rules=())
    assert "--add-dir" not in plain


def test_chat_env_carries_the_chat_id_to_the_buttons_the_agent_presses(monkeypatch):
    """外层 #63：agent 按的 `--detach` 从环境里知道自己属于哪段对话；没给就不留上一段的。"""
    from framework.workspace.jobs import CHAT_ID_ENV

    assert CHAT_ID_ENV == "AI4SCI_CHAT_ID"  # 适配器抄的那份名字与 framework 的对账
    assert build_env(1.0, LINK, "chat-1")[CHAT_ID_ENV] == "chat-1"
    monkeypatch.setenv(CHAT_ID_ENV, "chat-stale")
    assert CHAT_ID_ENV not in build_env(1.0, LINK)


def test_chat_argv_resumes_by_session_id_and_keeps_persistence(tmp_path: Path):
    from backends import Tuning

    chat = ClaudeCodeChat(LINK)
    common = dict(system_prompt="指南", allowed_paths=[tmp_path / "tasks"],
                  bash_rules=(".venv/bin/ai4sci",))
    first = chat.build_argv("你好", tmp_path, session_id=None, **common)
    second = chat.build_argv("继续", tmp_path, session_id=SID, **common)
    assert "--resume" not in first
    assert second[second.index("--resume") + 1] == SID
    # 指南只在开会话那一轮送：续接时 CLI 沿用开会话那份，再送也不生效（实测 2.1.286，见适配器
    # 文件头），中途变了由框架把变了的几节塞进话里
    assert first[first.index("--append-system-prompt") + 1] == "指南"
    assert "--append-system-prompt" not in second
    for argv in (first, second):
        assert "--no-session-persistence" not in argv, "多轮靠 CLI 的会话持久化，不能关"
        assert all(flag in argv for flag in ISOLATION_ARGS if flag)
        assert "--permission-mode" in argv and "dontAsk" in argv
        assert "--dangerously-skip-permissions" not in argv
        rules = argv[argv.index("--allowedTools") + 1: argv.index("--max-turns")]
        assert "Bash(.venv/bin/ai4sci *)" in rules  # 前缀翻成这家的白名单写法
        assert any(r.startswith("Write(//") and r.endswith("/tasks/**)") for r in rules)
    picked = chat.build_argv("x", tmp_path, session_id=None, tuning=Tuning(model="opus"), **common)
    assert picked[picked.index("--model") + 1] == "opus"


def test_tool_guides_teach_only_tools_this_cli_has():
    """P-25：「工具怎么用」是这家的。2.1.289 起没有 Glob / Grep 工具，照旧指南找文件白耗几轮
    （外层 #219）：读文件用 Read，找文件、搜内容用单条的只读命令（dontAsk 下自动放行）。"""
    chat = ClaudeCodeChat(LINK)
    for text in (chat.tool_guide(("ai4sci", ".venv/bin/ai4sci")),
                 ClaudeCodeRunner(LINK).tool_guide(("ai4sci skill",))):
        assert "Glob" not in text and "Grep" not in text
        assert "Read" in text and "find" in text and "grep" in text
        assert "Bash 里会改东西的只放行" in text


def test_chat_knobs_list_models_and_efforts_with_a_concrete_start():
    """外层 #86 / P-25：适配器自报有哪些模型、哪几档思考深度，以及起点（具体值，不是 None）。"""
    from backends import Knobs, Tuning
    from backends.claude_code import EFFORTS, MODELS

    knobs = ClaudeCodeChat(LINK).knobs()
    assert isinstance(knobs, Knobs) and knobs.models == MODELS and knobs.efforts == EFFORTS
    assert knobs.model == "sonnet" and knobs.effort == "medium"
    assert [c.id for c in knobs.efforts] == ["low", "medium", "high", "xhigh", "max"]
    knobs.check(Tuning(model="opus", effort="max"))
    knobs.check(Tuning())
    assert knobs.fill(None) == Tuning(model="sonnet", effort="medium")
    assert knobs.fill(Tuning(effort="high")) == Tuning(model="sonnet", effort="high")
    with pytest.raises(ValueError, match="模型 'gpt' 不在清单上；可选：sonnet, opus, fable"):
        knobs.check(Tuning(model="gpt"))
    with pytest.raises(ValueError, match="思考深度 'ultra' 不在清单上"):
        knobs.check(Tuning(effort="ultra"))
    with pytest.raises(AssertionError, match="起点 'nope' 不在清单"):
        Knobs(models=MODELS, efforts=EFFORTS, model="nope", effort="low")


def test_chat_argv_always_passes_model_and_effort(tmp_path: Path):
    """P-25：对话 meta 里记的是具体值；没给的用起点；从不让 CLI 自己猜。"""
    from backends import Tuning

    chat = ClaudeCodeChat(LINK)
    common = dict(session_id=None, system_prompt="", allowed_paths=[], bash_rules=())
    bare = chat.build_argv("x", tmp_path, **common)
    assert bare[bare.index("--model") + 1] == "sonnet"
    assert bare[bare.index("--effort") + 1] == "medium"
    picked = chat.build_argv("x", tmp_path, tuning=Tuning(model="opus", effort="max"), **common)
    assert picked[picked.index("--model") + 1] == "opus"
    assert picked[picked.index("--effort") + 1] == "max"
    half = chat.build_argv("x", tmp_path, tuning=Tuning(effort="high"), **common)
    assert half[half.index("--model") + 1] == "sonnet"
    assert half[half.index("--effort") + 1] == "high"
    with pytest.raises(ValueError, match="思考深度 'ultra' 不在清单上"):
        chat.build_argv("x", tmp_path, tuning=Tuning(effort="ultra"), **common)


def test_translate_turns_the_sample_stream_into_chat_events():
    events = [e for e in map(_translate, CHAT_FIXTURE.read_text(encoding="utf-8").splitlines())
              if e is not None]
    kinds = [e.kind for e in events]
    assert kinds == ["init", "tool_use", "tool_result", "denied", "tool_result", "text", "done"]
    assert events[0].session_id == SID
    assert events[1].tool == "Bash" and events[1].tool_input["command"] == "ls"
    assert events[2].text == "turn1.err\nturn1.jsonl" and events[2].is_error is False
    assert events[3].is_error and "白名单" in events[3].text
    assert events[4].text == "Permission denied" and events[4].is_error is True
    assert events[5].text.startswith("记住了 17")
    done = events[-1]
    assert done.text.startswith("记住了 17") and done.cost_usd == pytest.approx(0.0187643)
    assert done.duration_s == pytest.approx(4.321) and done.exit_code == 0
    assert all(e.raw for e in events), "每个事件都带原生 raw，落盘用"


def test_translate_ignores_noise_and_thinking():
    assert _translate("not json\n") is None
    assert _translate("   \n") is None
    assert _translate('{"type":"rate_limit_event"}') is None
    assert _translate('{"type":"assistant","message":{"content":[{"type":"thinking"}]}}') is None


def test_chat_event_rejects_unknown_kind():
    with pytest.raises(AssertionError):
        ChatEvent("banana")


@pytest.mark.skipif(os.environ.get("AI4SCI_LIVE") != "1", reason="真 CLI，AI4SCI_LIVE=1 才跑")
def test_live_chat_two_turns_remember_across_resume(tmp_path: Path):
    from backends import Tuning

    chat = ClaudeCodeChat(LIVE_LINK)
    common = dict(system_prompt="你是测试助手，回答极短。", allowed_paths=[], bash_rules=())
    first = list(chat.turn("记住这个数字：17。只回“好”。", tmp_path, 120, session_id=None,
                           tuning=Tuning(model="sonnet", effort="low"), **common))
    sid = first[0].session_id
    assert first[0].kind == "init" and sid and first[-1].kind == "done"
    # 旋钮真拧到了 CLI 上：init 事件回报的模型就是这一轮给的那个（外层 #86）
    assert "sonnet" in str(first[0].raw.get("model", ""))
    second = list(chat.turn("刚才的数字是多少？只回数字。", tmp_path, 120, session_id=sid,
                            tuning=Tuning(model="sonnet", effort="low"), **common))
    assert second[-1].kind == "done" and "17" in second[-1].text
    assert second[-1].session_id == sid
    # 端口契约：助理的话逐字先到，完整的 text 后到（外层 #65）
    kinds = [e.kind for e in second]
    assert "delta" in kinds and kinds.index("delta") < kinds.index("text")
    assert "".join(e.text for e in second if e.kind == "delta").strip() == \
        next(e.text for e in second if e.kind == "text").strip()


# --- 用量（外层 #256：首页的花费）---------------------------------------------------

from backends import Usage, read_usage  # noqa: E402
from backends.claude_code import usage  # noqa: E402

# 本机一轮真实对话的 init 与 result（GUA 项目第 1 轮，删去与用量无关的字段）
_INIT = {"type": "system", "subtype": "init", "model": "claude-opus-5[1m]"}
_RESULT = {"type": "result", "subtype": "success", "total_cost_usd": 1.2065,
           "duration_ms": 94369, "usage": {"input_tokens": 22, "cache_creation_input_tokens": 77824,
                     "cache_read_input_tokens": 582738, "output_tokens": 5072}}


def test_usage_reads_tokens_dollars_and_the_reported_model():
    """读进去的 = 没缓存的 + 写缓存的 + 读缓存的；模型是 CLI 报的那一版（别名 opus 解析成哪版
    以它为准），去掉 [1m] 这类上下文后缀——定价表按它查。"""
    assert usage([_INIT, _RESULT]) == Usage(input_tokens=22 + 77824 + 582738,
                                            cached_tokens=582738, output_tokens=5072,
                                            model="claude-opus-5", cost_usd=1.2065)


def test_usage_has_no_model_without_init():
    assert usage([_RESULT]).model is None


def test_prices_cover_every_version_and_every_third_party_model():
    """价目从 cc-switch 搬（外层 #266，`backends/catalog/prices.json`）：别名解析成的每一版、
    每个第三方供应商的每款模型都要有价——第三方的成本只能照它折算；命中缓存的比读进去的便宜。"""
    from backends import prices
    from backends.claude_code import PRICED, PROVIDERS

    table = prices("claude_code")
    assert set(table) == set(PRICED)
    assert table["claude-opus-5"].title == "Claude Opus 5"
    third = {c.id for p in PROVIDERS.values() if p.base_url for c in p.models}
    assert third and third <= set(table)
    assert all(p.cached < p.input < p.output for p in table.values())


def test_the_cli_is_only_trusted_on_dollars_for_its_own_models():
    """CLI 按自己的缺省价乱算第三方的成本（2026-10-06 实测 DeepSeek 一句 pong 报 $0.084，实价约
    $0.002）：只有 claude-* 的报数可信，别的是 NaN，读的人照价目折算。"""
    third = {**_INIT, "model": "deepseek-flash"}
    assert math.isnan(usage([third, _RESULT]).cost_usd)
    assert usage([third, _RESULT]).model == "deepseek-flash"
    assert not math.isnan(usage([_INIT, _RESULT]).cost_usd)


def test_usage_is_unknown_without_a_result_event():
    """超时被杀、进程崩了：result 没来，用了多少不知道——是 None，不编 0。"""
    assert usage([_INIT]) is None


def test_read_usage_finds_which_cli_wrote_the_events():
    assert read_usage([_INIT, _RESULT]) == ("claude_code", usage([_INIT, _RESULT]))
    assert read_usage([{"type": "unknown"}]) is None


# --- 供应商（外层 #266）---------------------------------------------------------
def test_deepseek_gets_its_address_and_haiku_mapping_and_nothing_from_the_shell(monkeypatch):
    """照 cc-switch 的预设接第三方：地址、后台小活映射到它的快档；shell 里的 ANTHROPIC_* 一律不
    继承——起服务的终端里设了 ANTHROPIC_API_KEY 也不能让平台悄悄改走按量计费（外层 #265）。"""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-from-shell")
    monkeypatch.setenv("ANTHROPIC_BASE_URL", "https://elsewhere")
    env = build_env(1.0, Link(home=HOME, provider="deepseek", key="sk-ds"))
    assert env["ANTHROPIC_BASE_URL"] == "https://api.deepseek.com/anthropic"
    assert env["ANTHROPIC_DEFAULT_HAIKU_MODEL"] == "deepseek-flash"
    assert "sk-ds" not in env.values() and "ANTHROPIC_API_KEY" not in env
    official = build_env(1.0, LINK)
    assert not any(k.startswith("ANTHROPIC_") for k in official)  # 官方订阅：登录在私有目录里


def test_the_key_reaches_the_cli_through_a_private_file_not_env_or_argv(tmp_path):
    """外层 #266：key 在环境里，CLI 的 Bash 工具就继承得到，agent 一个 printenv 就打出来
    （2026-10-06 实测）；改成私有配置目录里只有本人能读的文件，`apiKeyHelper` 让 CLI 自己读，
    命令行上只有路径。"""
    import stat

    from backends.claude_code import KEY_FILE, key_args

    link = Link(home=tmp_path / "cc", provider="deepseek", key="sk-ds-secret")
    argv = ClaudeCodeRunner(link).build_argv("hi", tmp_path, [tmp_path])
    assert not any("sk-ds-secret" in a for a in argv)
    helper = json.loads(argv[argv.index("--settings") + 1])["apiKeyHelper"]
    key_file = link.home / KEY_FILE
    assert helper == f"cat {key_file}" and key_file.read_text(encoding="utf-8") == "sk-ds-secret"
    assert stat.S_IMODE(key_file.stat().st_mode) == 0o600
    assert key_args(Link(home=tmp_path / "cc")) == []  # 官方订阅不要 key
    anthropic = Link(home=tmp_path / "cc", provider="anthropic", key="sk-ant")
    assert key_args(anthropic)[0] == "--settings" and "ANTHROPIC_BASE_URL" not in build_env(
        1.0, anthropic)


def test_a_missing_key_says_where_to_fill_it_instead_of_starting_the_cli():
    from backends import KeyMissing
    from backends.claude_code import ClaudeCodeChat, key_args

    with pytest.raises(KeyMissing, match="DeepSeek 的 key 还没填"):
        key_args(Link(home=HOME, provider="deepseek"))
    events = list(ClaudeCodeChat(Link(home=HOME, provider="deepseek"), cli="/nonexistent")
                  .turn("hi", Path("/tmp"), 5, session_id=None, system_prompt="",
                        allowed_paths=[], bash_rules=()))
    assert [e.kind for e in events] == ["error"] and "设置" in events[0].text


def test_models_follow_the_provider_and_third_party_ids_go_straight_to_the_cli(tmp_path):
    from backends.claude_code import ClaudeCodeChat

    link = Link(home=tmp_path / "cc", provider="deepseek", key="sk-ds")
    knobs = ClaudeCodeChat(link).knobs()
    assert [c.id for c in knobs.models] == ["deepseek-flash", "deepseek-v4-pro"]
    argv = ClaudeCodeRunner(link).build_argv("hi", tmp_path, [tmp_path])
    assert argv[argv.index("--model") + 1] == "deepseek-flash"
    custom = Link(home=HOME, provider="custom", base_url="https://llm.lab", models=("m1",))
    assert [c.id for c in ClaudeCodeChat(custom).knobs().models] == ["m1"]
    with pytest.raises(ValueError, match="要填地址和至少一个模型名"):
        ClaudeCodeChat(Link(home=HOME, provider="custom")).knobs()


def test_third_party_effort_lists_only_the_levels_the_provider_tells_apart():
    """思考深度一档对一档（外层 #266，主人 2026-10-06 定）：CLI 把 `--effort` 原样写进
    `output_config.effort`（本机抓包），DeepSeek 只分 low / high / max（medium、xhigh 服务端都当
    high），Kimi K3 也是这三档；旋钮上不给它分不出来的档。起点照各家官方缺省。"""
    from backends.claude_code import PROVIDERS

    for name, start in (("deepseek", "high"), ("kimi", "max")):
        provider = PROVIDERS[name]
        assert [c.id for c in provider.efforts] == ["low", "high", "max"]
        assert provider.effort == start
    # Kimi 的主模型是 K3；K2.7 Code 不认思考深度，不进清单
    assert [c.id for c in PROVIDERS["kimi"].models] == ["kimi-k3"]
    official = ["low", "medium", "high", "xhigh", "max"]  # 官方两家是 CLI 自己的五档
    assert [c.id for c in PROVIDERS["anthropic"].efforts] == official


def test_third_party_turn_cost_is_left_for_the_price_table(tmp_path):
    """第三方那一轮的 done 不带 CLI 报的美元（它按缺省价乱算），读的人照价目折算。"""
    from backends.claude_code import ClaudeCodeChat

    fake = tmp_path / "claude"
    fake.write_text("#!/bin/sh\necho '" + json.dumps(_RESULT) + "'\n", encoding="utf-8")
    fake.chmod(0o755)
    third = ClaudeCodeChat(Link(home=tmp_path, provider="deepseek", key="sk"), cli=str(fake))
    done = [e for e in third.turn("hi", tmp_path, 10, session_id=None, system_prompt="",
                                  allowed_paths=[], bash_rules=()) if e.kind == "done"]
    assert len(done) == 1 and math.isnan(done[0].cost_usd)
    own = ClaudeCodeChat(Link(home=tmp_path), cli=str(fake))
    done = [e for e in own.turn("hi", tmp_path, 10, session_id=None, system_prompt="",
                                allowed_paths=[], bash_rules=()) if e.kind == "done"]
    assert done[0].cost_usd == pytest.approx(1.2065)
