"""对 `runs/<run_id>/work/` 那个独立 git 仓的全部操作。

为什么 git 是状态载体（纲领 workflow.md §2）：分支 tip 永远是当前最好的版本，
被弃的尝试 reset 掉但先存进 `refs/attempts/`——这样"回到 best"是一条命令，
而账本每一行都还能在仓里找到对应的 commit（P-3 的对账测试）。

执行层不碰 git，提交由 runner 做，作者写死成 runner 自己：账本上的作者不该是
每轮换一个 CLI 的名字，那会让"谁改的"这个问题失去意义。

在四层的 run 层：work/ 是 run 目录的一部分，它的 git 状态就是这个 run 的状态。
本模块只跑 git 子进程，不 import framework 的任何东西。
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

AUTHOR_NAME = "ai4sci runner"
AUTHOR_EMAIL = "runner@ai4sci.local"
ATTEMPT_REF_PREFIX = "refs/attempts"

# 提交身份走环境变量而不是 `git config`：work/ 是每轮都可能被 reset 的仓，
# 身份跟着进程走才不会因为仓里的配置被改掉而变。
_IDENTITY = {
    "GIT_AUTHOR_NAME": AUTHOR_NAME, "GIT_AUTHOR_EMAIL": AUTHOR_EMAIL,
    "GIT_COMMITTER_NAME": AUTHOR_NAME, "GIT_COMMITTER_EMAIL": AUTHOR_EMAIL,
}


def git(work: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    """跑一条 git。失败默认抛（不吞异常）；只有明确要看退出码的调用才传 check=False。"""
    proc = subprocess.run(
        ["git", "-C", str(work), *args], capture_output=True, text=True, env=_env(), check=False
    )
    if check and proc.returncode != 0:
        raise RuntimeError(
            f"git {' '.join(args)} 在 {work} 失败（退出码 {proc.returncode}）："
            f"{proc.stderr.strip()}"
        )
    return proc


def _env() -> dict[str, str]:
    return {**os.environ, **_IDENTITY}


def init_repo(work: Path, message: str) -> str:
    """初始化 work/ 并把任务包基线提交成第一个 commit，返回它的 sha。"""
    git(work, "init", "-q", "-b", "main")
    git(work, "add", "-A")
    git(work, "commit", "-q", "-m", message)
    return head(work)


def head(work: Path) -> str:
    return git(work, "rev-parse", "HEAD").stdout.strip()


def is_clean(work: Path) -> bool:
    return git(work, "status", "--porcelain").stdout.strip() == ""


def commit_paths(work: Path, paths: list[str], message: str) -> str | None:
    """把指定路径下的改动提交掉；没有可提交的东西返回 None（不造空 commit）。"""
    git(work, "add", "-A", "--", *paths)
    if git(work, "diff", "--cached", "--quiet", check=False).returncode == 0:
        return None
    git(work, "commit", "-q", "-m", message)
    return head(work)


def revert_to(work: Path, sha: str) -> None:
    """revert-to-best：工作区丢弃、未跟踪清掉、HEAD 拉回 sha。下一轮的起点永远是 best。

    `clean` 带 `-x` 连被忽略的文件一起清：work/ 是一次性仓，任务包 `.gitignore` 挡住的
    产物（预测文件、缓存、执行层日志）留到下一轮只会污染下一轮的起点，而这里本来就
    没有"人手里正在改的东西"要保护。
    """
    git(work, "checkout", "-q", "--", ".")
    git(work, "clean", "-qfdx")
    git(work, "reset", "-q", "--hard", sha)


def diff_stat(work: Path, base: str, sha: str) -> str:
    """两个 commit 之间的 --stat，给实验笔记用；没有差异返回空串。"""
    return git(work, "diff", "--stat", base, sha).stdout.strip()


def diff_full(work: Path, base: str, sha: str, max_chars: int) -> str:
    """两个 commit 之间的完整 diff，给分析能力读；超过 max_chars 截断并注明，别整段塞进 prompt。"""
    text = git(work, "diff", base, sha).stdout
    if len(text) <= max_chars:
        return text.strip()
    note = f"\n\n…（diff 共 {len(text)} 字符，只保留前 {max_chars} 字符）"
    return text[:max_chars].rstrip() + note


def keep_attempt(work: Path, iter_n: int, sha: str) -> str:
    """把被弃的候选存进 refs/attempts/iter-N，reset 之前调用；返回 ref 名。"""
    ref = f"{ATTEMPT_REF_PREFIX}/iter-{iter_n}"
    git(work, "update-ref", ref, sha)
    return ref


def root_commit(work: Path) -> str | None:
    """当前分支的第一个 commit（任务包基线）。账本对账拿它当第一条 keep 行的 parent。"""
    shas = git(work, "rev-list", "--max-parents=0", "HEAD", check=False).stdout.split()
    return shas[-1] if shas else None


def rev_parse(work: Path, rev: str) -> str | None:
    """解析一个 revision；解析不出来返回 None（调用方要报"账本里的 commit 找不到"）。"""
    proc = git(work, "rev-parse", "--verify", "-q", f"{rev}^{{commit}}", check=False)
    return proc.stdout.strip() or None


def is_ancestor(work: Path, sha: str, rev: str = "HEAD") -> bool:
    """sha 在 rev 这条线上吗（含相等）。keep 的 commit 必须在分支上。"""
    return git(work, "merge-base", "--is-ancestor", sha, rev, check=False).returncode == 0


def attempt_refs(work: Path) -> dict[str, str]:
    """refs/attempts/ 下的全部 ref → sha。"""
    out = git(work, "for-each-ref", "--format=%(refname) %(objectname)", ATTEMPT_REF_PREFIX).stdout
    return dict(line.split() for line in out.splitlines() if line.strip())
