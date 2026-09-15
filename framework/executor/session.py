"""跑一次执行层会话：组 prompt → 调 `Runner` → 把取证日志按轮留档 → 交回 `RunResult`。

在四层的 executor 层：它是框架里唯一碰 `backends` 那个端口的地方，但**零模型调用**——
模型跑在适配器起的子进程里，这里只负责喂进去、收回来，并且不看会话自报的任何结论
（`RunResult.changed_files` 由适配器快照 diff 得出，判越界是能力那一层的事，P-2）。

模板与占位符由能力传进来（见 `prompting.build_prompt` 的说明），本层不知道实验内环
长什么样。`run_session` 是两个能力（实验、分析）共用的那一步：起会话、搬日志；
`run_executor` 是实验内环在它上面的薄封装（按轮留档、只许改 code/）。
"""

from __future__ import annotations

import shutil
from pathlib import Path

from backends import Runner, RunResult
from framework.executor import prompting
from framework.run import layout
from framework.run.context import RunContext, executor_timeout_s


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
    _stash_executor_logs(cwd, log_dir)
    return result


def run_executor(
    ctx: RunContext, runner: Runner, iter_n: int, template_path: Path,
    values: dict[str, object],
) -> RunResult:
    """实验内环的一轮：组 prompt、只许改 code/、日志按轮留档到 experiment/executor/iter-N/。"""
    prompt = prompting.build_prompt(template_path, values, ctx.domain_extra)
    return run_session(
        runner, prompt, cwd=ctx.work, allowed_paths=[layout.code(ctx.work)],
        log_dir=layout.executor_logs(ctx.run_dir, iter_n),
    )


def _stash_executor_logs(cwd: Path, log_dir: Path) -> None:
    """把适配器写在 cwd/.ai4sci/ 下的事件流搬到留档目录。

    为什么要搬：实验内环的 revert-to-best 用 git clean -x 连 ignored 文件一起清，取证日志
    留在 work/ 里会在下一轮开头被抹掉（真跑时就丢过一次）。日志是账本之外唯一能回答
    "执行层那一次到底干了什么"的证据（P-3、P-9），必须和产物一样留档。
    """
    src = layout.executor_scratch(cwd)
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
