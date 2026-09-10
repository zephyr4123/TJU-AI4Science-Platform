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

from backends import BackendNotFound, Runner, RunResult, available_backends, get_backend
from backends._snapshot import diff, snapshot
from backends.claude_code import ClaudeCodeRunner, final_metrics, kill_tree, parse_events

FIXTURE = Path(__file__).parent / "fixtures" / "claude_stream_sample.jsonl"


@pytest.fixture
def sample_events() -> list[dict]:
    events, junk = parse_events(FIXTURE.read_text(encoding="utf-8").splitlines(keepends=True))
    assert junk == [], "夹具应当每行都是合法 JSON"
    return events


# --- 端口 -----------------------------------------------------------------


def test_get_backend_returns_runner_shaped_object():
    runner = get_backend("claude_code")
    assert isinstance(runner, Runner)


def test_backend_not_found_lists_available_names():
    with pytest.raises(BackendNotFound) as excinfo:
        get_backend("codex")
    # 报错必须把可用名字带上，否则调用方只能去翻源码
    assert "claude_code" in str(excinfo.value)
    assert available_backends() == ["claude_code"]


# --- argv 组装 ------------------------------------------------------------


def test_argv_turns_allowed_paths_into_absolute_tool_rules(tmp_path: Path):
    code = tmp_path / "code"
    code.mkdir()
    argv = ClaudeCodeRunner().build_argv("改点东西", tmp_path, [code])
    rules = argv[argv.index("--allowedTools") + 1 : argv.index("--max-turns")]
    # `//` 前缀是实测结论：单个 `/` 会被当成项目根相对路径，规则不生效
    assert f"Edit(//{str(code).lstrip('/')}/**)" in rules
    assert f"Write(//{str(code).lstrip('/')}/**)" in rules
    assert f"Read(//{str(tmp_path).lstrip('/')}/**)" in rules
    # 没给 bash_rules 就一条 Bash 规则都不该有：Bash 是绕开路径白名单的口子
    assert not [r for r in rules if r.startswith("Bash(")]


def test_argv_carries_isolation_flags_and_never_bypasses_permissions(tmp_path: Path):
    argv = ClaudeCodeRunner().build_argv("hi", tmp_path, [tmp_path])
    for flag in ("--no-session-persistence", "--strict-mcp-config", "--disable-slash-commands",
                 "--setting-sources", "--output-format", "stream-json", "--verbose"):
        assert flag in argv
    # `--setting-sources` 的值必须是空串：它是不加载 CLAUDE.md / hook / plugin 的承重位
    assert argv[argv.index("--setting-sources") + 1] == ""
    assert argv[argv.index("--permission-mode") + 1] == "dontAsk"
    assert "--dangerously-skip-permissions" not in argv
    assert "bypassPermissions" not in argv


def test_env_config_has_read_points_and_defaults(tmp_path: Path, monkeypatch):
    argv = ClaudeCodeRunner().build_argv("hi", tmp_path, [tmp_path])
    assert argv[argv.index("--max-turns") + 1] == "30"
    assert argv[argv.index("--max-budget-usd") + 1] == "2.0"
    assert "--model" not in argv  # 缺省不传，用 CLI 自己的默认模型

    monkeypatch.setenv("AI4SCI_EXECUTOR_MAX_TURNS", "7")
    monkeypatch.setenv("AI4SCI_EXECUTOR_MAX_BUDGET_USD", "0.5")
    monkeypatch.setenv("AI4SCI_EXECUTOR_MODEL", "opus")
    argv = ClaudeCodeRunner().build_argv("hi", tmp_path, [tmp_path])
    assert argv[argv.index("--max-turns") + 1] == "7"
    assert argv[argv.index("--max-budget-usd") + 1] == "0.5"
    assert argv[argv.index("--model") + 1] == "opus"


@pytest.mark.parametrize("value", ["0", "-3"])
def test_env_config_rejects_nonsense_instead_of_falling_back(tmp_path: Path, monkeypatch, value):
    monkeypatch.setenv("AI4SCI_EXECUTOR_MAX_TURNS", value)
    with pytest.raises(AssertionError):
        ClaudeCodeRunner().build_argv("hi", tmp_path, [tmp_path])


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

    result: RunResult = get_backend("claude_code").run(
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
    runner = ClaudeCodeRunner(cli=str(fake))
    result = runner.run("noop", cwd=cwd, timeout_s=10.0, allowed_paths=[cwd])
    assert result.timed_out is False
    assert result.cost_usd == 0.01
    assert result.stdout_tail.endswith("W" * 100)
    assert list((cwd / ".ai4sci").glob("executor-*.stderr.log"))
