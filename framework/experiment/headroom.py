"""接任务预检：基线跑出来之后，机器先回答"值不值得跑"（外层 #42）。

原来这是一个人工停点（"看基线决定开不开跑"）。人看的其实就三个数：基线值、σ、统计门；
再加一个只有人知道的数：这道题的尽头在哪（撒一大批起点探出来的最优，或文献值）。把尽头
写进 scoring.yaml（`metrics[].attainable`），这三四个数的比较就是零模型的算术，不用人守着。

两条硬判定，判中就停、不开跑：
- 门是 0：σ=0 且没写 min_delta，任何噪声都算改进，等于没门。
- 基线到尽头的距离 ≤ 门：改进再大也过不了门，这道题在这个门下无解，得改题、松门或换基线。

门高的算式只在这里定义一次：内环的统计门（capabilities/auto_research/gate.py）调的也是它。
预检说"还有 1.7 个门的空间"，内环用的就是同一把尺子。

在实验族的共享层：读设计留下的 scoring.yaml 与 baseline/，不认识产出目录之外的东西。
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from framework.experiment import pack as packs

# scoring 不写时的缺省，与 experiment/context.py 的 DEFAULT_MIN_DELTA 同值：那边是内环的读取点，
# 这边是预检的；两处都写明"缺省 0"，改一处要改另一处（测试锁着）
DEFAULT_MIN_DELTA = 0.0


def gate_height(accept_sigma: float, sigma: float, min_delta: float) -> float:
    """统计门的高度：`max(accept_sigma×σ, min_delta)`。

    σ 会退化：baseline/ 的几次重复完全一致时 σ=0，`accept_sigma×σ` 也就是 0，那时任何
    一点点差值都算"改进"，统计门形同虚设。`budget.min_delta` 是这种情况下的兜底最小
    改进量，两者取大的那个——门只会被抬高，不会被放低（M4）。
    """
    return max(accept_sigma * sigma, min_delta)


@dataclass(frozen=True)
class Headroom:
    """一次预检看到的全部数字。`problems()` 是硬判定，`summary()` 是给协调层念给人听的一行。"""

    metric: str
    direction: str
    baseline: float
    sigma: float
    gate: float
    attainable: float | None
    # 基线到尽头的距离，按方向取正：minimize 是 baseline − attainable。尽头没给就是 None
    room: float | None

    def problems(self) -> list[str]:
        out: list[str] = []
        if self.gate == 0:
            out.append(
                "统计门是 0：baseline/ 的重复跑完全一致（σ=0）且 scoring.yaml 没写 "
                "budget.min_delta，任何噪声都会算改进；给 min_delta 一个最小改进量，"
                "或者把基线重跑出真实的 σ")
        if self.room is not None:
            if self.room < 0:
                out.append(
                    f"尽头值填错了：基线 {self.metric}={self.baseline:.6g} 已经比 attainable="
                    f"{self.attainable:.6g} 还好，改 scoring.yaml 的 metrics[].attainable")
            elif self.gate > 0 and self.room <= self.gate:
                out.append(
                    f"这道题在这个门下无解：基线 {self.metric}={self.baseline:.6g} 离尽头 "
                    f"{self.attainable:.6g} 只有 {self.room:.6g}，统计门 {self.gate:.6g}，"
                    "改进再大也过不了门；改题（比如改成稳定性）、松门（accept_sigma / min_delta）"
                    "或换一个更差的基线")
        return out

    def summary(self) -> str:
        line = (f"baseline={self.baseline:.6g}\tsigma={self.sigma:.6g}\tgate={self.gate:.6g}")
        if self.room is None:
            return line + "\tattainable=-"
        gates = f"{self.room / self.gate:.1f}" if self.gate > 0 else "inf"
        return line + f"\tattainable={self.attainable:.6g}\troom={self.room:.6g}（{gates} 个门）"


def assess(pack: Path) -> Headroom:
    """读 scoring.yaml 与 baseline/，算出上面那几个数。要求包已经有合约的 baseline/
    （validate 管形状）。"""
    pack = Path(pack)
    scoring = packs.read_scoring(pack)
    metric = packs.primary_metric(scoring)
    budget = scoring["budget"]
    run0 = pack / packs.BASELINE_DIRNAME
    baseline = _read_json(run0 / "results.json")["metrics"][metric["name"]]
    sigma = float(_read_json(run0 / "sigma.json")[metric["name"]]["sigma"])
    gate = gate_height(float(budget["accept_sigma"]), sigma,
                       float(budget.get("min_delta", DEFAULT_MIN_DELTA)))
    attainable = metric.get("attainable")
    room = None
    if attainable is not None:
        attainable = float(attainable)
        room = baseline - attainable if metric["direction"] == "minimize" else attainable - baseline
    return Headroom(metric=metric["name"], direction=metric["direction"], baseline=float(baseline),
                    sigma=sigma, gate=gate, attainable=attainable, room=room)


def _read_json(path: Path) -> Any:
    if not path.is_file():
        raise FileNotFoundError(f"预检要读 {path}，文件不在：基线没跑完或 baseline/ 不合约")
    return json.loads(path.read_text(encoding="utf-8"))
