"""Windows 上的进程树：Job Object（外层 #210）。只在 Windows 上 import，用到的都是 kernel32 /
user32 的公开接口，外加 ntdll 的 `NtResumeProcess`（Popen 拿到线程句柄就关了，挂起起的进程只能整个
放行）。

一棵树一个 Job，按根的 pid 起名（`ai4sci-tree-<pid>`），页面服务、续跑的那一次按名字再打开它。
名字只在还有人握着句柄时查得到（最后一个句柄一关，名字就从命名空间里摘掉，Job 里的进程还在也
一样，2026-10-07 真机实测），所以把句柄复制一份给根自己握着：根活着就找得到这棵树。作业「还在跑」
的判据本来就是根活着（`workspace/jobs.py`），根没了作业就是 lost、不再叫停，两边对得上。不设
「关句柄就全杀」：起它的进程退了树照跑，与 POSIX 上自成会话一致。根先挂起、放进 Job、递句柄、
再放行：放行之前它派生不了任何东西，没有漏网的窗口。每棵树的 Job 都不许脱离（breakaway）：Git for
Windows 的 bash 只要所在的 Job 许脱离，就给它起的每个子进程都带上脱离的标志，一轮里的命令、harness
起的 python 都会跳出去成杀不掉的孤儿（外层 #284 审查）。

作业（`spawn_detached`，外层 #284）要活过起它的那一轮、那个服务、外壳的 Job，又不能靠脱离：以当前
会话的 explorer 为父进程起（`PROC_THREAD_ATTRIBUTE_PARENT_PROCESS`），Job 从指定的父进程继承，作业
生来就不在任何 Job 里、也不是任何人的后代，再照常放进它自己那棵树的 Job。句柄同样从 explorer 继承，
所以作业的三个标准流一个都不接，日志由作业自己按路径打开。身份（token）也从 explorer 继承：只有它与
本进程是同一个用户、同一级权限时才借它——以管理员身份跑的服务借普通权限的 explorer，作业就降了权，
写不进服务建的只给管理员的目录（2026-10-07 真机：Python 3.13 起 `mkdir(mode=0o700)` 建的目录就是
这样）。会话里没有 explorer（SSH、服务里起的）或身份对不上，就照旧起、试着脱离，把为什么没能脱离
说出来。
"""

from __future__ import annotations

import ctypes
import logging
import shutil
import subprocess
from ctypes import wintypes
from pathlib import Path

LOGGER = logging.getLogger("ai4sci.procs")

CREATE_SUSPENDED = 0x00000004
CREATE_NEW_PROCESS_GROUP = 0x00000200
CREATE_UNICODE_ENVIRONMENT = 0x00000400
EXTENDED_STARTUPINFO_PRESENT = 0x00080000
CREATE_BREAKAWAY_FROM_JOB = 0x01000000
CREATE_NO_WINDOW = 0x08000000
# 一棵树的根怎么起：挂起（放进 Job 再放行）、单独一个 Ctrl+C 组、一个看不见的控制台
TREE_FLAGS = CREATE_SUSPENDED | CREATE_NEW_PROCESS_GROUP | CREATE_NO_WINDOW
PROC_THREAD_ATTRIBUTE_PARENT_PROCESS = 0x00020000
JOB_OBJECT_QUERY = 0x0004
JOB_OBJECT_TERMINATE = 0x0008
JOB_OBJECT_ALL_ACCESS = 0x1F001F
PROCESS_TERMINATE = 0x0001
PROCESS_CREATE_PROCESS = 0x0080
PROCESS_DUP_HANDLE = 0x0040
PROCESS_SET_QUOTA = 0x0100
PROCESS_SUSPEND_RESUME = 0x0800
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
TOKEN_QUERY = 0x0008
TOKEN_USER = 1  # TOKEN_INFORMATION_CLASS
TOKEN_ELEVATION = 20
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


class _StartupInfo(ctypes.Structure):
    _fields_ = [("cb", wintypes.DWORD), ("lpReserved", wintypes.LPWSTR),
                ("lpDesktop", wintypes.LPWSTR), ("lpTitle", wintypes.LPWSTR),
                ("dwX", wintypes.DWORD), ("dwY", wintypes.DWORD), ("dwXSize", wintypes.DWORD),
                ("dwYSize", wintypes.DWORD), ("dwXCountChars", wintypes.DWORD),
                ("dwYCountChars", wintypes.DWORD), ("dwFillAttribute", wintypes.DWORD),
                ("dwFlags", wintypes.DWORD), ("wShowWindow", wintypes.WORD),
                ("cbReserved2", wintypes.WORD), ("lpReserved2", wintypes.LPVOID),
                ("hStdInput", wintypes.HANDLE), ("hStdOutput", wintypes.HANDLE),
                ("hStdError", wintypes.HANDLE)]


class _StartupInfoEx(ctypes.Structure):
    _fields_ = [("StartupInfo", _StartupInfo), ("lpAttributeList", wintypes.LPVOID)]


class _ProcessInformation(ctypes.Structure):
    _fields_ = [("hProcess", wintypes.HANDLE), ("hThread", wintypes.HANDLE),
                ("dwProcessId", wintypes.DWORD), ("dwThreadId", wintypes.DWORD)]


_k32 = ctypes.WinDLL("kernel32", use_last_error=True)
_u32 = ctypes.WinDLL("user32", use_last_error=True)
_a32 = ctypes.WinDLL("advapi32", use_last_error=True)
_a32.OpenProcessToken.argtypes = (wintypes.HANDLE, wintypes.DWORD, ctypes.POINTER(wintypes.HANDLE))
_a32.OpenProcessToken.restype = wintypes.BOOL
_a32.GetTokenInformation.argtypes = (wintypes.HANDLE, ctypes.c_int, wintypes.LPVOID,
                                     wintypes.DWORD, wintypes.LPDWORD)
_a32.GetTokenInformation.restype = wintypes.BOOL
_a32.GetLengthSid.argtypes = (wintypes.LPVOID,)
_a32.GetLengthSid.restype = wintypes.DWORD
_ntdll = ctypes.WinDLL("ntdll")
_u32.GetShellWindow.restype = wintypes.HWND
_u32.GetWindowThreadProcessId.argtypes = (wintypes.HWND, wintypes.LPDWORD)
_u32.GetWindowThreadProcessId.restype = wintypes.DWORD
_k32.InitializeProcThreadAttributeList.argtypes = (wintypes.LPVOID, wintypes.DWORD,
                                                   wintypes.DWORD, ctypes.POINTER(ctypes.c_size_t))
_k32.InitializeProcThreadAttributeList.restype = wintypes.BOOL
_k32.UpdateProcThreadAttribute.argtypes = (wintypes.LPVOID, wintypes.DWORD, ctypes.c_size_t,
                                           wintypes.LPVOID, ctypes.c_size_t, wintypes.LPVOID,
                                           wintypes.LPVOID)
_k32.UpdateProcThreadAttribute.restype = wintypes.BOOL
_k32.DeleteProcThreadAttributeList.argtypes = (wintypes.LPVOID,)
_k32.DeleteProcThreadAttributeList.restype = None
_k32.CreateProcessW.argtypes = (wintypes.LPCWSTR, wintypes.LPWSTR, wintypes.LPVOID,
                                wintypes.LPVOID, wintypes.BOOL, wintypes.DWORD, wintypes.LPVOID,
                                wintypes.LPCWSTR, ctypes.POINTER(_StartupInfoEx),
                                ctypes.POINTER(_ProcessInformation))
_k32.CreateProcessW.restype = wintypes.BOOL
_k32.TerminateProcess.argtypes = (wintypes.HANDLE, wintypes.UINT)
_k32.TerminateProcess.restype = wintypes.BOOL
_k32.GetProcessTimes.argtypes = (wintypes.HANDLE, *[ctypes.POINTER(wintypes.FILETIME)] * 4)
_k32.GetProcessTimes.restype = wintypes.BOOL
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


def adopt(proc: subprocess.Popen) -> None:
    """`TREE_FLAGS` 起的根放进它的 Job 再放行；放不进去就杀掉它（还挂着、什么都没跑），不让它跑成
    一棵管不住的树。"""
    try:
        _adopt(proc.pid)
    except OSError:
        proc.kill()
        proc.wait()
        raise


def spawn_detached(argv: list[str], *, env: dict[str, str] | None,
                   cwd: str | None) -> tuple[int, str]:
    """起作业的根：以当前会话的 explorer 为父进程，再放进它自己那棵树的 Job。返回 pid 与要人知道的
    一句（没有 explorer 时为什么照旧起；空是没事）。"""
    shell, why = _shell()
    if not shell:  # 为什么交给调用方写进作业日志、记 WARNING；这里只留一行 info
        LOGGER.info("spawn_detached_without_shell why=%s argv0=%s", why, argv[0])
        return _spawn_in_place(argv, env=env, cwd=cwd), (
            f"作业没能脱离起它的进程（{why}）：起它的那一轮或服务结束时，它可能被一起结束")
    attributes = None
    try:
        size = ctypes.c_size_t()
        _k32.InitializeProcThreadAttributeList(None, 1, 0, ctypes.byref(size))  # 问要多大，必然失败
        attributes = ctypes.create_string_buffer(size.value)
        if not _k32.InitializeProcThreadAttributeList(attributes, 1, 0, ctypes.byref(size)):
            raise _fail("准备进程属性")
        parent = wintypes.HANDLE(shell)
        if not _k32.UpdateProcThreadAttribute(attributes, 0, PROC_THREAD_ATTRIBUTE_PARENT_PROCESS,
                                              ctypes.byref(parent), ctypes.sizeof(parent),
                                              None, None):
            raise _fail("把父进程指定成 explorer")
        info = _StartupInfoEx()
        info.StartupInfo.cb = ctypes.sizeof(info)
        info.lpAttributeList = ctypes.cast(attributes, wintypes.LPVOID)
        started = _ProcessInformation()
        line = ctypes.create_unicode_buffer(subprocess.list2cmdline(argv))
        block = None if env is None else ctypes.create_unicode_buffer(
            "".join(f"{k}={v}\0" for k, v in sorted(env.items(), key=lambda kv: kv[0].upper()))
            + "\0")
        if not _k32.CreateProcessW(None, line, None, None, False,
                                   TREE_FLAGS | CREATE_UNICODE_ENVIRONMENT
                                   | EXTENDED_STARTUPINFO_PRESENT,
                                   block, cwd, ctypes.byref(info), ctypes.byref(started)):
            raise _fail(f"起 {argv[0]}")
    finally:
        if attributes is not None:
            _k32.DeleteProcThreadAttributeList(attributes)
        _k32.CloseHandle(shell)
    try:
        _adopt(started.dwProcessId)
    except OSError:
        _k32.TerminateProcess(started.hProcess, KILLED_EXIT_CODE)  # 还挂着、什么都没跑
        raise
    finally:
        _k32.CloseHandle(started.hThread)
        _k32.CloseHandle(started.hProcess)
    return started.dwProcessId, ""


def _shell() -> tuple[int, str]:
    """当前会话的 explorer（桌面那个窗口的主人）：打开的句柄与空串；用不了就是 0 与为什么。它自己在
    Job 里（少见的沙箱环境）也不用：作业会从它那儿继承那个 Job。"""
    window = _u32.GetShellWindow()
    if not window:
        return 0, "这个会话里没有 explorer：SSH、服务里起的"
    pid = wintypes.DWORD()
    _u32.GetWindowThreadProcessId(window, ctypes.byref(pid))
    shell = _k32.OpenProcess(PROCESS_CREATE_PROCESS | PROCESS_QUERY_LIMITED_INFORMATION, False,
                             pid.value)
    if not shell:
        code = ctypes.get_last_error()
        return 0, f"打不开 explorer（进程 {pid.value}，WinError {code}）"
    inside = wintypes.BOOL()
    if not _k32.IsProcessInJob(shell, None, ctypes.byref(inside)) or inside.value:
        _k32.CloseHandle(shell)
        return 0, f"explorer（进程 {pid.value}）自己在 Job 里"
    ours = _identity(_k32.GetCurrentProcess())
    if ours is None or _identity(shell) != ours:
        _k32.CloseHandle(shell)
        return 0, (f"explorer（进程 {pid.value}）与本进程不是同一个用户或同一级权限"
                   "（以管理员身份运行的？），借它起的作业会换成它的身份")
    return shell, ""


def _identity(process: int) -> tuple[bytes, int] | None:
    """进程的身份：用户的 SID 与提没提权（TokenElevation）；查不出是 None。"""
    token = wintypes.HANDLE()
    if not _a32.OpenProcessToken(process, TOKEN_QUERY, ctypes.byref(token)):
        return None
    try:
        size = wintypes.DWORD()
        _a32.GetTokenInformation(token, TOKEN_USER, None, 0, ctypes.byref(size))  # 问要多大
        user = ctypes.create_string_buffer(size.value)
        elevated = wintypes.DWORD()
        if not (_a32.GetTokenInformation(token, TOKEN_USER, user, size, ctypes.byref(size))
                and _a32.GetTokenInformation(token, TOKEN_ELEVATION, ctypes.byref(elevated),
                                             ctypes.sizeof(elevated), ctypes.byref(size))):
            return None
        sid = ctypes.cast(user, ctypes.POINTER(wintypes.LPVOID))[0]  # TOKEN_USER 开头是 SID 指针
        return ctypes.string_at(sid, _a32.GetLengthSid(sid)), elevated.value
    finally:
        _k32.CloseHandle(token)


def _spawn_in_place(argv: list[str], *, env: dict[str, str] | None, cwd: str | None) -> int:
    """没有 explorer 时照旧起：试着脱离起它的 Job（终端、ssh 的 Job 许脱离就脱离得了；树的 Job
    不许），不许就留在原地。"""
    std = {"stdin": subprocess.DEVNULL, "stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL}
    try:
        proc = subprocess.Popen(argv, creationflags=TREE_FLAGS | CREATE_BREAKAWAY_FROM_JOB,
                                env=env, cwd=cwd, **std)
    except PermissionError:  # 起它的那个 Job 不许脱离：只能留在里面
        proc = subprocess.Popen(argv, creationflags=TREE_FLAGS, env=env, cwd=cwd, **std)
    adopt(proc)
    return proc.pid


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
    """Git for Windows 的 bash：先从 PATH 上的 git 推（git.exe 在 `<Git>/cmd/`、`<Git>/bin/` 或
    `<Git>/mingw64/bin/`，bash 在 `<Git>/bin/bash.exe`），PATH 上没有再看安装器登记的位置
    （注册表 `SOFTWARE\\GitForWindows` 的 InstallPath，本机级与本人级）。MinGit 不带 bash。"""
    roots: list[Path] = []
    if (git := shutil.which("git")) is not None:
        roots += Path(git).resolve().parents[:3]
    roots += _registered_git()
    for root in roots:
        candidate = root / "bin" / "bash.exe"
        if candidate.is_file():
            return str(candidate)
    if git is not None:
        raise FileNotFoundError(f"{git} 这份 git 没带 bash（MinGit？）：装完整的 Git for Windows，"
                                "或终端里跑 ai4sci setup")
    raise FileNotFoundError("没有 Git for Windows：终端里跑 ai4sci setup 装上")


def _registered_git() -> list[Path]:
    import winreg

    found: list[Path] = []
    for hive in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
        try:
            with winreg.OpenKey(hive, r"SOFTWARE\GitForWindows") as key:
                found.append(Path(winreg.QueryValueEx(key, "InstallPath")[0]))
        except OSError:
            continue  # 这一级没登记
    return found


def birth(pid: int) -> str:
    """进程的创建时间（FILETIME，100 纳秒一格）：认人用；进程不在是空串。"""
    process = _k32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not process:
        return ""
    try:
        code = wintypes.DWORD()
        if not _k32.GetExitCodeProcess(process, ctypes.byref(code)) or code.value != STILL_ACTIVE:
            return ""
        times = [wintypes.FILETIME() for _ in range(4)]
        if not _k32.GetProcessTimes(process, *(ctypes.byref(t) for t in times)):
            raise _fail(f"查进程 {pid} 的创建时间")
        return str(times[0].dwHighDateTime << 32 | times[0].dwLowDateTime)
    finally:
        _k32.CloseHandle(process)


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
