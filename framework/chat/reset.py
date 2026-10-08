"""清除平台的家（外层 #263，主人 2026-10-06：用户带着干净的环境进来，想清除时一把删干净）。

`ai4sci reset` 与设置页「清除全部数据」都走 `reset()`：先让两家 CLI 在平台的私有目录里登出——
Claude Code 的登录记在系统钥匙串里（按配置目录分开），只删目录会留下那一条——再删掉家里的一切，
只留标记、一行命令装的程序（`bin/` `tools/`，外层 #277）与在跑的服务的登记（`run/`，外层 #285）：
回到刚装好的样子（`AI4SCI_HOME` 指的目录也还在，下次起得来）。卸载是删整个家，不归这里。

三道闸，任何一道不过都不删（ResetRefused，一句给人看的话）：
- 家里要有平台放的标记（`paths.MARKER_NAME`）：`AI4SCI_HOME` 指错了（指到 `~`、指到别人的目录）
  也删不到；
- 不是用户的主目录、不是文件系统的根；
- 没有作业在跑：删了它的工作区，跑完的结果无处可落。
"""

from __future__ import annotations

import logging
import shutil
import subprocess
from collections.abc import Callable
from pathlib import Path

from backends import available_backends
from framework import agents, files, paths
from framework.workspace import jobs, project

LOGGER = logging.getLogger("ai4sci.reset")
LOGOUT_TIMEOUT_S = 60
# 清除不碰的：家的标记、一行命令装的程序（外层 #277）、在跑的服务的登记（外层 #285：清除时服务
# 就开着，删了它，服务崩了以后没人收拾它起的轮次）
KEPT = frozenset({paths.MARKER_NAME, paths.BIN_DIRNAME, paths.TOOLS_DIRNAME, paths.RUN_DIRNAME})

# 谁来给登出命令：缺省是真适配器（测试里换成不碰 CLI 的）
Logout = Callable[[str], tuple[list[str], dict[str, str]]]


class ResetRefused(RuntimeError):
    """这次不删：原因一句话给人看。"""


def running(home: Path) -> list[str]:
    """家里在跑的作业：`<项目>/<工作区>/<作业>`。"""
    found: list[str] = []
    for proj in project.list_projects(project.projects_root(home)):
        for ws in proj.workspaces():
            found += [f"{proj.id}/{ws.root.name}/{job.job_id}"
                      for job in jobs.running_jobs(ws.jobs)]
    return found


def check(home: Path) -> None:
    """三道闸：不过就抛 ResetRefused。"""
    home = Path(home).resolve()
    if home in (Path.home().resolve(), Path(home.anchor)):
        raise ResetRefused(f"{home} 是主目录或根目录，不删")
    if not (home / paths.MARKER_NAME).is_file():
        raise ResetRefused(f"{home} 里没有平台的标记（{paths.MARKER_NAME}），不是平台建的家，不删")
    busy = running(home)
    if busy:
        raise ResetRefused(f"有 {len(busy)} 个作业在跑（{'、'.join(busy[:3])}），先叫停再清除")


def reset(home: Path, logout: Logout = agents.logout_command) -> list[str]:
    """登出两家、清空家里除 `KEPT` 以外的一切；返回做了什么（一行一件，给人看）。"""
    home = Path(home).resolve()
    check(home)
    done: list[str] = []
    for name in available_backends():
        argv, env = logout(name)
        if shutil.which(argv[0]) is None:
            done.append(f"{name}：没装，不用登出")
            continue
        proc = subprocess.run(argv, env=env, capture_output=True, text=True,
                              encoding="utf-8", errors="replace",
                              timeout=LOGOUT_TIMEOUT_S, stdin=subprocess.DEVNULL, check=False)
        said = (proc.stdout or proc.stderr).strip().splitlines()
        note = said[-1] if said else ""
        # 没登录过的那家登出会报错：照实记一行，不拦清除
        done.append(f"{name}：{'已登出' if proc.returncode == 0 else '没有可登出的'}"
                    f"{('（' + note + '）') if note else ''}")
        LOGGER.info("reset_logout backend=%s exit=%s", name, proc.returncode)
    for child in home.iterdir():
        if child.name in KEPT:
            continue
        if child.is_dir() and not child.is_symlink():
            files.remove_tree(child)
        else:
            child.unlink()
    done.append(f"已清空 {home}")
    LOGGER.info("reset_done home=%s", home)
    return done
