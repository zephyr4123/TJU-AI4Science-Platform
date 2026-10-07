"""假 CLI：一段 Python 顶替 claude / codex / 装出来的程序，测适配器起进程、读事件流、排空 stderr
那一层（模型那一层用剧本后端，P-5）。

POSIX 上就是带 shebang 的脚本。Windows 起不了脚本（CreateProcess 只认 exe），所以用系统自带的 C#
编译器（.NET Framework 4 的 csc.exe，Win10 / Win11 与 GitHub 的 windows runner 都有）编一个转发壳：
`<名字>.exe` 起本解释器跑旁边的 `<名字>.py`，自己那条命令行除程序名外原样转过去——引号怎么拆由
Python 照 Windows 的规矩拆，与真 CLI 收到的一样（外层 #210）。壳一次会话编一次。
"""

from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

_SHIM_CS = r"""
using System;
using System.Diagnostics;
using System.IO;

class Shim {
    static int Main() {
        string self = Process.GetCurrentProcess().MainModule.FileName;
        string line = Environment.CommandLine.TrimStart();
        int cut = line.StartsWith("\"") ? line.IndexOf('"', 1) + 1 : line.IndexOf(' ');
        string rest = cut < 0 ? "" : line.Substring(cut);
        string script = "\"" + Path.ChangeExtension(self, ".py") + "\"";
        var info = new ProcessStartInfo(@"PYTHON", script + rest);
        info.UseShellExecute = false;
        var child = Process.Start(info);
        child.WaitForExit();
        return child.ExitCode;
    }
}
"""


def fake_cli(path: Path, body: str) -> str:
    """把 `body`（Python 源码）做成 `path` 处一个能直接起的程序，返回交给 Popen 的路径。"""
    if os.name != "nt":
        path.write_text(f"#!{sys.executable}\n{body}", encoding="utf-8")
        path.chmod(0o755)
        return str(path)
    exe = path.with_suffix(".exe")
    path.with_suffix(".py").write_text(body, encoding="utf-8")
    shutil.copyfile(_shim(), exe)
    return str(exe)


def _shim() -> Path:
    source = _SHIM_CS.replace("PYTHON", sys.executable)
    digest = hashlib.sha256(source.encode("utf-8")).hexdigest()[:12]
    exe = Path(tempfile.gettempdir()) / f"ai4sci-fake-cli-{digest}.exe"
    if exe.is_file():
        return exe
    csc = Path(os.environ["WINDIR"]) / "Microsoft.NET" / "Framework64" / "v4.0.30319" / "csc.exe"
    cs = exe.with_suffix(".cs")
    cs.write_text(source, encoding="utf-8")
    done = subprocess.run([str(csc), "/nologo", f"/out:{exe}", str(cs)], capture_output=True,
                          check=False)
    assert done.returncode == 0, done.stdout.decode(errors="replace")
    return exe
