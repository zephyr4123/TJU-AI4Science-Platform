"""SSH 算力后端与按人的算力清单（纲领 P-23）。

不联网的：路径映射两边可逆、ssh 只认密钥（BatchMode、-i）、submit 的远端脚本形状、清单文件的读写与
形状（没有 password、kind 只认 local / ssh、缺省要在清单里）、CLI 的 list / remove / default。
连真机器的：`AI4SCI_LIVE_SSH=<清单里的名字>` 才跑——探测、同步 / 起任务 / 等 / 取回一整圈、
在那台机器上建 venv 跑基线、内环一轮在远端跑。CI 不跑。
"""

from __future__ import annotations

import json
import os
import shutil
from pathlib import Path

import pytest

import procs
from compute import ComputeNotFound, available_computes, get_compute
from compute.ssh import JOB_DIRNAME, SshCompute
from framework import computes, paths
from framework.cli import main

LIVE = os.environ.get("AI4SCI_LIVE_SSH", "")


@pytest.fixture
def registry_file():
    """清单在平台的家里（conftest 把家指到了 tmp）。"""
    return paths.computes_file()


def _ssh() -> SshCompute:
    return SshCompute(host="h.example", user="u", key="~/.ssh/id_ed25519",
                      root="/data/ai4sci", port=2222)


# ── 形状（不联网）───────────────────────────────────────────────────────────
def test_port_lists_both_kinds_and_builds_ssh_from_params():
    assert available_computes() == ["local", "ssh"]
    ssh = get_compute("ssh", host="h", user="u", key="k", root="/r", port=22)
    assert ssh.kind == "ssh" and ssh.uv == ["uv"]
    with pytest.raises(ComputeNotFound, match="slurm"):
        get_compute("slurm")
    with pytest.raises(AssertionError, match="四样"):
        SshCompute(host="", user="u", key="k", root="/r")


def test_remote_dir_mapping_is_reversible_and_readable(tmp_path):
    ssh = _ssh()
    local = tmp_path / "ws" / "experiment" / "1" / "iters" / "iter_3"
    remote = ssh.remote_dir_for(local)
    tail = local.resolve().as_posix()
    tail = f"{tail[0].lower()}{tail[2:]}" if local.resolve().drive else tail.lstrip("/")
    assert remote == f"/data/ai4sci/{tail}" and ":" not in remote  # Windows 的盘符是一级目录
    assert ssh.local_dir_for(remote) == local.resolve()
    with pytest.raises(AssertionError, match="不在远端根"):
        ssh.local_dir_for("/elsewhere/x")


class _ThisMachine(SshCompute):
    """「远端」就是本机：ssh 换成本机的 bash（Windows 上是 Git Bash，带 tar 与 find）。"""

    def _ssh_argv(self) -> list[str]:
        return [procs.bash(), "-c"]


def test_without_rsync_files_travel_as_tar_with_the_same_effect(tmp_path, monkeypatch):
    """本机没有 rsync（Windows 都没有，外层 #210）就打 tar 走 ssh：推过去删远端多出来的、排除的
    不碰（远端的 .venv 留着），拉回来不删本地的、`.ai4sci` 不带回来。"""
    which = shutil.which
    monkeypatch.setattr("compute.ssh.shutil.which",
                        lambda name: None if name == "rsync" else which(name))
    box = _ThisMachine(host="h", user="u", key="k", root=(tmp_path / "remote").as_posix())
    local = tmp_path / "local"
    (local / "code").mkdir(parents=True)
    (local / "code" / "train.py").write_text("print('中文')\n", encoding="utf-8")
    (local / "empty").mkdir()
    (local / ".venv").mkdir()
    (local / ".venv" / "mine").write_text("本机的环境", encoding="utf-8")
    remote = box.remote_dir_for(local)
    there = Path(remote)
    (there / ".venv").mkdir(parents=True)
    (there / ".venv" / "theirs").write_text("远端的环境", encoding="utf-8")
    (there / "stale.txt").write_text("上一轮留下的", encoding="utf-8")

    box.sync(local, remote)
    assert (there / "code" / "train.py").read_text(encoding="utf-8") == "print('中文')\n"
    assert (there / "empty").is_dir() and not (there / "stale.txt").exists()
    assert (there / ".venv" / "theirs").is_file() and not (there / ".venv" / "mine").exists()

    (there / "out").mkdir()
    (there / "out" / "results.json").write_text("{}", encoding="utf-8")
    (there / ".ai4sci").mkdir()
    (there / ".ai4sci" / "events.jsonl").write_text("", encoding="utf-8")
    back = tmp_path / "back"
    back.mkdir()
    (back / "job.json").write_text("{}", encoding="utf-8")
    box.get(remote, back)
    assert (back / "out" / "results.json").is_file() and (back / "code" / "train.py").is_file()
    assert (back / "job.json").is_file() and not (back / ".ai4sci").exists()


def test_ssh_argv_only_uses_keys_and_never_prompts():
    argv = _ssh()._ssh_argv()
    assert argv[:3] == ["ssh", "-p", "2222"] and "-i" in argv
    assert argv[argv.index("-i") + 1] == str(Path("~/.ssh/id_ed25519").expanduser())
    assert "BatchMode=yes" in argv and argv[-1] == "u@h.example"
    assert not any("password" in a.lower() for a in argv)


def test_submit_script_starts_a_session_and_records_the_exit_code(monkeypatch, tmp_path):
    """远端脚本：setsid 自成进程组、退出码写进 .job/exit.code、日志路径记成本地镜像。"""
    ssh = _ssh()
    seen: dict = {}

    class Proc:
        returncode = 0
        stdout = "4242\n"
        stderr = ""

    def fake_sh(script, **kw):
        seen["script"] = script
        return Proc()

    monkeypatch.setattr(ssh, "_sh", fake_sh)
    remote = ssh.remote_dir_for(tmp_path / "run")
    job = ssh.submit(remote, ["bash", "harness/launcher.sh"], {"AI4SCI_SEED": "42"}, 30.0)
    assert job.pid == 4242 and job.pgid == 4242 and job.remote_dir == remote
    assert "nohup setsid bash -c" in seen["script"] and "exit.code" in seen["script"]
    assert f"rm -f {JOB_DIRNAME}/exit.code" in seen["script"]  # 同目录连着两次 submit 不读旧的
    assert "export AI4SCI_SEED=42" in seen["script"]
    assert f"tee {JOB_DIRNAME}/pgid" in seen["script"]  # 人叫停时另一个进程凭它下手
    assert Path(job.stderr_path) == (tmp_path / "run").resolve() / JOB_DIRNAME / "stderr.log"


def test_cancel_under_kills_only_live_groups_of_this_directory(monkeypatch, tmp_path):
    """人叫停时下手的是另一个进程，只知道产出目录：远端脚本找目录下每个 .job/pgid，跑完的
    （有 exit.code）不碰、进程组号被别人复用的（组长 cwd 不是这个目录）不碰，其余先 TERM 再
    KILL，报回杀了谁。"""
    ssh = _ssh()
    seen: dict = {}

    class Proc:
        returncode = 0
        stdout = "4242\n4300\n"
        stderr = ""

    def fake_sh(script, **kw):
        seen["script"] = script
        return Proc()

    monkeypatch.setattr(ssh, "_sh", fake_sh)
    remote = ssh.remote_dir_for(tmp_path / "design" / "4")
    assert ssh.cancel_under(remote) == [4242, 4300]
    script = seen["script"]
    assert f"find {remote} -path '*/{JOB_DIRNAME}/pgid'" in script  # 路径没空格时 quote 不加引号
    assert "exit.code" in script and "/proc/$pg/cwd" in script
    assert "kill -TERM -- -$pg" in script and "kill -KILL -- -$pg" in script


# ── 按人的清单（不联网）─────────────────────────────────────────────────────
def test_registry_has_local_by_default_and_round_trips(registry_file):
    registry = computes.load()
    assert list(registry.entries) == ["local"] and registry.default == "local"
    assert not registry_file.exists()
    entry = computes.add("box", "ssh", {"host": "h", "user": "u", "key": "~/.ssh/k",
                                        "root": "/r", "port": 2222})
    assert entry.params["port"] == 2222 and registry_file.is_file()
    text = registry_file.read_text(encoding="utf-8")
    assert "password" not in text and "kind: ssh" in text and "port: 2222" in text
    again = computes.load()
    assert list(again.entries) == ["local", "box"] and again.get("box").params["host"] == "h"
    computes.set_default("box")
    assert computes.load().default == "box"
    assert computes.add("box", "ssh", {"host": "h2", "user": "u", "key": "k", "root": "/r"}) \
        .params["port"] == computes.DEFAULT_SSH_PORT  # 同名覆盖：AutoDL 关机重开端口会变
    computes.remove("box")
    assert computes.load().default == "local" and "box" not in computes.load().entries
    with pytest.raises(ComputeNotFound, match="有：local"):
        computes.load().get("nope")
    with pytest.raises(computes.ComputesInvalid, match="删不掉"):
        computes.remove("local")


SSH_OK = {"kind": "ssh", "host": "h", "user": "u", "key": "k", "root": "/r"}


@pytest.mark.parametrize("doc, message", [
    ({**SSH_OK, "password": "x"}, "不收密码"),
    ({k: v for k, v in SSH_OK.items() if k != "root"}, "缺 \\['root'\\]"),
    ({"kind": "slurm"}, "kind 只认"),
    ({**SSH_OK, "extra": 1}, "多了"),
    ({**SSH_OK, "port": "22"}, "端口号"),
])
def test_registry_rejects_bad_entries(registry_file, doc, message):
    registry_file.write_text(json.dumps({"computes": {"box": doc}}), encoding="utf-8")
    with pytest.raises(computes.ComputesInvalid, match=message):
        computes.load()


def test_registry_default_must_exist_and_local_stays_local(registry_file):
    registry_file.write_text(json.dumps({"computes": {}, "default": "gone"}), encoding="utf-8")
    with pytest.raises(computes.ComputesInvalid, match="default 'gone'"):
        computes.load()
    registry_file.write_text(json.dumps({"computes": {"local": {"kind": "ssh", "host": "h",
                                                                "user": "u", "key": "k",
                                                                "root": "/r"}}}), encoding="utf-8")
    with pytest.raises(computes.ComputesInvalid, match="只能是 local"):
        computes.load()


def test_cli_list_remove_default_and_add_rejects_missing_key(registry_file, capsys, tmp_path):
    assert main(["compute", "list"]) == 0
    assert capsys.readouterr().out.splitlines() == ["local\tlocal\t本机\t无 GPU\t未探测\t(缺省)"]
    assert main(["compute", "add", "box", "--ssh", "u@h:22", "--key", str(tmp_path / "nokey")]) == 2
    assert "密钥文件不存在" in capsys.readouterr().err
    assert main(["compute", "add", "box", "--ssh", "u@h:99999x", "--key", "~/.ssh"]) == 2
    computes.add("box", "ssh", {"host": "h", "user": "u", "key": "k", "root": "/r"})
    assert main(["compute", "default", "box"]) == 0 and computes.load().default == "box"
    assert main(["show", "computes"]) == 0
    out = capsys.readouterr().out
    assert "box\tssh\tu@h:22\t无 GPU\t未探测\t(缺省)" in out
    assert main(["compute", "remove", "box"]) == 0 and main(["compute", "remove", "box"]) == 2


def test_a_machine_that_checks_out_is_followed_by_the_environment_question(
        registry_file, capsys, tmp_path, monkeypatch):
    """外层 #287：探测过了，下一步是 P-23 的那一问——用机器上现成的环境还是隔离新建——在接上机器的
    那一刻由 CLI 说，指南里不再写一大段；探测没过不推，照 ✗ 那几项说。"""
    from compute import Probe

    key = tmp_path / "id"
    key.write_text("k", encoding="utf-8")
    probe = Probe(items=[("连接", True, "box"), ("已有环境", True, "/opt/py 3.11 torch 2.3 cuda")])

    class Checks:
        def check(self) -> Probe:
            return probe

    monkeypatch.setattr(computes, "instance", lambda name: Checks())
    assert main(["compute", "add", "box", "--ssh", "u@h:22", "--key", str(key)]) == 0
    added = capsys.readouterr().out.splitlines()[-1]
    assert added.startswith("ok box\t可用\t写入 ") and "\tnext=" in added
    tail = added.partition("\tnext=")[2]
    assert "租的" in tail and "实验室" in tail
    assert "ai4sci env use --compute box" in tail and "ai4sci env resolve --compute box" in tail
    assert main(["compute", "check", "box"]) == 0
    assert capsys.readouterr().out.splitlines()[-1] == f"ok box\t可用\tnext={tail}"
    probe.items.append(("GPU", False, "nvidia-smi 不在"))
    assert main(["compute", "check", "box"]) == 1
    assert "next=" not in capsys.readouterr().out


# ── 连真机器 ────────────────────────────────────────────────────────────────
live = pytest.mark.skipif(not LIVE, reason="AI4SCI_LIVE_SSH=<清单里的名字> 才连真机器")


@pytest.fixture
def real_registry(monkeypatch):
    """连真机器的测试要读真清单：平台真的家（conftest 把它隔离掉了）。"""
    monkeypatch.delenv(paths.HOME_ENV, raising=False)


@live
def test_live_check_sync_submit_wait_get_round_trip(tmp_path, real_registry):
    ssh = computes.instance(LIVE)
    probe = ssh.check()
    assert probe.ok, probe.items
    assert probe.hostname and probe.uv
    local = tmp_path / "job"
    local.mkdir()
    (local / "go.sh").write_text("echo hello-$AI4SCI_SEED > out.txt; exit 3\n", encoding="utf-8")
    remote = ssh.remote_dir_for(local)
    ssh.put(local, remote)
    with pytest.raises(FileExistsError):
        ssh.put(local, remote)  # 快照语义：已在就拒
    job = ssh.submit(remote, ["bash", "go.sh"], {"AI4SCI_SEED": "7"}, 60.0)
    status = ssh.wait(job)
    assert status.exit_code == 3 and not status.timed_out
    ssh.get(remote, local)
    assert (local / "out.txt").read_text(encoding="utf-8").strip() == "hello-7"
    assert Path(status.stdout_path).is_file()
    slow = tmp_path / "slow"
    slow.mkdir()
    (slow / "go.sh").write_text("sleep 120\n", encoding="utf-8")
    from compute.ssh import SshError
    with pytest.raises(SshError, match="127"):
        ssh.submit(ssh.remote_dir_for(slow), ["bash", "go.sh"], {}, 1.0)  # 没 put 过：cd 不进去就炸
    ssh.sync(slow, ssh.remote_dir_for(slow))
    ssh.sync(slow, ssh.remote_dir_for(slow))  # sync 允许已在
    job = ssh.submit(ssh.remote_dir_for(slow), ["bash", "go.sh"], {}, 1.0)
    status = ssh.wait(job, timeout_s=8.0)
    assert status.timed_out and status.exit_code is None


@live
def test_live_baseline_and_one_iteration_run_on_the_box(tmp_path, real_registry):
    from framework.capabilities.auto_research import run_loop
    from framework.experiment.baseline import run_baseline
    from framework.experiment.checkpoint import read_checkpoint
    from tests.fixtures import packs_factory as pf
    from tests.fixtures.scripted_backend import ScriptedRunner
    from tests.test_capability_design import MAKE_RUN0_SH
    from tests.test_experiment_loop import make_loop_pack, open_run, train_for_mse

    ssh = computes.instance(LIVE)
    probe = ssh.check()
    remote_python = probe.python.split()[-1].rsplit(".", 1)[0]  # 远端有的 X.Y，uv 不用去下
    pack = make_loop_pack(tmp_path)
    pf.write_env(pack.pack, python_version=remote_python)
    (pack.pack / "harness" / "make_run0.sh").write_text(MAKE_RUN0_SH, encoding="utf-8")
    for name in ("launcher.sh", "make_run0.sh"):  # 真包由 seal_harness 加执行位，夹具自己加
        (pack.pack / "harness" / name).chmod(0o755)
    pf.refresh_sums(pack.pack)
    shutil.rmtree(pack.pack / "baseline", ignore_errors=True)
    line = run_baseline(pack.pack, ssh)
    assert line.startswith("inner_k=1") and (pack.pack / "baseline" / "sigma.json").is_file()
    assert not (pack.pack / ".venv").exists(), "venv 在远端建，本机不该有"

    run_dir = open_run(pack, compute=ssh, compute_label=computes.load().get(LIVE).label())
    state = read_checkpoint(run_dir)
    assert state["compute"]["name"] == LIVE and state["python"].startswith(ssh.root)
    runner = ScriptedRunner([train_for_mse(0.001)])
    stop = run_loop(run_dir, runner, ssh, max_iters=1)
    assert stop.iter == 1
    text = (run_dir / "iters" / "iter_1" / "results.json").read_text(encoding="utf-8")
    results = json.loads(text)
    assert abs(results["metrics"]["val_mse"] - 0.001) < 1e-9


def test_remote_prelude_reuses_the_boxes_pip_mirror_for_uv():
    """AutoDL 直连 pypi.org 只有 19 KB/s：那台机器 pip 配了镜像就让 uv 也用，但只当额外索引
    （镜像落后 PyPI 几天，缺的版本回 pypi.org），http 的镜像还要放行不安全主机。"""
    from compute.ssh import PATH_PRELUDE

    assert "pip config list" in PATH_PRELUDE and "global.index-url" in PATH_PRELUDE
    assert "UV_INDEX=" in PATH_PRELUDE and "UV_INDEX_STRATEGY=unsafe-best-match" in PATH_PRELUDE
    assert "UV_INSECURE_HOST" in PATH_PRELUDE and "UV_DEFAULT_INDEX" not in PATH_PRELUDE
    assert "ServerAliveInterval=30" in _ssh()._ssh_argv()


def test_probe_env_line_carries_the_interpreter_path():
    """「已有环境」那一行要带解释器绝对路径：`ai4sci env use` 要的就是它，不打出来助理只能猜。"""
    from compute.ssh import _envs, env_line

    text = ("PY=Python 3.12.3\nENV=/root/miniconda3/bin/python\t3.12.3\t2.8.0+cu128 cuda\n"
            "ENV=/root/miniconda3/envs/gua/bin/python\t3.10.12\t-\n"
            "ENV=/opt/py/bin/python\t3.11.0\t-\n")
    lines = [env_line(e) for e in _envs(text)]
    assert lines == [
        "conda base /root/miniconda3/bin/python 3.12.3 torch 2.8.0+cu128 cuda",
        "conda gua /root/miniconda3/envs/gua/bin/python 3.10.12 torch -",
        "/opt/py/bin/python 3.11.0 torch -",
    ]
