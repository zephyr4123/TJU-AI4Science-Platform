"""国内源：平台自己下载东西时用的镜像地址，只在这一处（外层 #277）。

主人 2026-10-07 定 onboarding 的硬要求：全程走国内源，不访问外网就能装好、跑起来。用到它们的有四处：
`framework/toolchain.py` 从 npmmirror 取两家 CLI 的原生程序；平台起 uv（skill 脚本、本机的实验环境）
时补上 PyPI、Python 的下载源与 HuggingFace 的镜像（`missing`）；skill 的锁文件对着清华锁（门禁查
`PYPI_OFFICIAL`）；一行命令的 `install/install.sh` 在 Python 还没有时也要用其中两个，那份写死在
脚本里、由 `tests/test_install_script.py` 对账。

用户 shell 里自己设了同名变量的（在国外、或有自己的源）用他的：`missing` 只补没设的。
"""

from __future__ import annotations

from collections.abc import Mapping

NPM_REGISTRY = "https://registry.npmmirror.com"
PYPI_INDEX = "https://mirrors.tuna.tsinghua.edu.cn/pypi/web/simple"
PYTHON_DOWNLOADS = "https://registry.npmmirror.com/-/binary/python-build-standalone"
HF_ENDPOINT = "https://hf-mirror.com"
# Windows 上没装 Git 时 `ai4sci setup` 从这里取 Git for Windows 的便携版（外层 #210）
GIT_FOR_WINDOWS = "https://registry.npmmirror.com/-/binary/git-for-windows"
# 官方 PyPI 的两个地址：uv 照锁文件装依赖时用锁文件里写的地址、不看上面的镜像设置，锁文件里出现
# 它们，装的时候就出了国（skill 门禁查，`framework/skills/library.py`）
PYPI_OFFICIAL = ("https://pypi.org/simple", "https://files.pythonhosted.org/")

# 变量 → 平台给的值；后面跟着「用户设了这些里任何一个就算他自己有源」
_WANTED = (
    ("UV_DEFAULT_INDEX", PYPI_INDEX, ("UV_DEFAULT_INDEX", "UV_INDEX_URL")),
    ("UV_PYTHON_INSTALL_MIRROR", PYTHON_DOWNLOADS, ("UV_PYTHON_INSTALL_MIRROR",)),
    ("HF_ENDPOINT", HF_ENDPOINT, ("HF_ENDPOINT",)),
)


def missing(environ: Mapping[str, str]) -> dict[str, str]:
    """`environ` 里没设的那几个下载源：盖在起 uv 的环境上。`UV_INDEX_URL` 是 uv 旧的写法，设了它也
    算用户有自己的 PyPI 源——两个都在时 uv 认新的，补上去就把用户的盖掉了。"""
    return {name: value for name, value, theirs in _WANTED
            if not any(environ.get(v) for v in theirs)}
