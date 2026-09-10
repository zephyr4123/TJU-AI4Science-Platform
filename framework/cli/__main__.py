"""`python -m framework.cli` 的入口：与装出来的 `ai4sci` 命令走同一个 `main`。

单独一个文件是包化之后的必需品——模块形态时 `if __name__ == "__main__"` 就够了，
包形态下 `-m` 找的是 `__main__`。测试用 `-m` 起真进程，缺了它就等于 CLI 没法被直接跑。
"""

from __future__ import annotations

import sys

from framework.cli import main

sys.exit(main())
