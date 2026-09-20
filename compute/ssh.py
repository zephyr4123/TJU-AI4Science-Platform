"""SSH 算力后端：一台能 ssh 上去的 Linux（AutoDL、实验室机器、学校集群的登录节点都一样）。

put=rsync 过去，submit=远端 `nohup setsid` 起 launcher 拿 pid，wait=轮询退出码文件，
cancel=远端杀进程组，get=rsync 回来，check=探一遍（连接、Python、uv 缺就装、GPU、磁盘）。
只认密钥：参数里只有 主机 / 端口 / 用户 / 密钥路径 / 远端根目录，没有密码这回事（P-23）；
`ssh` 一律 `BatchMode=yes`，要密码就是没配好，当场失败不挂着等人敲。

远端命令一律 `bash -lc <脚本>`：登录 shell 才有 conda / `~/.local/bin`（uv 装在那）这些 PATH；
脚本整段 shlex.quote 成一个参数（不走 stdin：脚本里任何读 stdin 的命令都会把后半段脚本吃掉，
实测 uv 的安装脚本就这样卡死）。远端路径映射：本地绝对路径去掉开头的 `/`
接在远端根目录后面（`/root/ai4sci/Users/…/experiment/1/iters/iter_3`），长但一眼能对上、两边可逆。
远端 venv 由 framework 按 `env/` 用这台机器上的 uv 建（`uv` 属性），镜像里预装的 Python / torch
一概不用——版本才可追溯。
"""

from __future__ import annotations

import shlex
import subprocess
import time
from pathlib import Path

from compute import ExitStatus, Job, Outcome, Probe

IGNORED = (".git", ".ai4sci", "__pycache__", ".venv", ".job")
JOB_DIRNAME = ".job"
EXIT_FILE = "exit.code"
_POLL_S = 5.0
_CONNECT_TIMEOUT_S = 20
_PROBE_TIMEOUT_S = 300  # 装 uv 要联网，给足
# 装 uv：先走 PyPI 的 wheel（`pip install --user`，国内机器也通、十秒），不行再走 astral 的安装脚本
# （它从 GitHub 下二进制，实测 AutoDL 上卡死；AutoDL 有 /etc/network_turbo 学术加速，有就先 source）
UV_INSTALL = ("python3 -m pip install --user --quiet --force-reinstall uv"
              " </dev/null >/dev/null 2>&1"
              " || { [ -f /etc/network_turbo ] && . /etc/network_turbo; "
              "curl -LsSf https://astral.sh/uv/install.sh | sh </dev/null >/dev/null 2>&1; }")
# 每条远端命令前面都跑的一段：登录 shell 之外再保一手 PATH（uv 装在 ~/.local/bin，有的镜像的 profile
# 不加它）；那台机器的 pip 配了镜像源（AutoDL 配的是 aliyun）就让 uv 也用——实测 AutoDL 直连 pypi.org
# 只有 19 KB/s，torch 的 CUDA 轮子几个 GB 一小时下不完；镜像会落后 PyPI 几天，所以只当额外的索引
# （UV_INDEX + unsafe-best-match：镜像有就从镜像拿，没有的版本回 pypi.org），不当唯一的源
PATH_PRELUDE = """export PATH="$HOME/.local/bin:$PATH"
__idx="$(python3 -m pip config list 2>/dev/null \\
  | sed -n "s/^global.index-url='\\(.*\\)'$/\\1/p" | head -1)"
if [ -n "$__idx" ]; then
  export UV_INDEX="$__idx" UV_INDEX_STRATEGY=unsafe-best-match
  case "$__idx" in http://*) __h="${__idx#http://}"; export UV_INSECURE_HOST="${__h%%/*}";; esac
fi"""


class SshError(RuntimeError):
    """ssh / rsync 本身失败（连不上、密钥不对、远端命令起不来）。信息带 stderr。"""


class SshCompute:
    kind = "ssh"

    def __init__(self, host: str, user: str, key: str, root: str, port: int = 22) -> None:
        assert host and user and key and root, "ssh 算力要 host / user / key / root 四样"
        self.host, self.user, self.port = host, user, int(port)
        self.key = str(Path(key).expanduser())
        self.root = root.rstrip("/")
        self._live: dict[int, float] = {}

    # ── 形状 ────────────────────────────────────────────────────────────
    @property
    def uv(self) -> list[str]:
        return ["uv"]

    def remote_dir_for(self, local_dir: Path) -> str:
        return f"{self.root}/{Path(local_dir).resolve().as_posix().lstrip('/')}"

    def local_dir_for(self, remote_dir: str) -> Path:
        assert remote_dir.startswith(self.root + "/"), f"{remote_dir} 不在远端根 {self.root} 下"
        return Path("/" + remote_dir[len(self.root) + 1:])

    # ── ssh 底座 ────────────────────────────────────────────────────────
    def _ssh_argv(self) -> list[str]:
        # ServerAlive：长命令期间没输出时 NAT / 平台的 SSH 通道会掐连接，心跳保着
        return ["ssh", "-p", str(self.port), "-i", self.key, "-o", "BatchMode=yes",
                "-o", "StrictHostKeyChecking=accept-new",
                "-o", f"ConnectTimeout={_CONNECT_TIMEOUT_S}",
                "-o", "ServerAliveInterval=30", "-o", "ServerAliveCountMax=6",
                f"{self.user}@{self.host}"]

    def _sh(self, script: str, *, timeout_s: float = 120.0,
            check: bool = True) -> subprocess.CompletedProcess[str]:
        """在远端登录 shell 里跑一段脚本，返回 CompletedProcess；失败带 stderr 抛。"""
        remote = f"bash -lc {shlex.quote(PATH_PRELUDE + chr(10) + script)}"
        try:
            proc = subprocess.run([*self._ssh_argv(), remote], stdin=subprocess.DEVNULL,
                                  capture_output=True, text=True, timeout=timeout_s, check=False)
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise SshError(f"ssh {self.user}@{self.host}:{self.port} 起不来或超时：{exc}") from exc
        if check and proc.returncode != 0:
            raise SshError(f"远端命令失败（退出码 {proc.returncode}）："
                           f"{proc.stderr.strip()[-1500:]}\n脚本：{script[:300]}")
        return proc

    def _rsync(self, src: str, dst: str, *, timeout_s: float = 1800.0) -> None:
        argv = ["rsync", "-az", "--delete", *(f"--exclude={name}" for name in IGNORED),
                "-e", " ".join(shlex.quote(a) for a in self._ssh_argv()[:-1]), src, dst]
        try:
            proc = subprocess.run(argv, capture_output=True, text=True, timeout=timeout_s,
                                  check=False)
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise SshError(f"rsync 起不来或超时：{exc}") from exc
        if proc.returncode != 0:
            raise SshError(f"rsync 失败（退出码 {proc.returncode}）：{proc.stderr.strip()[-1500:]}")

    def _target(self) -> str:
        return f"{self.user}@{self.host}"

    # ── 五个动作 ─────────────────────────────────────────────────────────
    def put(self, local_dir: Path, remote_dir: str) -> None:
        """快照过去。远端目录已在只有一种解释：那一轮被杀了没走完，语义同 local（续跑收尾）。"""
        q = shlex.quote(remote_dir)
        probe = self._sh(f"test -e {q} && echo EXISTS || mkdir -p {q}", check=False)
        if "EXISTS" in probe.stdout:
            raise FileExistsError(
                f"快照目录已存在，可能是被杀的一轮，请跑 ai4sci loop resume 收尾：{remote_dir}")
        self._rsync(f"{Path(local_dir).resolve()}/", f"{self._target()}:{remote_dir}/")

    def sync(self, local_dir: Path, remote_dir: str) -> None:
        """同步过去（允许已存在）：设计那包建远端 venv、跑基线用；快照那条路走 `put`。"""
        self._sh(f"mkdir -p {shlex.quote(remote_dir)}")
        self._rsync(f"{Path(local_dir).resolve()}/", f"{self._target()}:{remote_dir}/")

    def run(self, remote_dir: str, cmd: list[str], env: dict[str, str],
            timeout_s: float) -> Outcome:
        """同步跑完一条命令（远端建 venv、算清单、跑基线），退出码与两路输出原样带回。

        不在一条 ssh 连接里干等：建 venv 装 torch 要几十分钟，一条没输出的长连接会被掐（实测
        AutoDL 上装到一半断了）。走 submit / wait 那条路——远端 nohup 起、轮询退出码——再把两份
        日志 cat 回来。
        """
        try:
            job = self.submit(remote_dir, cmd, env, timeout_s)
        except SshError as exc:
            return Outcome(exit_code=255, stdout="", stderr=str(exc))
        status = self.wait(job)
        logs = f"{remote_dir}/{JOB_DIRNAME}"
        try:
            script = (f"cat {shlex.quote(logs + '/stdout.log')} 2>/dev/null; echo __AI4SCI_SEP__; "
                      f"cat {shlex.quote(logs + '/stderr.log')} 2>/dev/null")
            out = self._sh(script, check=False).stdout
        except SshError as exc:
            return Outcome(exit_code=255, stdout="", stderr=str(exc))
        stdout, _, stderr = out.partition("__AI4SCI_SEP__\n")
        if status.timed_out:
            stderr += f"\n超过 {timeout_s:g} 秒，已杀"
        code = status.exit_code if status.exit_code is not None else 255
        return Outcome(exit_code=code, stdout=stdout, stderr=stderr)

    def submit(self, remote_dir: str, cmd: list[str], env: dict[str, str],
               timeout_s: float) -> Job:
        assert timeout_s > 0, f"timeout_s 必须是正数，得到 {timeout_s!r}"
        q = shlex.quote(remote_dir)
        exports = "\n".join(f"export {k}={shlex.quote(v)}" for k, v in env.items())
        command = " ".join(shlex.quote(c) for c in cmd)
        # setsid：自成进程组，超时才有一整组可杀；退出码写文件：wait 不是亲爹，只能这么拿
        inner = shlex.quote(f"{command}; echo $? > {JOB_DIRNAME}/{EXIT_FILE}")
        script = (f"cd {q} || exit 127\nmkdir -p {JOB_DIRNAME} || exit 126\n{exports}\n"
                  f"nohup setsid bash -c {inner}"
                  f" > {JOB_DIRNAME}/stdout.log 2> {JOB_DIRNAME}/stderr.log < /dev/null &\n"
                  "echo $!")
        proc = self._sh(script)  # cd 不进去、建不了 .job 都在这儿炸，不会拿到一个假 pid
        pid = int(proc.stdout.strip().splitlines()[-1])
        local = self.local_dir_for(remote_dir) / JOB_DIRNAME
        self._live[pid] = time.time()
        # 日志路径记本地镜像：get 回来之后就在那儿，读 stderr 尾巴的人不用知道远端
        return Job(pid=pid, pgid=pid, started_at=time.time(), remote_dir=remote_dir,
                   stdout_path=str(local / "stdout.log"), stderr_path=str(local / "stderr.log"),
                   timeout_s=float(timeout_s))

    def wait(self, job: Job, timeout_s: float | None = None) -> ExitStatus:
        limit = job.timeout_s if timeout_s is None else timeout_s
        deadline = time.monotonic() + limit
        code: int | None = None
        timed_out = False
        exit_path = f"{job.remote_dir}/{JOB_DIRNAME}/{EXIT_FILE}"
        script = (f"if [ -f {shlex.quote(exit_path)} ]; then cat {shlex.quote(exit_path)}; "
                  f"elif kill -0 {job.pid} 2>/dev/null; then echo RUNNING; else echo DEAD; fi")
        while True:
            out = self._sh(script).stdout.strip().splitlines()[-1]
            if out == "RUNNING":
                if time.monotonic() >= deadline:
                    timed_out = True
                    break
                time.sleep(_POLL_S)
                continue
            if out == "DEAD":
                break  # 进程没了、退出码没写下：未知（None），不填 0
            code = int(out)
            break
        if timed_out:
            self.cancel(job)
        return ExitStatus(exit_code=code, timed_out=timed_out,
                          elapsed_s=time.time() - job.started_at,
                          stdout_path=job.stdout_path, stderr_path=job.stderr_path)

    def cancel(self, job: Job) -> None:
        """远端杀整组：先 TERM 再 KILL；组不在了不算错。"""
        self._sh(f"kill -TERM -- -{job.pgid} 2>/dev/null; sleep 1; "
                 f"kill -KILL -- -{job.pgid} 2>/dev/null; true", check=False)

    def get(self, remote_dir: str, local_dir: Path) -> None:
        Path(local_dir).mkdir(parents=True, exist_ok=True)
        argv_src = f"{self._target()}:{remote_dir}/"
        # 回来的时候不 --delete：本地那份可能有远端没有的东西（job.json 是本地写的）
        argv = ["rsync", "-az", *(f"--exclude={name}" for name in IGNORED if name != JOB_DIRNAME),
                "-e", " ".join(shlex.quote(a) for a in self._ssh_argv()[:-1]),
                argv_src, f"{Path(local_dir).resolve()}/"]
        proc = subprocess.run(argv, capture_output=True, text=True, timeout=1800, check=False)
        if proc.returncode != 0:
            raise SshError(f"rsync 回来失败（退出码 {proc.returncode}）："
                           f"{proc.stderr.strip()[-1500:]}")

    # ── 探一遍 ───────────────────────────────────────────────────────────
    def check(self) -> Probe:
        """接机器时与之后随时：连接、Python、uv（缺就装）、GPU、远端根的磁盘；连不上也是一条。"""
        probe = Probe()
        started = time.monotonic()
        try:
            out = self._sh("echo HOST=$(hostname)", timeout_s=_CONNECT_TIMEOUT_S + 10)
        except SshError as exc:
            probe.items.append(("连接", False, str(exc).splitlines()[0][:200]))
            return probe
        probe.hostname = _field(out.stdout, "HOST")
        probe.items.append(("连接", True,
                            f"{time.monotonic() - started:.1f} s · {probe.hostname}"))
        script = f"""
echo PY=$(python3 --version 2>&1 || python --version 2>&1)
if ! command -v uv >/dev/null 2>&1; then
  echo UVINSTALL=1; {UV_INSTALL}
fi
{PATH_PRELUDE}
echo UV=$(uv --version 2>/dev/null | awk '{{print $2}}')
echo GPU=$(nvidia-smi --query-gpu=name,memory.total --format=csv,noheader 2>/dev/null | head -1)
mkdir -p {shlex.quote(self.root)} \\
  && echo DISK=$(df -h {shlex.quote(self.root)} | awk 'NR==2{{print $4}}')
echo RSYNC=$(command -v rsync)
"""
        out = self._sh(script, timeout_s=_PROBE_TIMEOUT_S, check=False)
        text = out.stdout
        probe.python = _field(text, "PY")
        probe.uv = _field(text, "UV")
        probe.gpu = _field(text, "GPU")
        disk = _field(text, "DISK")
        probe.items.append(("Python", bool(probe.python), probe.python or "没有 python3"))
        installed = "UVINSTALL=1" in text
        probe.items.append(("uv", bool(probe.uv),
                            (probe.uv + ("（刚装的）" if installed else "")) if probe.uv
                            else "没有，也装不上（远端出不了网？）"))
        probe.items.append(("GPU", True, probe.gpu or "无"))
        probe.items.append(("磁盘", bool(disk),
                            f"{self.root} 剩 {disk}" if disk else f"{self.root} 建不出来"))
        rsync = _field(text, "RSYNC")
        probe.items.append(("rsync", bool(rsync), rsync or "远端没有 rsync：apt install rsync"))
        return probe


def _field(text: str, key: str) -> str:
    for line in text.splitlines():
        if line.startswith(key + "="):
            return line[len(key) + 1:].strip()
    return ""


def make_compute(host: str, user: str, key: str, root: str, port: int = 22) -> SshCompute:
    return SshCompute(host=host, user=user, key=key, root=root, port=port)
