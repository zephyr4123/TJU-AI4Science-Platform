"""六类失败的确定性分类（纲领 workflow.md §2）。

分类不调模型：规则是写死的、优先级是固定的，同样的输入永远得到同样的结论——
裁判是框架，执行层不参与判自己的卷（P-2）。分类结果连同一句修复提示喂给下一轮，
提示是常数大小的固定文本，不是把 stderr 整段塞回上下文（P-9）。

优先级从上到下，第一条命中即返回：
    只读被改 → 超时 → 缺依赖 → 崩溃 → 结果缺失 / 不合 schema / status 不是 ok → 指标 NaN

崩溃与"没有结果"的边界（M1）：崩溃看的是 stderr 里有没有 traceback，不是只看退出码。
真任务包的 `launcher.sh` 写着 `set -euo pipefail`，而 harness 契约要求 `evaluate.py`
拒收产物时用 `SystemExit(码)` 带一句话退出、不打 traceback（tasks/mlp-regression 就是
这么写的）。于是"执行层只 print 了一个分数、什么产物都没写"这种**假成功**在退出码上与
"跑崩了"长得一模一样。假成功比崩溃更值得单独点名：它是执行层在骗分，修法也完全不同
（去把产物写出来 vs 去照 stderr 修报错），所以退非 0 而 stderr 没有 traceback 时一律
先看产物，判 no_results。反过来，退非 0 但 results.json 合法、主指标有限的极端情况仍
归 crash——产物齐了却非正常退出，说明跑的过程中出了事，这个成绩不能采信。
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from pathlib import Path

import jsonschema

from backends._snapshot import snapshot  # 与执行层取证同一份快照实现，不另起一套 sha 逻辑
from framework.packs import SCHEMA_DIR

READONLY_VIOLATED = "readonly_violated"
TIMEOUT = "timeout"
MISSING_DEPENDENCY = "missing_dependency"
CRASH = "crash"
NO_RESULTS = "no_results"
NAN_METRIC = "nan_metric"
NOOP = "noop"

# 只读区：执行层与 harness 都不许动它们（纲领 §2）
READONLY_DIRS = ("harness/", "data/")
SCHEMA_PATH = SCHEMA_DIR / "results.schema.json"

FAILURE_STATUSES = (READONLY_VIOLATED, TIMEOUT, MISSING_DEPENDENCY, CRASH, NO_RESULTS, NAN_METRIC)

# stderr 里出现这些字样就判缺依赖：三条都是解释器自己吐的固定串，不做模糊匹配。
_DEPENDENCY_MARKERS = ("ModuleNotFoundError", "ImportError", "No module named")
# 判崩溃的凭据：解释器自己打的固定串。运行期异常有 traceback 头；主脚本编译期就挂
# （语法错）时 CPython 只打 "SyntaxError:" 没有 traceback 头，所以两条都要认。
TRACEBACK_MARKER = "Traceback (most recent call last)"
_CRASH_MARKERS = (TRACEBACK_MARKER, "SyntaxError:")

HINTS = {
    READONLY_VIOLATED: "只准改 code/ 下的文件；harness/ 与 data/ 是只读的，已回滚到上一个最好版本",
    TIMEOUT: "上一轮超出墙钟预算被杀；请降低计算量（更小的规模 / 更少的轮数），不要加大",
    MISSING_DEPENDENCY: "上一轮 import 了环境里没有的包；只用标准库与任务包已有的依赖，"
                        "不要新增依赖",
    CRASH: "上一轮跑崩了；先照 stderr 摘要修掉报错，改完自己确认语法与形状对得上",
    NO_RESULTS: "上一轮没产出合规的 results.json；train.py 必须真的写出预测产物，光打印分数不算数",
    NAN_METRIC: "上一轮主指标是 NaN 或 Inf；通常是学习率过大或除零，先把数值稳定性修掉",
    NOOP: "上一轮一个文件都没改；这一轮必须在 code/ 下落到实际改动",
}


@dataclass
class Verdict:
    status: str
    note: str


def readonly_verdict(paths: list[str]) -> Verdict:
    """执行层改到了 code/ 之外——事后 diff 判的，不看 CLI 自报（纲领 §5）。"""
    return Verdict(READONLY_VIOLATED, f"改动越界：{', '.join(paths[:5])}")


def noop_verdict() -> Verdict:
    return Verdict(NOOP, "一个文件都没改")


def gitignored_verdict() -> Verdict:
    """改动都落在任务包 `.gitignore` 挡住的路径上：git 里留不下东西，按没改处理。"""
    return Verdict(NOOP, "改动全被 .gitignore 挡住，未产生 commit")


def classify_run(
    *,
    tampered: list[str],
    timed_out: bool,
    exit_code: int | None,
    stderr_tail: str,
    results_problems: list[str],
    metric: float | None,
) -> Verdict | None:
    """判一轮 harness 的结局；返回 None 表示这一轮跑出了可比的成绩。

    `exit_code is None` 是"未知"（续跑读回的 job），按没通过处理：不知道就不能算通过。
    """
    if tampered:
        return Verdict(READONLY_VIOLATED, f"只读文件被改：{', '.join(tampered[:5])}")
    if timed_out:
        return Verdict(TIMEOUT, "超出墙钟预算被杀")
    failed = exit_code != 0  # None（未知）也落在这边
    code = "未知" if exit_code is None else exit_code
    if failed and any(marker in stderr_tail for marker in _DEPENDENCY_MARKERS):
        return Verdict(MISSING_DEPENDENCY, f"退出码 {code}，stderr 有 import 错误")
    if failed and any(marker in stderr_tail for marker in _CRASH_MARKERS):
        return Verdict(CRASH, f"退出码 {code}：{_tail_line(stderr_tail)}")
    if results_problems:
        return Verdict(NO_RESULTS, results_problems[0])
    if metric is None:
        return Verdict(NO_RESULTS, "results.json 里没有主指标")
    if failed:
        # 产物齐、主指标也在，却非正常退出：不是假成功，但成绩同样不能采信
        return Verdict(CRASH, f"退出码 {code}，但 results.json 是全的：{_tail_line(stderr_tail)}")
    if not math.isfinite(metric):
        return Verdict(NAN_METRIC, f"主指标不是有限数：{metric!r}")
    return None


def _tail_line(stderr_tail: str) -> str:
    """取 stderr 最后一行非空内容做 note；账本一行一条，不塞整段日志。"""
    lines = [ln.strip() for ln in stderr_tail.splitlines() if ln.strip()]
    return lines[-1][:160] if lines else "stderr 为空"


# --------------------------------------------------------------------------
# 分类要用的取证：只读文件的指纹、harness 产物、stderr 尾巴
# --------------------------------------------------------------------------
def readonly_hashes(root: Path) -> dict[str, str]:
    """`harness/` 与 `data/` 的内容指纹——"评测和数据没被改"的唯一证据（纲领 §2）。"""
    return {p: h for p, h in snapshot(Path(root)).items() if p.startswith(READONLY_DIRS)}


def tampered(before: dict[str, str], after_root: Path) -> list[str]:
    """跑之前与跑之后的只读文件对比；删除也算改动。"""
    after = readonly_hashes(after_root)
    return sorted(p for p in before.keys() | after.keys() if before.get(p) != after.get(p))


def harness_sha(work: Path) -> str:
    """账本里的 harness_sha：SHA256SUMS 自身的指纹，一列就能证明评测那套没换过。"""
    sums = Path(work) / "harness" / "SHA256SUMS"
    return hashlib.sha256(sums.read_bytes()).hexdigest() if sums.is_file() else "-"


def read_results(path: Path, metric_name: str) -> tuple[float | None, list[str]]:
    """读 harness 的产物，返回（主指标, 问题清单）。

    NaN 照收不误：Python 的 json 默认解析 NaN，而 NaN 要走 nan_metric 这一类，
    在这里当成"文件不合法"会把病因说错，下一轮给执行层的修复提示也就跟着错。

    `status` 是 harness 自己对这一趟的定性，不是 ok 就当成"没有可用结果"（问题清单里带上
    它自报的值）：指标算出来了但 harness 说这趟不算数时，采信指标就是采信一个作废的成绩。
    """
    path = Path(path)
    if not path.is_file():
        return None, [f"results.json 缺失：{path}"]
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except ValueError as exc:
        return None, [f"results.json 解析失败：{' '.join(str(exc).split())}"]
    schema = json.loads((SCHEMA_PATH).read_text(encoding="utf-8"))
    problems = [
        f"results.json 不合 schema：{' '.join(str(e.message).split())}"
        for e in jsonschema.Draft202012Validator(schema).iter_errors(doc)
    ]
    status = doc.get("status") if isinstance(doc, dict) else None
    if status is not None and status != "ok":
        problems.append(f"harness 自报 status={status!r}，不是 ok")
    value = doc.get("metrics", {}).get(metric_name) if isinstance(doc, dict) else None
    if value is not None and not isinstance(value, (int, float)):
        return None, [*problems, f"主指标 {metric_name} 不是数字：{value!r}"]
    if value is None and not problems:
        problems.append(f"results.json 里没有主指标 {metric_name}")
    return value, problems


def stderr_tail(path: Path, limit: int = 4000) -> str:
    """stderr 的尾巴：分类要看它，但只看尾部，日志本体留在盘上（P-9）。"""
    path = Path(path)
    return path.read_text(encoding="utf-8", errors="replace")[-limit:] if path.is_file() else ""
