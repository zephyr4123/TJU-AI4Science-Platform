"""剧本执行层：按预先写好的剧本改 cwd，形状与真 `Runner` 完全一致。

为什么内环测试不能用真 CLI：内环要跑二十多轮，每轮一次模型调用既慢又贵，且结论
不确定——而内环本身是**确定性代码**，它的正确性不该由模型的发挥来证明（P-5）。
剧本后端把"执行层这一轮干了什么"变成一个可枚举的输入：真改进、假改进、改坏、
假成功、动 harness、崩溃、超时、缺依赖、什么都不改，一条一条摆出来。

`changed_files` 走 `backends._snapshot` 同一份快照 diff：跟真适配器同一条取证路径，
剧本自己说改了什么一律不作数（P-2）。
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from backends import RunResult, Tuning
from backends._snapshot import diff, snapshot

# 一个 move 要么是 {相对路径: 内容}，要么是一个拿 cwd 干活的函数
Move = dict[str, str] | Callable[[Path], None]


class ScriptExhausted(AssertionError):
    """剧本用完了还在调 run()：说明循环没在该停的地方停下，测试要炸而不是继续编。"""


class ScriptedRunner:
    # 顶着真适配器的名字：起会话那层按名字查按人的设置里这家用什么模型（P-25）
    name = "claude_code"

    def __init__(
        self,
        moves: list[Move],
        *,
        cost_usd: float = 0.01,
        duration_s: float = 0.5,
        raise_at: int | None = None,
        exception: BaseException | None = None,
        die_at: tuple[int, ...] = (),
    ) -> None:
        self.moves = list(moves)
        self.cost_usd = cost_usd
        self.duration_s = duration_s
        # raise_at 是"第几次调用 run() 时炸"，用来模拟第 N 轮被杀：异常原样抛给 run_loop，
        # 由它一路冒到调用方（不吞异常），剩下的靠 resume 收拾。
        self.raise_at = raise_at
        self.exception = exception or KeyboardInterrupt()
        # die_at：这几次调用模拟执行层被外部 kill -9——改了一半、退出码 -9、没有 result 事件
        self.die_at = set(die_at)
        self.calls = 0
        self.prompts: list[str] = []
        # 每轮的自述，与 moves 一一对应；缺省一句"剧本第 N 步"，测试笔记时显式给
        self.reports: list[str] = []

    @staticmethod
    def tool_guide(bash_rules: tuple[str, ...]) -> str:
        """与 Claude Code 适配器同一段话：能力的测试对着「Bash 只放行」这几个字对账。"""
        commands = "、".join(f"`{p} …`" for p in bash_rules)
        return f"## 工具怎么用\n\n- Bash 只放行 {commands} 一类命令。\n"

    def run(
        self, prompt: str, cwd: Path, timeout_s: float, allowed_paths: list[Path],
        bash_rules: tuple[str, ...] = (), tuning: Tuning | None = None,
        max_turns: int | None = None,
        max_budget_usd: float | None = None,
    ) -> RunResult:
        self.calls += 1
        self.prompts.append(prompt)
        self.bash_rules = bash_rules  # 框架给执行层放行了哪些命令，测试对账（只该有 ai4sci skill）
        self.tuning = tuning  # 按人的设置里这家用什么，测试对账
        self.limits = (max_turns, max_budget_usd)  # 能力给这次会话的轮数 / 花费上限
        assert timeout_s > 0 and allowed_paths, "runner 的调用形状变了，剧本要跟着改"
        if self.raise_at is not None and self.calls == self.raise_at:
            raise self.exception
        if not self.moves:
            raise ScriptExhausted(f"剧本已用完，但第 {self.calls} 次 run() 又来了")
        move = self.moves.pop(0)
        before = snapshot(cwd)
        _apply(move, Path(cwd))
        if self.calls in self.die_at:
            return RunResult(exit_code=-9, events=[], changed_files=diff(before, snapshot(cwd)),
                             cost_usd=float("nan"), duration_s=self.duration_s,
                             timed_out=False, stdout_tail="")
        # 与真适配器同形：事件流写在 cwd/.ai4sci/，框架负责把它搬到按轮留档的位置
        log_dir = Path(cwd) / ".ai4sci"
        log_dir.mkdir(exist_ok=True)
        (log_dir / f"executor-scripted-{self.calls}.jsonl").write_text(
            '{"type":"system","subtype":"init","scripted":true}\n', encoding="utf-8"
        )
        report = self.reports.pop(0) if self.reports else f"剧本第 {self.calls} 步"
        return RunResult(
            exit_code=0,
            # 与真后端同形：Claude Code 的自述在最终 result 事件里，适配器抄进 report
            events=[{"type": "result", "result": report}],
            changed_files=diff(before, snapshot(cwd)),
            cost_usd=self.cost_usd, duration_s=self.duration_s, timed_out=False,
            stdout_tail="scripted", report=report,
        )


def _apply(move: Move, cwd: Path) -> None:
    if callable(move):
        move(cwd)
        return
    for rel, content in move.items():
        path = cwd / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")


def write_train(y_pred: list[float]) -> dict[str, str]:
    """最常用的一步：改 code/train.py，让它写出指定的预测（mse = 各项平方的均值）。"""
    return {"code/train.py": (
        "import json\n"
        "from pathlib import Path\n"
        "TASK_DIR = Path(__file__).resolve().parent.parent\n"
        f"(TASK_DIR / 'predictions.json').write_text(json.dumps({{'y_pred': {y_pred!r}}}))\n"
    )}
