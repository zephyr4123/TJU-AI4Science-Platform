"""Windows 上的进程树：Job Object（外层 #210）。只在 Windows 上 import，用到的都是 kernel32 的公开
接口，外加 ntdll 的 `NtResumeProcess`（Popen 拿到线程句柄就关了，挂起起的进程只能整个放行）。

一棵树一个 Job，按根的 pid 起名（`ai4sci-tree-<pid>`），页面服务、续跑的那一次按名字再打开它。
名字只在还有人握着句柄时查得到（最后一个句柄一关，名字就从命名空间里摘掉，Job 里的进程还在也
一样，2026-10-07 真机实测），所以把句柄复制一份给根自己握着：根活着就找得到这棵树。作业「还在跑」
的判据本来就是根活着（`workspace/jobs.py`），根没了作业就是 lost、不再叫停，两边对得上。不设
「关句柄就全杀」：起它的进程退了树照跑，与 POSIX 上自成会话一致。根先挂起、放进 Job、递句柄、
再放行：放行之前它派生不了任何东西，没有漏网的窗口。
"""

from __future__ import annotations

import ctypes
import logging
import shutil
import subprocess
from ctypes import wintypes
from pathlib import Path
from typing import Any

LOGGER = logging.getLogger("ai4sci.procs")

CREATE_SUSPENDED = 0x00000004
CREATE_NEW_PROCESS_GROUP = 0x00000200
CREATE_BREAKAWAY_FROM_JOB = 0x01000000
CREATE_NO_WINDOW = 0x08000000
JOB_OBJECT_QUERY = 0x0004
JOB_OBJECT_TERMINATE = 0x0008
JOB_OBJECT_ALL_ACCESS = 0x1F001F
PROCESS_TERMINATE = 0x0001
PROCESS_DUP_HANDLE = 0x0040
PROCESS_SET_QUOTA = 0x0100
PROCESS_SUSPEND_RESUME = 0x0800
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
STILL_ACTIVE = 259
ERROR_ACCESS_DENIED = 5
ERROR_ALREADY_EXISTS = 183
DUPLICATE_SAME_ACCESS = 0x2
JOB_BASIC_ACCOUNTING = 1  # JobObjectBasicAccountingInformation
KILLED_EXIT_CODE = 1


class _Accounting(ctypes.Structure):
    _fields_ = [("TotalUserTime", ctypes.c_int64), ("TotalKernelTime", ctypes.c_int64),
                ("ThisPeriodTotalUserTime", ctypes.c_int64),
                ("ThisPeriodTotalKernelTime", ctypes.c_int64),
                ("TotalPageFaultCount", wintypes.DWORD), ("TotalProcesses", wintypes.DWORD),
                ("ActiveProcesses", wintypes.DWORD), ("TotalTerminatedProcesses", wintypes.DWORD)]


_k32 = ctypes.WinDLL("kernel32", use_last_error=True)
_ntdll = ctypes.WinDLL("ntdll")
_k32.CreateJobObjectW.argtypes = (wintypes.LPVOID, wintypes.LPCWSTR)
_k32.CreateJobObjectW.restype = wintypes.HANDLE
_k32.OpenJobObjectW.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.LPCWSTR)
_k32.OpenJobObjectW.restype = wintypes.HANDLE
_k32.AssignProcessToJobObject.argtypes = (wintypes.HANDLE, wintypes.HANDLE)
_k32.AssignProcessToJobObject.restype = wintypes.BOOL
_k32.TerminateJobObject.argtypes = (wintypes.HANDLE, wintypes.UINT)
_k32.TerminateJobObject.restype = wintypes.BOOL
_k32.QueryInformationJobObject.argtypes = (wintypes.HANDLE, ctypes.c_int, wintypes.LPVOID,
                                           wintypes.DWORD, wintypes.LPDWORD)
_k32.QueryInformationJobObject.restype = wintypes.BOOL
_k32.IsProcessInJob.argtypes = (wintypes.HANDLE, wintypes.HANDLE, ctypes.POINTER(wintypes.BOOL))
_k32.IsProcessInJob.restype = wintypes.BOOL
_k32.GetCurrentProcess.restype = wintypes.HANDLE
_k32.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
_k32.OpenProcess.restype = wintypes.HANDLE
_k32.GetExitCodeProcess.argtypes = (wintypes.HANDLE, wintypes.LPDWORD)
_k32.GetExitCodeProcess.restype = wintypes.BOOL
_k32.DuplicateHandle.argtypes = (wintypes.HANDLE, wintypes.HANDLE, wintypes.HANDLE,
                                 ctypes.POINTER(wintypes.HANDLE), wintypes.DWORD, wintypes.BOOL,
                                 wintypes.DWORD)
_k32.DuplicateHandle.restype = wintypes.BOOL
_k32.CloseHandle.argtypes = (wintypes.HANDLE,)
_k32.CloseHandle.restype = wintypes.BOOL
_ntdll.NtResumeProcess.argtypes = (wintypes.HANDLE,)
_ntdll.NtResumeProcess.restype = ctypes.c_long


def _name(pgid: int) -> str:
    return f"ai4sci-tree-{pgid}"


def _fail(what: str) -> OSError:
    code = ctypes.get_last_error()
    return OSError(code, f"{what} 失败：{ctypes.FormatError(code).strip()}（WinError {code}）")


def spawn(argv: list[str], *, detach: bool, **popen: Any) -> subprocess.Popen:
    flags = popen.pop("creationflags", 0) | CREATE_SUSPENDED | CREATE_NEW_PROCESS_GROUP \
        | CREATE_NO_WINDOW
    if detach:
        try:
            proc = subprocess.Popen(argv, creationflags=flags | CREATE_BREAKAWAY_FROM_JOB, **popen)
        except PermissionError:  # 起它的那个 Job 不许脱离：只能留在里面
            LOGGER.info("spawn_breakaway_denied argv0=%s", argv[0])
            proc = subprocess.Popen(argv, creationflags=flags, **popen)
    else:
        proc = subprocess.Popen(argv, creationflags=flags, **popen)
    try:
        _adopt(proc.pid)
    except OSError:
        proc.kill()  # 还挂着、什么都没跑：放不进 Job 就不让它跑成一棵管不住的树
        proc.wait()
        raise
    return proc


def _adopt(pid: int) -> None:
    """挂起的根放进以它命名的 Job、递给它一个 Job 的句柄，再放行。"""
    ctypes.set_last_error(0)  # 建成功时它不清零：不先清，「已经有了」读到的可能是上一次的错
    job = _k32.CreateJobObjectW(None, _name(pid))
    if not job:
        raise _fail(f"建 Job {_name(pid)}")
    if ctypes.get_last_error() == ERROR_ALREADY_EXISTS:  # 同一个 pid 以前那棵还有进程活着
        LOGGER.warning("job_name_reused name=%s", _name(pid))
    process = _k32.OpenProcess(PROCESS_SET_QUOTA | PROCESS_TERMINATE | PROCESS_SUSPEND_RESUME
                               | PROCESS_DUP_HANDLE, False, pid)
    try:
        if not process:
            raise _fail(f"打开进程 {pid}")
        if not _k32.AssignProcessToJobObject(job, process):
            raise _fail(f"把进程 {pid} 放进 Job")
        held = wintypes.HANDLE()
        if not _k32.DuplicateHandle(_k32.GetCurrentProcess(), job, process, ctypes.byref(held),
                                    0, False, DUPLICATE_SAME_ACCESS):
            raise _fail(f"把 Job 的句柄递给进程 {pid}")
        status = _ntdll.NtResumeProcess(process)
        if status != 0:
            raise OSError(status, f"放行进程 {pid} 失败（NTSTATUS {status:#x}）")
    finally:
        if process:
            _k32.CloseHandle(process)
        _k32.CloseHandle(job)


def kill_tree(pgid: int) -> list[int]:
    """把那个 Job 整个结束；没有 Job（不是 `spawn` 起的，或早已全退）而根还活着，用 taskkill /T 兜底
    （只在父子关系还连着时管用）。"""
    job = _k32.OpenJobObjectW(JOB_OBJECT_TERMINATE | JOB_OBJECT_QUERY, False, _name(pgid))
    if job:
        try:
            inside = wintypes.BOOL()
            if not _k32.IsProcessInJob(_k32.GetCurrentProcess(), job, ctypes.byref(inside)):
                raise _fail(f"查本进程在不在 {_name(pgid)} 里")
            if inside.value:  # 护栏：绝不把框架自己那棵带走
                LOGGER.warning("kill_tree_refused_own_tree name=%s", _name(pgid))
                return []
            if not _k32.TerminateJobObject(job, KILLED_EXIT_CODE):
                raise _fail(f"结束 {_name(pgid)}")
        finally:
            _k32.CloseHandle(job)
        return [pgid]
    if not pid_alive(pgid):
        return []
    done = subprocess.run(["taskkill", "/T", "/F", "/PID", str(pgid)], capture_output=True,
                          stdin=subprocess.DEVNULL, check=False)
    if done.returncode != 0 and pid_alive(pgid):  # taskkill 的话是系统编码，只记退出码
        raise RuntimeError(f"taskkill /T 没杀掉 {pgid}（退出码 {done.returncode}）")
    LOGGER.info("kill_tree_fallback_taskkill pid=%d", pgid)
    return [pgid]


def tree_alive(pgid: int) -> bool:
    """Job 里还有没有活着的进程；Job 已经不在（全退了）就是没有。"""
    job = _k32.OpenJobObjectW(JOB_OBJECT_QUERY, False, _name(pgid))
    if not job:
        return pid_alive(pgid)  # 不是 `spawn` 起的：只能看根
    try:
        info = _Accounting()
        if not _k32.QueryInformationJobObject(job, JOB_BASIC_ACCOUNTING, ctypes.byref(info),
                                              ctypes.sizeof(info), None):
            raise _fail(f"查 {_name(pgid)}")
        return info.ActiveProcesses > 0
    finally:
        _k32.CloseHandle(job)


def git_bash() -> str:
    """Git for Windows 的 bash：git.exe 在 `<Git>/cmd/`（装的版本放进 PATH 的那个）、`<Git>/bin/`
    或 `<Git>/mingw64/bin/`，bash 在 `<Git>/bin/bash.exe`；MinGit 不带 bash。"""
    git = shutil.which("git")
    if git is None:
        raise FileNotFoundError("没有 Git for Windows：终端里跑 ai4sci setup 装上")
    for root in Path(git).resolve().parents[:3]:
        candidate = root / "bin" / "bash.exe"
        if candidate.is_file():
            return str(candidate)
    raise FileNotFoundError(f"{git} 这份 git 没带 bash（MinGit？）：装完整的 Git for Windows，"
                            "或终端里跑 ai4sci setup")


def pid_alive(pid: int) -> bool:
    process = _k32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not process:
        # 拒绝访问说明它在（别人的进程）；别的错（参数错：没有这个 pid）就是不在
        return ctypes.get_last_error() == ERROR_ACCESS_DENIED
    try:
        code = wintypes.DWORD()
        if not _k32.GetExitCodeProcess(process, ctypes.byref(code)):
            raise _fail(f"查进程 {pid} 的退出码")
        return code.value == STILL_ACTIVE
    finally:
        _k32.CloseHandle(process)
