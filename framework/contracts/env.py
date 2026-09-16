"""任务包的环境契约：`env/` 怎么读、怎么判、怎么建成任务级 venv（纲领 packs.md §2）。

任务自带环境，平台 venv 一个包不多装（红线：环境必隔离）。两个文件：

    env/python-version      一行，如 3.14
    env/requirements.lock   逐行 name==version，钉死；可以为空

建 venv 的动作也放在 contracts 层而不是 run 层：同一份 lock 要建在两处
（`tasks/<id>/.venv` 给 make_run0.sh，`runs/<id>/.venv` 给每个 run），两处必须走同一个函数，
否则"任务里能跑、run 里跑不动"这种事迟早发生。本模块只认文件与 uv，不知道 run 与任务包的
其它部分。

为什么用 uv：一条工具把找解释器、拉解释器、建 venv、按 lock 同步四件事做完，且是 pip 可装的
轮子，能钉进平台自己的 requirements.lock。uv 不在或解释器拉不下来就抛 `EnvBuildError`，
绝不静默退回到平台 venv（P-7）。
"""

from __future__ import annotations

import importlib.util
import logging
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

LOGGER = logging.getLogger("ai4sci.env")

ENV_DIRNAME = "env"
PYTHON_VERSION_NAME = "python-version"
REQUIREMENTS_NAME = "requirements.lock"
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

_VERSION_RE = re.compile(r"^(\d+)\.(\d+)$")
# 钉死的一行：名字（可带 extras）== 版本；别的写法（>=、URL、-e）一律不收
_PIN_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*(\[[A-Za-z0-9._,\s-]+\])?==[A-Za-z0-9.!+*-]+$")
_STDERR_TAIL = 1500


class EnvBuildError(RuntimeError):
    """venv 建不出来：uv 不在、解释器拉不下来、依赖装不上。调用方按"这个任务现在跑不了"处理。"""


@dataclass(frozen=True)
class EnvSpec:
    python_version: str
    requirements: tuple[str, ...]


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

    与 packs.validate_task 同一套约定：问题一行一条、带文件与期望 vs 实际，不抛。
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
        if not _VERSION_RE.match(version):
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

    if problems:
        return None, problems
    return EnvSpec(python_version=version, requirements=tuple(requirements)), []


def build_venv(task_dir: Path, venv_dir: Path) -> Path:
    """按 `<task_dir>/env/` 建（或重建）venv 到 venv_dir，返回它的解释器路径。

    task_dir 是"任务形状"的目录：`tasks/<id>/` 或 run 里的 `work/`，两处都有 env/。
    三步：`uv venv --python X.Y`（找不到就拉一个到 uv 的用户级目录）→ 有依赖就 `uv pip sync`
    （精确对齐 lock，多的卸、少的装）→ 起一次解释器核对版本。每一步失败都带 stderr 抛
    `EnvBuildError`，半截的 venv 留在原地给人看，不做"看起来建好了"。
    """
    spec, problems = read_env(task_dir)
    if spec is None:
        raise EnvBuildError("env/ 不合约，建不了环境：\n" + "\n".join(problems))
    if importlib.util.find_spec("uv") is None:
        raise EnvBuildError(
            "uv 不在平台 venv 里，建不了任务环境：跑 `make venv` 重装（pyproject 已声明 uv），"
            "不会退回到平台 venv 跑任务"
        )
    venv_dir = Path(venv_dir)
    uv = [sys.executable, "-m", "uv"]
    _run(uv + ["venv", "--quiet", "--clear", "--python", spec.python_version, str(venv_dir)],
         what=f"uv venv --python {spec.python_version}")
    python = venv_python(venv_dir)
    if spec.requirements:
        lock = env_dir(task_dir) / REQUIREMENTS_NAME
        _run(uv + ["pip", "sync", "--quiet", "--python", str(python), str(lock)],
             what=f"uv pip sync {lock}")
    else:
        LOGGER.info("env_build venv=%s requirements=0 skip_sync", venv_dir)

    probe = _run([str(python), "-c",
                  "import sys; print(f'{sys.version_info[0]}.{sys.version_info[1]}')"],
                 what="核对解释器版本")
    actual = probe.stdout.strip()
    if actual != spec.python_version:
        raise EnvBuildError(
            f"venv 的解释器版本对不上：期望 {spec.python_version}，实际 {actual}（{python}）"
        )
    LOGGER.info("env_build venv=%s python=%s requirements=%d",
                venv_dir, spec.python_version, len(spec.requirements))
    return python


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
