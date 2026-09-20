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

from compute import ComputeNotFound, available_computes, get_compute
from compute.ssh import JOB_DIRNAME, SshCompute
from framework import computes
from framework.cli import main

LIVE = os.environ.get("AI4SCI_LIVE_SSH", "")


@pytest.fixture
def registry_file(tmp_path, monkeypatch):
    file = tmp_path / "computes.yaml"
    monkeypatch.setenv(computes.PATH_ENV, str(file))
    return file


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
    assert remote == f"/data/ai4sci/{local.resolve().as_posix().lstrip('/')}"
    assert ssh.local_dir_for(remote) == local.resolve()
    with pytest.raises(AssertionError, match="不在远端根"):
        ssh.local_dir_for("/elsewhere/x")


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
    assert "export AI4SCI_SEED=42" in seen["script"]
    assert Path(job.stderr_path) == (tmp_path / "run").resolve() / JOB_DIRNAME / "stderr.log"


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
    assert computes.default_name() == "box"
    assert computes.add("box", "ssh", {"host": "h2", "user": "u", "key": "k", "root": "/r"}) \
        .params["port"] == computes.DEFAULT_SSH_PORT  # 同名覆盖：AutoDL 关机重开端口会变
    computes.remove("box")
    assert computes.default_name() == "local" and "box" not in computes.load().entries
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
    assert main(["compute", "default", "box"]) == 0 and computes.default_name() == "box"
    assert main(["show", "computes"]) == 0
    out = capsys.readouterr().out
    assert "box\tssh\tu@h:22\t无 GPU\t未探测\t(缺省)" in out
    assert main(["compute", "remove", "box"]) == 0 and main(["compute", "remove", "box"]) == 2


# ── 连真机器 ────────────────────────────────────────────────────────────────
live = pytest.mark.skipif(not LIVE, reason="AI4SCI_LIVE_SSH=<清单里的名字> 才连真机器")


@pytest.fixture
def real_registry(monkeypatch):
    """连真机器的测试要读真清单（conftest 把它隔离掉了）。"""
    monkeypatch.delenv(computes.PATH_ENV, raising=False)


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
    from framework.capabilities.design.baseline import run_baseline
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
    results = json.loads((run_dir / "iters" / "iter_1" / "results.json").read_text("utf-8"))
    assert abs(results["metrics"]["val_mse"] - 0.001) < 1e-9


def test_remote_prelude_reuses_the_boxes_pip_mirror_for_uv():
    """AutoDL 直连 pypi.org 只有 19 KB/s：那台机器 pip 配了镜像就让 uv 也用，但只当额外索引
    （镜像落后 PyPI 几天，缺的版本回 pypi.org），http 的镜像还要放行不安全主机。"""
    from compute.ssh import PATH_PRELUDE

    assert "pip config list" in PATH_PRELUDE and "global.index-url" in PATH_PRELUDE
    assert "UV_INDEX=" in PATH_PRELUDE and "UV_INDEX_STRATEGY=unsafe-best-match" in PATH_PRELUDE
    assert "UV_INSECURE_HOST" in PATH_PRELUDE and "UV_DEFAULT_INDEX" not in PATH_PRELUDE
    assert "ServerAliveInterval=30" in _ssh()._ssh_argv()
