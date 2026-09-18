"""统计门：这一轮的差值算不算改进（纲领 workflow.md §2）。

单独一个模块，因为它是内环里唯一一处"下判断"的算术，也是最容易被悄悄放松的地方：
门高一处定义、比较一处实现，改它的 diff 就藏不住。本模块是纯函数，不读盘不写盘。
"""

from __future__ import annotations

from framework.contracts.headroom import gate_height
from framework.run.context import RunContext

# 分数与 best 完全相同：几乎只有"改动没生效"一种解释（rahman-1 第 2 轮：逐起点调优化器时换撒点
# 方式等于没换）。判决还是 discard，但备注要说清，下一轮的提示据此给修复方向（外层 #45）
NO_EFFECT_NOTE = "持平 delta=0：分数与 best 完全相同，改动很可能没有生效"


def gate(ctx: RunContext) -> float:
    """统计门的高度。算式只有一处定义（`contracts.headroom.gate_height`）：接任务的预检与
    内环的比较用的是同一个门，预检说"有空间"内环就不会用另一把尺子。"""
    return gate_height(ctx.accept_sigma, ctx.sigma, ctx.min_delta)


def compare(ctx: RunContext, best_metric: float, metric: float) -> tuple[str, str]:
    """统计门：差值超过门才算改进，门内一律判持平不留（纲领 §2）。"""
    if ctx.direction == "minimize":
        delta = best_metric - metric
    elif ctx.direction == "maximize":
        delta = metric - best_metric
    else:
        # load_context 已经断言过一次；这里不拿 else 当 maximize 兜底：方向写错时
        # 悄悄按反方向比，会把变差的改动当改进留下来（P-7）
        raise ValueError(f"未知的 direction {ctx.direction!r}，只认 minimize / maximize")
    height = gate(ctx)
    if delta > height:
        return "keep", f"改进 delta={delta:.6g} > gate={height:.6g}"
    if delta > 0:
        return "discard", f"within noise: delta={delta:.6g} <= gate={height:.6g}"
    if delta == 0:
        return "discard", NO_EFFECT_NOTE
    return "discard", f"变差 delta={delta:.6g}"
