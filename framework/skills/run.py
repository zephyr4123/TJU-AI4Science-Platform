"""起一个 skill 的脚本：`uv run --locked --offline --script <脚本> <参数…>`（纲领 P-22）。

只做一件事：找到脚本、按锁起环境、把参数原样递过去；不解析脚本的输出，不替脚本猜路径。
stdout / stderr 直通调用方（agent 读 stdout 的那行 JSON），退出码原样返回。

`--locked`：锁文件与头部的依赖对不上就报错，不静默重解析；`--offline`：环境由 `make skills` 预热过，
运行时不联网，沙箱断网照跑。冷机器上会失败，uv 的报错会说没缓存——那是承接没做完，不是运行时该兜的。
uv 是平台 venv 里的（`python -m uv`，与 experiment/env.py 同一份），不找系统 PATH 上的。
"""

from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
from pathlib import Path

from framework.skills.library import Skill, SkillInvalid, lock_path

UV_RUN_ARGS = ("run", "--locked", "--offline", "--script")
UV_LOCK_CHECK_ARGS = ("lock", "--check", "--script")
UV_SYNC_ARGS = ("sync", "--locked", "--script")


class UvMissing(RuntimeError):
    """平台 venv 里没有 uv：`make venv` 重装。绝不退回到平台 venv 直接跑脚本。"""


def uv_argv() -> list[str]:
    if importlib.util.find_spec("uv") is None:
        raise UvMissing("uv 不在平台 venv 里，起不了 skill 脚本：跑 make venv 重装"
                        "（pyproject 已声明 uv）")
    return [sys.executable, "-m", "uv"]


def uv_env() -> dict[str, str]:
    """起 uv 的环境：去掉 VIRTUAL_ENV——脚本环境在 uv 的缓存里，不是平台 venv，留着它 uv 每次都打一行
    warning 到 stderr，agent 会当成出了错。"""
    env = dict(os.environ)
    env.pop("VIRTUAL_ENV", None)
    return env


def pick_script(skill: Skill, name: str | None) -> Path:
    """`run <skill>` 起哪个脚本：只有一个就是它；几个就得 `--script <文件名>` 点名。"""
    if not skill.scripts:
        raise SkillInvalid(f"skill {skill.name!r} 没有脚本（scripts/ 下没有 .py），只能读不能跑")
    if name is None:
        if len(skill.scripts) == 1:
            return skill.scripts[0]
        names = ", ".join(p.name for p in skill.scripts)
        raise SkillInvalid(f"skill {skill.name!r} 有几个脚本（{names}），用 --script <文件名> 点名")
    for script in skill.scripts:
        if script.name == name or script.stem == name:
            return script
    names = ", ".join(p.name for p in skill.scripts)
    raise SkillInvalid(f"skill {skill.name!r} 没有叫 {name!r} 的脚本；有：{names}")


def run_script(script: Path, args: list[str], cwd: Path | None = None) -> int:
    """起脚本，参数原样递过去，返回它的退出码。stdout / stderr 不截、不改。"""
    assert lock_path(script).is_file(), f"{script} 没有锁文件，load_skill 该已经拦下"
    argv = [*uv_argv(), *UV_RUN_ARGS, str(script), *args]
    proc = subprocess.run(argv, cwd=None if cwd is None else str(cwd), env=uv_env(), check=False)
    return proc.returncode


def warm_script(script: Path) -> None:
    """`make skills` 用：核对锁文件（`uv lock --script --check`）再预热环境（`uv sync`）。
    这是唯一允许联网的一步；失败就带 stderr 抛，不留一个「看起来预热过」的环境。"""
    uv = uv_argv()
    for what, argv in (("uv lock --check", [*uv, *UV_LOCK_CHECK_ARGS, str(script)]),
                       ("uv sync", [*uv, *UV_SYNC_ARGS, str(script)])):
        proc = subprocess.run(argv, capture_output=True, text=True, env=uv_env(), check=False)
        if proc.returncode != 0:
            raise SkillInvalid(f"{script}: {what} 失败（退出码 {proc.returncode}）："
                               f"{proc.stderr.strip()[-1500:]}")
