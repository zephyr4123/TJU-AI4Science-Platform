"""跑一次执行层会话：组 prompt → 调 `Runner` → 把取证日志按轮留档 → 交回 `RunResult`。

在四层的 executor 层：它是框架里唯一碰 `backends` 那个端口的地方，但**零模型调用**——
模型跑在适配器起的子进程里，这里只负责喂进去、收回来，并且不看会话自报的任何结论
（`RunResult.changed_files` 由适配器快照 diff 得出，判越界是能力那一层的事，P-2）。

模板与占位符由能力传进来（见 `prompting.build_prompt` 的说明），本层不知道实验内环
长什么样。
"""

from __future__ import annotations

import shutil
from pathlib import Path

from backends import Runner, RunResult
from framework.executor import prompting
from framework.run import layout
from framework.run.context import RunContext, executor_timeout_s


def run_executor(
    ctx: RunContext, runner: Runner, iter_n: int, template_path: Path,
    values: dict[str, object],
) -> RunResult:
    """组一轮的 prompt、起一次执行层会话、把它写的日志搬进留档目录。

    `allowed_paths` 只是"尽量收紧"的意图，各家 CLI 的权限模型对不齐；真正的门是回来
    之后按 `changed_files` 判越界（纲领 §5）。
    """
    prompt = prompting.build_prompt(template_path, values, ctx.domain_extra)
    result = runner.run(
        prompt=prompt, cwd=ctx.work, timeout_s=executor_timeout_s(),
        allowed_paths=[layout.code(ctx.work)],
    )
    _stash_executor_logs(ctx.run_dir, ctx.work, iter_n)
    return result


def _stash_executor_logs(run_dir: Path, work: Path, iter_n: int) -> None:
    """把适配器写在 work/.ai4sci/ 下的事件流搬到 experiment/executor/iter-N/。

    为什么要搬：revert-to-best 用 git clean -x 连 ignored 文件一起清，取证日志留在 work/
    里会在下一轮开头被抹掉（真跑时就丢过一次）。日志是账本之外唯一能回答"执行层那一轮
    到底干了什么"的证据（P-3、P-9），必须和快照一样按轮留档。
    """
    src = layout.executor_scratch(work)
    if not src.is_dir():
        return
    dst = layout.executor_logs(run_dir, iter_n)
    dst.mkdir(parents=True, exist_ok=True)
    for path in sorted(src.iterdir()):
        shutil.move(str(path), str(dst / path.name))
    src.rmdir()


def executor_report(result: RunResult) -> str:
    """执行层这一轮的自述 = stream-json 最终 result 事件的文本；没有就空串，不编。"""
    final = next((e for e in reversed(result.events) if e.get("type") == "result"), None)
    text = (final or {}).get("result")
    return text.strip() if isinstance(text, str) else ""
