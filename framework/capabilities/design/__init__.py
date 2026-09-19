"""写评分脚本、跑基线：设计阶段里的那个能力——读需求（与假设），起执行层写评分契约、harness
与基线代码，框架封、lint、校验，接着起 `make_run0.sh` 跑基线、算预检。

前半段的干活代码在同包的 `drafting.py`（组提示、起会话、判越界、封 harness、ruff、validate），
后半段在 `baseline.py`。评分脚本写完不跑基线没意义，基线又只能跑封好的评分脚本，所以是一个
（外层 #96）。

产出 `design/<n>/` 就是实验族的那包东西：scoring.yaml、harness/、code/、data/（原件的拷贝）、env/
（原件里的 env/）、baseline/。草稿有问题就停在前半段（草稿留在盘上，问题一行一条），协调层
`--continue design/<n> --feedback` 让执行层照着改第二版（纲领 P-19：continuable，同一次产出）。
"""

from __future__ import annotations

import logging
import shutil
from pathlib import Path

from framework import paths
from framework.capabilities.design.baseline import run_baseline
from framework.capabilities.design.drafting import DesignFailed, draft
from framework.contracts import requirement
from framework.contracts.capability import Capability, CapabilityFailed, Inputs, Param, Ports
from framework.experiment import env
from framework.experiment import pack as packs

LOGGER = logging.getLogger("ai4sci.design")
NAME = "design"
MATERIALS_DIRNAME = "materials"
# 原件里不搬进 data/ 的：env/ 另有去处，其余是别人的状态
IGNORED = (".git", "__pycache__", ".venv", ".DS_Store", env.ENV_DIRNAME)
DESCRIPTOR = Capability(
    name=NAME,
    stage="设计",
    title="评分脚本与基线",
    brief="按需求写评分契约、评分脚本与基线代码，跑出起点成绩",
    does=(
        "起一个执行层会话，照已确认的需求（带了假设阶段的产出就一并读）写评分契约 scoring.yaml"
        "（指标、方向、预算、统计门）、评分脚本 harness/（launcher.sh、evaluate.py、make_run0.sh）"
        "与一版最朴素的基线代码 code/。会话结束后框架接手："
        "给脚本加执行位、写 SHA256SUMS 封住 harness，跑 ruff 与契约校验；"
        "都过了就按 env/ 建 .venv、起 make_run0.sh 跑基线——重复 inner_k 次得到起点成绩与 σ，"
        "写进 baseline/；最后做预检：统计门 max(accept_sigma × σ, min_delta) 要大于零，"
        "给了尽头值 attainable 则基线到尽头的距离要大于门。"
    ),
    does_not=(
        "不改需求：requirement.md 是它的输入，人确认过才动手。不跑内环、不开实验。"
        "封好的 harness 之后任何能力都不许再改；要改评分脚本，带修改意见接着改这次产出，"
        "不另开目录。"
    ),
    brings=(
        "已确认的需求 requirement.md（要优化什么、数据在哪、怎么算好、花多少）；原件 materials/"
        "（评分脚本重算指标要用的数据，搬进 data/）与 materials/env/（python-version 与"
        "requirements.lock，研究者环境的 pip freeze）；假设阶段的产出可选。"
        "改第二版时接着上一次产出，带修改意见。"
    ),
    leaves=(
        "scoring.yaml、harness/（封好的评分脚本与 SHA256SUMS）、code/（基线代码）、data/、env/、"
        "baseline/（results.json、repeats/、sigma.json：改进率的分母与统计门的基线）、.venv/；"
        "执行层会话的日志在 executor/。"
    ),
    stops=(
        "执行层改了别的目录、ruff 或契约校验没过：草稿留在盘上、问题一行一条，"
        "等修改意见改第二版。make_run0.sh 退非零或预检没过（门为零、离尽头不够一个门）："
        "停下来说清，这道题不值得跑。都过了就一次成活，结论行里是基线、σ、门与离尽头几个门。"
    ),
    params=(
        Param("domain", "str", packs.DEFAULT_DOMAIN,
              "领域包名（domains/ 下的目录）：执行层提示按它追加领域约定", "领域包"),
        Param("feedback", "str", "",
              "喂回执行层的修改意见（改第二版）；写 @<文件> 就读那个文件；空串是第一版", "修改意见",
              in_flow=False),
    ),
    needs_executor=True,
    continuable=True,
)


def run(output_dir: Path, inputs: Inputs, ports: Ports, *, domain: str = packs.DEFAULT_DOMAIN,
        feedback: str = "") -> str:
    output_dir = Path(output_dir).resolve()
    assert ports.runner is not None, "design 需要执行层端口"
    if feedback.startswith("@"):
        path = Path(feedback[1:])
        if not path.is_file():
            raise CapabilityFailed(f"--feedback 指的文件不存在：{path}")
        feedback = path.read_text(encoding="utf-8")
    _prepare(output_dir, inputs.workspace)
    hypotheses = inputs.of_stage("hypothesis")
    hypothesis = "\n\n".join(_read_text_files(h) for h in hypotheses)
    try:
        outcome = draft(output_dir, requirement.read(inputs.workspace), hypothesis, domain,
                        paths.domains_root(), ports.runner, feedback=feedback)
    except DesignFailed as exc:
        raise CapabilityFailed(str(exc)) from exc
    head = (f"session={outcome.session}\tchanged={len(outcome.changed_files)}"
            f"\tsealed={','.join(outcome.sealed) or '-'}\tlint={len(outcome.lint_problems)}"
            f"\tvalidate={len(outcome.validate_problems)}\tcost_usd={outcome.cost_usd:.4f}"
            f"\tlog={outcome.log_dir}")
    oid = f"design/{output_dir.name}"
    if outcome.problems:
        # 草稿已经封在盘上，问题一行一条：协调层决定喂回执行层改第二版还是找人
        raise CapabilityFailed(
            f"design draft\t{head}\n" + "\n".join(outcome.problems)
            + f"\nnext=把上面的问题喂回：ai4sci cap design --continue {oid} --feedback @<文件>")
    baseline = run_baseline(output_dir)
    return (f"design ok\t{head}\t{baseline}"
            f"\tnext=对照需求「怎么算好」核对 harness/evaluate.py，报给人；"
            f"人签了就 ai4sci cap auto-research --from {oid}")


def _prepare(pack: Path, workspace: Path) -> None:
    """第一次进这个目录：原件搬进 data/（env/ 除外），原件里的 env/ 搬成包的 env/。
    第二次（--continue）什么都不动：草稿在，别覆盖。"""
    materials = Path(workspace) / MATERIALS_DIRNAME
    if (pack / "data").exists():
        return
    if not materials.is_dir():
        raise CapabilityFailed(f"工作区没有 {MATERIALS_DIRNAME}/：研究者的原件要放在那里")
    src_env = materials / env.ENV_DIRNAME
    spec, problems = env.read_env(materials)
    if spec is None:
        raise CapabilityFailed(
            f"{MATERIALS_DIRNAME}/{env.ENV_DIRNAME}/ 要有 {env.PYTHON_VERSION_NAME}（研究者脚本用的"
            f"Python 版本）"
            f"与 {env.REQUIREMENTS_NAME}（pip freeze）：\n" + "\n".join(problems))
    shutil.copytree(materials, pack / "data", ignore=shutil.ignore_patterns(*IGNORED))
    shutil.copytree(src_env, pack / env.ENV_DIRNAME)
    LOGGER.info("design_prepare pack=%s data_files=%d",
                pack, sum(1 for p in (pack / "data").rglob("*") if p.is_file()))


def _read_text_files(directory: Path) -> str:
    """假设产出里的文本文件原样拼起来（meta.yaml 不算）：假设阶段现在没有能力，助理写什么都行。"""
    parts = []
    for path in sorted(Path(directory).rglob("*")):
        if path.is_file() and path.suffix in (".md", ".txt") and path.name != "meta.yaml":
            parts.append(f"### {path.relative_to(directory).as_posix()}\n\n"
                         + path.read_text(encoding="utf-8").strip())
    return "\n\n".join(parts)
