"""跑一次执行层会话：调 `Runner` → 把取证日志留档 → 交回 `RunResult`。

在 executor 层：它是框架里唯一碰 `backends` 那个端口的地方，但**零模型调用**——
模型跑在适配器起的子进程里，这里只负责喂进去、收回来，并且不看会话自报的任何结论
（`RunResult.changed_files` 由适配器快照 diff 得出，判越界是能力那一层的事，P-2）。

提示由能力组好传进来，本层不知道任何一个能力长什么样。
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path

from backends import Runner, RunResult

EXECUTOR_TIMEOUT_ENV = "AI4SCI_EXECUTOR_TIMEOUT_S"
DEFAULT_EXECUTOR_TIMEOUT_S = 900.0
# 执行层适配器把事件流写在 cwd/<这个目录>/ 下；跑完搬走留档
SCRATCH_DIRNAME = ".ai4sci"


def executor_timeout_s() -> float:
    """执行层单轮墙钟上限（秒）。它与 harness 的预算是两根轴：改代码慢不等于跑得慢。"""
    raw = os.environ.get(EXECUTOR_TIMEOUT_ENV)
    value = DEFAULT_EXECUTOR_TIMEOUT_S if raw is None else float(raw)
    assert value > 0, f"{EXECUTOR_TIMEOUT_ENV} 必须是正数，得到 {value!r}"
    return value


def run_session(
    runner: Runner, prompt: str, cwd: Path, allowed_paths: list[Path], log_dir: Path,
    timeout_s: float | None = None,
) -> RunResult:
    """起一次执行层会话，然后把它写在 `cwd/.ai4sci/` 下的事件流搬到 `log_dir`。

    `allowed_paths` 只是"尽量收紧"的意图，各家 CLI 的权限模型对不齐；真正的门是回来
    之后按 `changed_files` 判越界，那是能力的事（纲领 §5）。
    """
    result = runner.run(
        prompt=prompt, cwd=cwd,
        timeout_s=executor_timeout_s() if timeout_s is None else timeout_s,
        allowed_paths=allowed_paths,
    )
    stash_executor_logs(cwd, log_dir)
    return result


def stash_executor_logs(cwd: Path, log_dir: Path) -> None:
    """把适配器写在 cwd/.ai4sci/ 下的事件流搬到留档目录。

    为什么要搬：实验内环的 revert-to-best 用 git clean -x 连 ignored 文件一起清，取证日志
    留在 work/ 里会在下一轮开头被抹掉（真跑时就丢过一次）。日志是账本之外唯一能回答
    "执行层那一次到底干了什么"的证据（P-3、P-9），必须和产物一样留档。
    """
    src = Path(cwd) / SCRATCH_DIRNAME
    if not src.is_dir():
        return
    log_dir.mkdir(parents=True, exist_ok=True)
    for path in sorted(src.iterdir()):
        shutil.move(str(path), str(log_dir / path.name))
    src.rmdir()


def executor_report(result: RunResult) -> str:
    """执行层这一轮的自述 = stream-json 最终 result 事件的文本；没有就空串，不编。"""
    final = next((e for e in reversed(result.events) if e.get("type") == "result"), None)
    text = (final or {}).get("result")
    return text.strip() if isinstance(text, str) else ""
