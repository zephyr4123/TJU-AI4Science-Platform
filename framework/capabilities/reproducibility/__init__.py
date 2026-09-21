"""复现性分析：分析阶段的第二颗能力——读一次「原码复现基线」的产出，执行层写 analysis.md：论文值
与我们的值对照、复现到第几级、硬件与环境差异、偏离论文之处、容易与困难、未决（纲领 P-24）。

与 `analysis`（分析初稿，读实验的账本）并列、可替换：输入不同（读设计那包，不读实验），提示不同，
产出同名 `analysis.md`、同一份形状契约（`experiment.analysis`：三节必有、数据表可回溯）。数字对不对
由验证能力回溯：来源写成 `design/<n>/baseline`、`design/<n>/repeat_<seed>`、`design/<n>/scoring`
（论文值）、`design/<n>/sigma`。零模型调用：收集输入、组 prompt、起一次会话、校验形状。
"""

from __future__ import annotations

import logging
import math
from pathlib import Path

from framework import skills
from framework.contracts import requirement
from framework.contracts.capability import Capability, CapabilityFailed, Inputs, Ports
from framework.contracts.output import read_meta
from framework.executor import prompting, session
from framework.experiment import artifacts, env
from framework.experiment import pack as packs
from framework.experiment.analysis import check_session_outcome
from framework.experiment.context import DIRECTION_ZH
from framework.experiment.results import read_metrics

LOGGER = logging.getLogger("ai4sci.reproducibility")
NAME = "reproducibility"
DOC_NAME = "analysis.md"
LOG_DIRNAME = "executor"
PROMPT_TEMPLATE = Path(__file__).resolve().parent / "prompt.md"
DIFF_MAX_CHARS = 20_000
LOCK_HEAD_LINES = 40  # 环境清单只贴头部：版本出处在头几行，几百行的 pin 分析不需要

DESCRIPTOR = Capability(
    name=NAME,
    stage="分析",
    title="复现性分析",
    brief="论文值与复现值对照，说清差在哪、为什么",
    does=(
        "起一个执行层会话，只给它一次原码复现基线的产出：评分契约里的论文值、baseline/ 的一次成绩与"
        "每次重复、σ、上游代码的来源与 commit、code/ 相对上游的改动、环境清单与跑在哪台机器上，"
        "以及需求与文献阶段的材料来源；让它写一份 analysis.md：结论（复现到第几级、对上没对上、"
        "为什么）、数据表（| 来源 | 指标 | 值 |，来源写成 design/<n>/scoring、design/<n>/baseline、"
        "design/<n>/repeat_<seed>、design/<n>/sigma，只许从结果清单抄）、方法与环境、偏离与改动、"
        "容易与困难、证伪与未决。会话结束后框架核形状：三节必有、数据表至少一行能解析。"
    ),
    does_not=(
        "不核对数字对不对（验证阶段回溯）、不重跑、不改代码、不替人判「算不算复现成功」——"
        "它把两列数与全部差异摆清楚，判定是研究者签字那一下。"
    ),
    brings=(
        "一次设计阶段的产出（原码复现基线跑过的）：scoring.yaml、baseline/、upstream.json、"
        "upstream.diff、env/；文献阶段的产出 sources.md 可选。"
    ),
    leaves="analysis.md；执行层会话的日志在 executor/。",
    stops=(
        "一次成稿就退出。会话写了别的文件、三节缺一、数据表一行都解析不出：判失败、报告原因，"
        "协调层看了决定重跑（新开一次产出）还是找人。"
    ),
    needs_executor=True,
)


def run(output_dir: Path, inputs: Inputs, ports: Ports) -> str:
    output_dir = Path(output_dir).resolve()
    assert ports.runner is not None, "复现性分析要执行层端口"
    design_dir = inputs.one_of("design", "复现性分析")
    oid = next(i for i in inputs.ids if i.startswith("design/"))
    if not (design_dir / packs.BASELINE_DIRNAME / "results.json").is_file():
        raise CapabilityFailed(f"{oid} 还没有跑出 baseline/，没有可分析的复现结果")
    scoring = packs.read_scoring(design_dir)
    domain = str(scoring.get("domain", packs.DEFAULT_DOMAIN))
    prompt = prompting.build_prompt(PROMPT_TEMPLATE, _prompt_values(design_dir, oid, inputs),
                                    skills=skills.for_executor(domain))
    result = session.run_session(
        ports.runner, prompt, cwd=output_dir, allowed_paths=[output_dir],
        log_dir=output_dir / LOG_DIRNAME,
    )
    claims = check_session_outcome(output_dir, result, doc_name=DOC_NAME, log_dirname=LOG_DIRNAME)
    LOGGER.info("reproducibility_done out=%s claims=%d cost_usd=%s duration_s=%.1f",
                output_dir, len(claims), result.cost_usd, result.duration_s)
    cost = "nan" if math.isnan(result.cost_usd) else f"{result.cost_usd:.4f}"
    return (f"reproducibility ok\tclaims={len(claims)}\tcost_usd={cost}\tpath={DOC_NAME}"
            f"\tnext=ai4sci cap verify --from analysis/{output_dir.name} --from {oid}")


def _prompt_values(design_dir: Path, oid: str, inputs: Inputs) -> dict[str, object]:
    scoring = packs.read_scoring(design_dir)
    metric = packs.primary_metric(scoring)
    upstream = packs.read_upstream(design_dir)
    meta = read_meta(design_dir)
    compute = meta.compute or {}
    where = (", ".join(f"{k}={v}" for k, v in compute.items() if v)
             or "（meta 没记在哪台机器上跑的）")
    sources = "\n\n".join(_read_text_files(d) for d in inputs.of_stage("literature"))
    return {
        "requirement": requirement.read(inputs.workspace).strip(),
        "sources": sources or "（没有材料清单：文献阶段没跑）",
        "oid": oid,
        "metric_name": metric["name"], "direction": metric["direction"],
        "direction_zh": DIRECTION_ZH[metric["direction"]],
        "paper": _paper_block(scoring),
        "results": _results_listing(design_dir, oid),
        "upstream": (f"仓库 `{upstream.get('name') or '?'}`，"
                     f"来源 {upstream.get('source') or '（未记录）'}，"
                     f"commit `{upstream.get('commit') or '（未记录）'}`"),
        "diff": _diff_block(design_dir),
        "environment": _env_block(design_dir, where),
    }


def _paper_block(scoring: dict) -> str:
    lines = []
    for m in scoring.get("metrics", ()):
        target = m.get("attainable")
        shown = (f"**{float(target)!r}**" if isinstance(target, (int, float))
                 else "（scoring 里没填）")
        lines.append(f"- `{m['name']}`（方向 {m['direction']}）：论文值 {shown}")
    return "\n".join(lines)


def _results_listing(design_dir: Path, oid: str) -> str:
    """每一次的全部指标一行一条，值用 repr 原样给；来源写成 `<设计 id>/<名字>`。"""
    lines: list[str] = []
    scoring = packs.read_scoring(design_dir)
    for m in scoring.get("metrics", ()):
        target = m.get("attainable")
        if isinstance(target, (int, float)):
            lines.append(f"- {oid}/scoring：{m['name']} = {float(target)!r}（论文值）")
    for name, path in artifacts.design_results(design_dir).items():
        metrics, problems = read_metrics(path)
        if metrics is None:
            lines.append(f"- {oid}/{name}：results.json 不合约（{'；'.join(problems)}），不能引用")
            continue
        lines.append(f"- {oid}/{name}：" + "，".join(f"{k} = {v!r}" for k, v in metrics.items()))
    sigma_path = design_dir / packs.BASELINE_DIRNAME / "sigma.json"
    if sigma_path.is_file():
        import json

        doc = json.loads(sigma_path.read_text(encoding="utf-8"))
        for name, entry in doc.items():
            if isinstance(entry, dict) and "sigma" in entry:
                lines.append(f"- {oid}/sigma：{name} = {float(entry['sigma'])!r}"
                             f"（{len(entry.get('seeds', ()))} 次重复的样本标准差）")
    return "\n".join(lines) or "（baseline/ 里一个结果都没有）"


def _diff_block(design_dir: Path) -> str:
    path = design_dir / packs.UPSTREAM_DIFF_NAME
    if not path.is_file():
        return "（没有 upstream.diff：这次产出不是原码复现基线，或没记上游）"
    text = path.read_text(encoding="utf-8", errors="replace")
    if len(text) > DIFF_MAX_CHARS:
        text = text[:DIFF_MAX_CHARS] + f"\n…（截断，原文 {len(text)} 字符）\n"
    return text.rstrip()


def _env_block(design_dir: Path, where: str) -> str:
    env_dir = design_dir / env.ENV_DIRNAME
    parts = [f"- 跑在：{where}"]
    version = env_dir / env.PYTHON_VERSION_NAME
    if version.is_file():
        parts.append(f"- Python：`{version.read_text(encoding='utf-8').strip()}`")
    interpreter = env_dir / env.INTERPRETER_NAME
    if interpreter.is_file():
        parts.append("- 用的是机器上现成的解释器："
                     f"`{interpreter.read_text(encoding='utf-8').strip()}`")
    lock = env_dir / env.REQUIREMENTS_NAME
    if lock.is_file():
        head = lock.read_text(encoding="utf-8").splitlines()[:LOCK_HEAD_LINES]
        parts.append("- 依赖清单（头部）：\n\n```\n" + "\n".join(head) + "\n```")
    return "\n".join(parts)


def _read_text_files(directory: Path) -> str:
    parts = []
    files = sorted(Path(directory).rglob("*"),
                   key=lambda p: (p.name != "sources.md", p.as_posix()))
    for path in files:
        if path.is_file() and path.suffix in (".md", ".txt") and path.name != "meta.yaml":
            parts.append(f"### {path.relative_to(directory).as_posix()}\n\n"
                         + path.read_text(encoding="utf-8").strip())
    return "\n\n".join(parts)
