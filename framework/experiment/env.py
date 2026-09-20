"""设计那包的环境约定：`env/` 怎么读、怎么判、怎么建成任务级 venv。

任务自带环境，平台 venv 一个包不多装（红线：环境必隔离）。两个文件：

    env/python-version      一行，如 3.14
    env/requirements.lock   逐行 name==version，钉死；可以为空

建 venv 的动作也放在实验族的共享层：同一份 lock 要建在两处
（设计产出里的 `.venv` 给 make_run0.sh，实验产出里的 `.venv` 给每一次实验），两处必须走同一个函数，
否则"设计里能跑、实验里跑不动"这种事迟早发生。本模块只认文件与 uv，不知道包的其它部分。

为什么用 uv：一条工具把找解释器、拉解释器、建 venv、按 lock 同步四件事做完，且是 pip 可装的
轮子，能钉进平台自己的 requirements.lock。uv 不在或解释器拉不下来就抛 `EnvBuildError`，
绝不静默退回到平台 venv（P-7）。

清单必须完整（每个包的传递依赖都钉在里面，`uv pip sync` 是精确安装、不补依赖）：建完 venv
`uv pip check` 一遍，缺依赖在开跑前报，不是跑到 import 才炸。研究者没有现成环境时（非工程师的
常态）由 `resolve_lock` 按几个包名算出完整清单（`uv pip compile`），助理用 `ai4sci env resolve`
调它，不再手写（外层 #117：手写的三行清单让基线一 import 就 ModuleNotFoundError）。
"""

from __future__ import annotations

import importlib.util
import logging
import re
import subprocess
import tempfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from compute import Compute, Outcome

LOGGER = logging.getLogger("ai4sci.env")

ENV_DIRNAME = "env"
PYTHON_VERSION_NAME = "python-version"
REQUIREMENTS_NAME = "requirements.lock"
# 第三个文件，可选：`<算力名字>:<那台机器上的解释器>`——研究者选了「用机器上现成的环境」
# （P-23 的两问）。在时不建 venv，直接拿那个解释器当 AI4SCI_PYTHON；requirements.lock 是那个
# 环境的 pip freeze（出处留档）。
# 换了机器就拒：现成的环境只在那一台上
INTERPRETER_NAME = "interpreter"
VENV_DIRNAME = ".venv"
# harness 经这个环境变量拿到任务 venv 的解释器：框架提交 harness 时设，
# make_run0.sh 缺省指到任务目录的 .venv
PYTHON_ENV = "AI4SCI_PYTHON"
# 框架起 harness 时**保证**给出的另外几个变量（packs.md §2）：一次跑的墙钟预算、评分内部重复
# 次数；起跑时刻由 launcher 自己设给 evaluate.py。保证给出就意味着 harness 拿不到时必须停，
# 不许写默认值——rahman-nll 第一版评分脚本缺 INNER_K 时默认按 5 份算，算出一份看着合法的
# 假成绩，签字的人没看出来（外层 #44）。种子不在此列：AI4SCI_SEED 缺省 42 是契约的一部分。
BUDGET_ENV = "AI4SCI_BUDGET_S"
INNER_K_ENV = "AI4SCI_INNER_K"
START_EPOCH_ENV = "AI4SCI_START_EPOCH"
SEED_ENV = "AI4SCI_SEED"
GUARANTEED_ENV = (PYTHON_ENV, BUDGET_ENV, INNER_K_ENV, START_EPOCH_ENV)

VERSION_RE = re.compile(r"^(\d+)\.(\d+)$")
# 钉死的一行：名字（可带 extras）== 版本；别的写法（>=、URL、-e）一律不收
_PIN_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*(\[[A-Za-z0-9._,\s-]+\])?==[A-Za-z0-9.!+*-]+$")
_STDERR_TAIL = 1500


class EnvBuildError(RuntimeError):
    """venv 建不出来：uv 不在、解释器拉不下来、依赖装不上。调用方按"这个任务现在跑不了"处理。"""


@dataclass(frozen=True)
class EnvSpec:
    python_version: str
    requirements: tuple[str, ...]
    # (算力名字, 解释器路径)：用机器上现成的环境；None 是隔离新建
    interpreter: tuple[str, str] | None = None


def harness_env(python: Path, wall_clock_s: float, inner_k: int) -> dict[str, str]:
    """框架起 harness（内环的 launcher、基线的 make_run0）时给的那组环境变量，两处走同一个函数。"""
    assert inner_k >= 1, f"inner_k 要是正整数：{inner_k!r}"
    assert wall_clock_s > 0, f"wall_clock_s 要是正数：{wall_clock_s!r}"
    return {PYTHON_ENV: str(python), BUDGET_ENV: f"{wall_clock_s:g}", INNER_K_ENV: str(inner_k)}


def env_dir(task_dir: Path) -> Path:
    return Path(task_dir) / ENV_DIRNAME


def venv_python(venv_dir: Path) -> Path:
    """venv 里的解释器路径；只做 POSIX，本项目不跑 Windows。"""
    return Path(venv_dir) / "bin" / "python"


def read_env(task_dir: Path) -> tuple[EnvSpec | None, list[str]]:
    """读 env/ 并逐条校验，返回（规格, 问题清单）；有问题时规格为 None。

    与 pack.validate_pack 同一套约定：问题一行一条、带文件与期望 vs 实际，不抛。
    """
    edir = env_dir(task_dir)
    label = f"{ENV_DIRNAME}/"
    if not edir.is_dir():
        return None, [f"{label}: 目录缺失，任务包必须自带环境（期望 {edir}）"]
    problems: list[str] = []

    version_path = edir / PYTHON_VERSION_NAME
    version = ""
    if not version_path.is_file():
        problems.append(
            f"{label}{PYTHON_VERSION_NAME}: 文件缺失，期望一行如 3.14（{version_path}）"
        )
    else:
        version = version_path.read_text(encoding="utf-8").strip()
        if not VERSION_RE.match(version):
            problems.append(
                f"{label}{PYTHON_VERSION_NAME}: 期望 <major>.<minor> 如 3.14，实际 {version!r}"
            )

    lock_path = edir / REQUIREMENTS_NAME
    requirements: list[str] = []
    if not lock_path.is_file():
        problems.append(
            f"{label}{REQUIREMENTS_NAME}: 文件缺失，零依赖也要有一个空文件（{lock_path}）"
        )
    else:
        for lineno, raw in enumerate(lock_path.read_text(encoding="utf-8").splitlines(), start=1):
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            if not _PIN_RE.match(line):
                problems.append(
                    f"{label}{REQUIREMENTS_NAME}:{lineno}: 期望钉死的 name==version，实际 {line!r}"
                )
                continue
            requirements.append(line)

    interpreter = None
    interp_path = edir / INTERPRETER_NAME
    if interp_path.is_file():
        raw = interp_path.read_text(encoding="utf-8").strip()
        name, _, path = raw.partition(":")
        if not name or not path.startswith("/"):
            problems.append(f"{label}{INTERPRETER_NAME}: 期望 <算力名字>:<绝对路径>，实际 {raw!r}")
        else:
            interpreter = (name, path)
    if problems:
        return None, problems
    return EnvSpec(python_version=version, requirements=tuple(requirements),
                   interpreter=interpreter), []


def build_venv(task_dir: Path, venv_dir: Path) -> Path:
    """本机建 venv：`build_venv_on(LocalCompute)` 的便捷写法，返回解释器路径。"""
    from compute.local import LocalCompute  # 本地适配器只在这条便捷路径上用，避免包顶层就拉它

    local = LocalCompute()
    task_dir, venv_dir = Path(task_dir).resolve(), Path(venv_dir).resolve()
    return Path(build_venv_on(local, str(task_dir), str(venv_dir)))


def build_venv_on(compute: Compute, task_dir: str, venv_dir: str) -> str:
    """在一台算力上按 `<task_dir>/env/` 建（或重建）venv 到 venv_dir，返回那台机器上的解释器路径。

    task_dir / venv_dir 都是**那台机器上**的路径（本机就是本机路径；ssh 由 `remote_dir_for` 映射）。
    `env/` 的规格在本机读（调用方先 `sync` 过去）：设计产出 `design/<n>/` 或实验里的 `work/`。
    四步：`uv venv --python X.Y`（找不到就拉一个）→ 有依赖就 `uv pip sync`（精确对齐 lock）→
    `uv pip check`（清单完整）→ 起一次解释器核对版本。每一步失败都带 stderr 抛 `EnvBuildError`，
    半截的 venv 留在原地给人看，不做"看起来建好了"。uv 是那台机器上的（`compute.uv`）。
    """
    local_task = _local_mirror(compute, task_dir)
    spec, problems = read_env(local_task)
    if spec is None:
        raise EnvBuildError("env/ 不合约，建不了环境：\n" + "\n".join(problems))
    if spec.interpreter is not None:
        return _existing_interpreter(compute, spec)
    if compute.kind == "local" and importlib.util.find_spec("uv") is None:
        raise EnvBuildError(
            "uv 不在平台 venv 里，建不了任务环境：跑 `make venv` 重装（pyproject 已声明 uv），"
            "不会退回到平台 venv 跑任务"
        )
    uv = list(compute.uv)
    python = f"{venv_dir}/bin/python"
    lock = f"{task_dir}/{ENV_DIRNAME}/{REQUIREMENTS_NAME}"
    _run_on(compute, task_dir,
            [*uv, "venv", "--quiet", "--clear", "--python", spec.python_version, venv_dir],
            what=f"uv venv --python {spec.python_version}", timeout_s=900)
    if spec.requirements:
        _run_on(compute, task_dir, [*uv, "pip", "sync", "--quiet", "--python", python, lock],
                what=f"uv pip sync {lock}", timeout_s=3600)
        check = compute.run(task_dir, [*uv, "pip", "check", "--python", python], {}, 300)
        if not check.ok:
            detail = (check.stdout + check.stderr).strip()[-_STDERR_TAIL:]
            raise EnvBuildError(
                f"{lock} 不完整：装完缺依赖（uv pip check）：\n{detail}\n"
                "清单要是 pip freeze 那样把传递依赖都钉上的；没有现成环境就用 "
                "ai4sci env resolve <包名>… 重新算一份"
            )
    else:
        LOGGER.info("env_build venv=%s requirements=0 skip_sync", venv_dir)
    version_probe = "import sys; print(f'{sys.version_info[0]}.{sys.version_info[1]}')"
    probe = _run_on(compute, task_dir, [python, "-c", version_probe], what="核对解释器版本",
                    timeout_s=60)
    actual = probe.stdout.strip().splitlines()[-1] if probe.stdout.strip() else ""
    if actual != spec.python_version:
        raise EnvBuildError(
            f"venv 的解释器版本对不上：期望 {spec.python_version}，实际 {actual!r}（{python}）"
        )
    LOGGER.info("env_build compute=%s venv=%s python=%s requirements=%d",
                compute.kind, venv_dir, spec.python_version, len(spec.requirements))
    return python


def _existing_interpreter(compute: Compute, spec: EnvSpec) -> str:
    """研究者选了机器上现成的环境：只在那一台上认；解释器要在、版本要对上，不建 venv。"""
    wanted, python = spec.interpreter
    actual = compute_name(compute)
    if actual != wanted:
        raise EnvBuildError(
            f"这份环境是算力 {wanted!r} 上现成的解释器（{python}），现在要在 {actual!r} 上跑："
            "换了机器要重选——ai4sci env use --compute <名字> <解释器>，"
            "或 ai4sci env resolve 隔离新建")
    version_probe = "import sys; print(f'{sys.version_info[0]}.{sys.version_info[1]}')"
    outcome = compute.run(compute.scratch, [python, "-c", version_probe], {}, 60)
    if not outcome.ok:
        raise EnvBuildError(f"算力 {wanted!r} 上的解释器 {python} 起不来："
                            f"{outcome.stderr.strip()[-500:]}")
    actual_version = outcome.stdout.strip().splitlines()[-1] if outcome.stdout.strip() else ""
    if actual_version != spec.python_version:
        raise EnvBuildError(
            f"{python} 的版本对不上：env/ 记的是 {spec.python_version}，实际 {actual_version!r}")
    LOGGER.info("env_existing compute=%s python=%s", wanted, python)
    return python


def compute_name(compute: Compute) -> str:
    """适配器在清单里的名字（`computes.instance` 起的时候贴上）；没贴就按种类（local）。"""
    return str(getattr(compute, "name", compute.kind))


def _local_mirror(compute: Compute, remote_dir: str) -> Path:
    """`env/` 规格在本机这份读：本机就是同一个目录；ssh 按映射反推回本机路径。"""
    if compute.kind == "local":
        return Path(remote_dir)
    local_dir_for = getattr(compute, "local_dir_for", None)
    assert local_dir_for is not None, f"{compute.kind} 适配器要能把远端路径映射回本机"
    return local_dir_for(remote_dir)


def _run_on(compute: Compute, cwd: str, cmd: list[str], *, what: str,
            timeout_s: float) -> Outcome:
    outcome = compute.run(cwd, cmd, {}, timeout_s)
    if not outcome.ok:
        raise EnvBuildError(
            f"{what} 失败（退出码 {outcome.exit_code}）：{outcome.stderr.strip()[-_STDERR_TAIL:]}"
        )
    return outcome


def resolve_lock(target_env: Path, python_version: str, packages: list[str],
                 compute: Compute | None = None) -> Path:
    """按几个包名算出完整的清单写进 `<target_env>/requirements.lock`（`uv pip compile`，会联网）；
    `python-version` 一并写。返回锁文件路径。解析失败带 uv 的 stderr 抛 EnvBuildError。

    按解析那台机器的平台解析（不 `--universal`）：缺省本机；给了 `compute` 就到那台机器上算
    （CUDA 版 torch 只在 GPU 机器上解析得对），清单头部写明是哪台。
    """
    assert VERSION_RE.match(python_version), f"python-version 要是 X.Y：{python_version!r}"
    assert packages and all(p.strip() for p in packages), "至少给一个包名"
    if compute is None:
        from compute.local import LocalCompute  # 便捷路径：本机

        compute = LocalCompute()
    if compute.kind == "local" and importlib.util.find_spec("uv") is None:
        raise EnvBuildError("uv 不在平台 venv 里，算不了清单：跑 make venv 重装"
                            "（pyproject 已声明 uv）")
    target_env = Path(target_env)
    target_env.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        wanted = Path(tmp) / "requirements.in"
        wanted.write_text("\n".join(p.strip() for p in packages) + "\n", encoding="utf-8")
        remote_tmp = compute.remote_dir_for(Path(tmp))
        compute.sync(Path(tmp), remote_tmp)
        proc = _run_on(compute, remote_tmp,
                       [*compute.uv, "pip", "compile", "--quiet", "--no-header", "--no-annotate",
                        "--python-version", python_version, "requirements.in"],
                       what=f"uv pip compile（{', '.join(packages)}）", timeout_s=900)
    pins = [line.strip() for line in proc.stdout.splitlines() if line.strip()]
    bad = [line for line in pins if not _PIN_RE.match(line)]
    assert not bad, f"uv pip compile 出了不是 name==version 的行：{bad}"
    stamp = datetime.now(UTC).strftime("%Y-%m-%d")
    where = "本机" if compute.kind == "local" else f"算力 {compute.kind}"
    header = (f"# 由 ai4sci env resolve 于 {stamp} 按 PyPI 算出的完整清单（uv pip compile，"
              f"Python {python_version}，在{where}上按它的平台解析）。\n"
              f"# 要的包：{' '.join(packages)}；其余是它们的传递依赖。换机器要在那台机器上重算。\n")
    (target_env / PYTHON_VERSION_NAME).write_text(python_version + "\n", encoding="utf-8")
    lock = target_env / REQUIREMENTS_NAME
    lock.write_text(header + "\n".join(pins) + "\n", encoding="utf-8")
    (target_env / INTERPRETER_NAME).unlink(missing_ok=True)  # 算了清单 = 回到隔离新建
    LOGGER.info("env_resolve target=%s python=%s packages=%d pins=%d",
                target_env, python_version, len(packages), len(pins))
    return lock


def use_interpreter(target_env: Path, compute: Compute, python: str) -> Path:
    """研究者选了机器上现成的环境：探它的版本、`pip freeze` 当清单（出处留档）、写 `interpreter`。
    返回 env 目录。解释器起不来、没有 pip 都抛 EnvBuildError。"""
    name = compute_name(compute)
    version_probe = "import sys; print(f'{sys.version_info[0]}.{sys.version_info[1]}')"
    probe = compute.run(compute.scratch, [python, "-c", version_probe], {}, 60)
    if not probe.ok:
        raise EnvBuildError(f"算力 {name!r} 上的解释器 {python} 起不来："
                            f"{probe.stderr.strip()[-500:]}")
    version = probe.stdout.strip().splitlines()[-1]
    assert VERSION_RE.match(version), f"解释器报的版本不是 X.Y：{version!r}"
    frozen = compute.run(compute.scratch, [python, "-m", "pip", "freeze"], {}, 300)
    if not frozen.ok:
        raise EnvBuildError(f"{python} 里没有 pip，列不出它装了什么："
                            f"{frozen.stderr.strip()[-500:]}")
    pins, odd = [], []
    for line in frozen.stdout.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        (pins if _PIN_RE.match(line) else odd).append(line)
    target_env = Path(target_env)
    target_env.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y-%m-%d")
    header = (f"# 算力 {name} 上现成的环境 {python} 于 {stamp} 的 pip freeze"
              "（研究者选的「用现成的」，不隔离、不由平台建；出处留档用）。\n"
              "# 换机器时这份清单不能照装，要重选环境或 ai4sci env resolve 隔离新建。\n")
    if odd:
        header += "# 下面这些行不是 name==version（本地路径、可编辑安装），照录不装：\n"
        header += "".join(f"#   {line}\n" for line in odd)
    (target_env / PYTHON_VERSION_NAME).write_text(version + "\n", encoding="utf-8")
    (target_env / REQUIREMENTS_NAME).write_text(header + "\n".join(pins) + "\n", encoding="utf-8")
    (target_env / INTERPRETER_NAME).write_text(f"{name}:{python}\n", encoding="utf-8")
    LOGGER.info("env_use compute=%s python=%s version=%s pins=%d", name, python, version, len(pins))
    return target_env


def _run(argv: list[str], *, what: str) -> subprocess.CompletedProcess[str]:
    try:
        proc = subprocess.run(argv, capture_output=True, text=True, check=False)
    except OSError as exc:
        raise EnvBuildError(f"{what} 起不来：{exc}") from exc
    if proc.returncode != 0:
        raise EnvBuildError(
            f"{what} 失败（退出码 {proc.returncode}）：{proc.stderr.strip()[-_STDERR_TAIL:]}"
        )
    return proc
