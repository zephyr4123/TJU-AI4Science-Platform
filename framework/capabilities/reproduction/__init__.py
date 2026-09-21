"""原码复现基线：设计阶段的第二颗能力——别人的代码原样跑一遍，与论文值并排（纲领 P-24）。

与 `design`（自己写基线代码）并列、可替换，产出同一包东西：scoring.yaml、harness/、code/、data/、
env/、baseline/。不同的是 code/ 不是执行层写的，是原件里 download 拉下来的上游仓库；执行层只写
「怎么起它、怎么把它的输出算成论文那几个数、目标是多少」三样。框架跑一次基线就是复现结果，
把论文值与我们的值并排写在结论行——**对没对上不判**：助理念给研究者，研究者签（主人：前期别把
机器校验卡太死）。允许改别人的代码（老代码跑不起来是常态），但 code/ 相对上游的每一处改动写进
`upstream.diff`，那是复现的诚实底线，不是门槛。

前半段（组提示、起会话、封 harness、ruff、validate）与后半段（跑基线）都在实验族的共享层
`experiment/drafting.py`、`experiment/baseline.py`，与 `design` 共用；两颗互不 import。
"""

from __future__ import annotations

import json
import logging
import shutil
import subprocess
from pathlib import Path

from framework import paths
from framework.contracts import requirement
from framework.contracts.capability import Capability, CapabilityFailed, Inputs, Param, Ports
from framework.experiment import drafting, env
from framework.experiment import pack as packs
from framework.experiment.baseline import run_baseline

LOGGER = logging.getLogger("ai4sci.reproduction")
NAME = "reproduction"
PROMPT_TEMPLATE = Path(__file__).resolve().parent / "prompt.md"
MATERIALS_DIRNAME = "materials"
RECEIPT_NAME = ".ai4sci-download.json"  # download skill 留在目录里的收据
# 原件里不搬的：别人的状态、平台自己的环境目录
IGNORED = (".git", "__pycache__", ".venv", ".DS_Store", env.ENV_DIRNAME)
CODE_LISTING_MAX = 300  # 提示里 code/ 的目录清单最多列多少个文件：上游仓库可能几千个
# 执行层这次会话的额度：要先读懂别人的整个仓库再写壳，比从零写一版多得多——真跑时缺省的 30 轮
# 在读完仓库、写完四个文件、还没来得及自述时就被掐了（外层 #122）
SESSION_MAX_TURNS = 80
SESSION_MAX_BUDGET_USD = 6.0
DESCRIPTOR = Capability(
    name=NAME,
    stage="设计",
    title="原码复现基线",
    brief="拿论文自己的代码原样跑一遍，与论文值并排",
    does=(
        "把原件里论文的代码（download 拉下来的那个目录）搬进 code/，其余原件搬进 data/，"
        "记下它的来源与 commit。起一个执行层会话，照已确认的需求与文献阶段的材料来源，"
        "写评分契约 scoring.yaml（指标就是论文报的那几个数，尽头值 attainable 填论文值）、"
        "评分脚本 harness/（launcher.sh 按论文的配置起上游代码，evaluate.py 把它的输出算成"
        "那几个数，"
        "make_run0.sh 跑一次加重复）；上游代码跑不起来时允许改 code/，"
        "改动记进 upstream.diff。"
        "会话结束后框架封 harness、跑 ruff 与契约校验，都过了就在所选算力上按 env/ 建环境、"
        "起 make_run0.sh 跑一次——这一次就是复现结果，结论行里论文值与我们的值并排。"
    ),
    does_not=(
        "不判对没对上：容差与算不算复现成功是研究者在需求里定、看着两列数签的。"
        "不写训练代码、不改评测定义；不搜材料、不下载（那是文献阶段与 download 的事）。"
        "预检里「离尽头不够一个门就无解」那一条不适用：基线到论文值的距离就是复现的结果本身。"
    ),
    brings=(
        "已确认的需求（哪篇论文、哪几个数、复现到第几级、对上的标准）；原件 materials/ 里"
        "论文的代码目录（带 download 的收据更好：来源与 commit 有据）、数据、materials/env/"
        "（按上游的 requirements 算的清单，或机器上现成的解释器）；文献阶段的产出 sources.md 可选。"
        "改第二版时接着上一次产出，带修改意见。"
    ),
    leaves=(
        "scoring.yaml、harness/（封好的评分脚本与 SHA256SUMS）、code/（上游代码，可能带必要改动）、"
        "upstream.json（来源、commit）、upstream.diff（改了什么）、data/、env/、"
        "baseline/（一次复现的成绩与重复）；执行层会话的日志在 executor/。"
    ),
    stops=(
        "执行层改了别的目录、ruff 或契约校验没过：草稿留在盘上、问题一行一条，等修改意见改第二版。"
        "make_run0.sh 退非零：停下来说清（多半是上游代码在这台机器上跑不起来，"
        "看日志改 code/ 或换环境）。"
        "跑成就一次成活，结论行里是论文值、我们的值、σ 与改了几个上游文件。"
        "基线没跑成（环境装不上、机器换了、被叫停）：接着干、不给修改意见，只重跑基线。"
    ),
    params=(
        Param("code", "str", "",
              "原件里哪个目录是论文的代码（download 拉下来的目录名）；第一次开跑必须给",
              "代码目录"),
        Param("domain", "str", packs.DEFAULT_DOMAIN,
              "领域包名（domains/ 下的目录）：执行层提示按它追加领域约定", "领域包"),
        Param("feedback", "str", "",
              "喂回执行层的修改意见（改第二版）；写 @<文件> 就读那个文件；接着干时不给就是"
              "草稿不动、只重跑基线", "修改意见",
              in_flow=False),
    ),
    needs_executor=True,
    needs_compute=True,
    continuable=True,
)


def run(output_dir: Path, inputs: Inputs, ports: Ports, *, code: str = "",
        domain: str = packs.DEFAULT_DOMAIN, feedback: str = "") -> str:
    output_dir = Path(output_dir).resolve()
    assert ports.runner is not None and ports.compute is not None, "reproduction 需要执行层与算力"
    if feedback.startswith("@"):
        path = Path(feedback[1:])
        if not path.is_file():
            raise CapabilityFailed(f"--feedback 指的文件不存在：{path}")
        feedback = path.read_text(encoding="utf-8")
    materials = Path(inputs.workspace) / MATERIALS_DIRNAME
    _prepare(output_dir, materials, code)
    upstream_dir = materials / packs.read_upstream(output_dir)["name"]
    oid = f"design/{output_dir.name}"
    next_step = (f"next=把论文值（attainable）与我们的值（baseline）念给研究者，对上了没由他判；"
                 f"签了就 ai4sci cap reproducibility --from {oid}")
    if _drafted(output_dir) and not feedback.strip():
        # 接着干、没有修改意见 = 草稿留着不动，只重跑基线（环境没装成、机器换了、上次被叫停）
        problems = packs.validate_pack(output_dir, paths.domains_root(), require_baseline=False)
        if problems:
            raise CapabilityFailed("草稿不合约，先喂修改意见改一版：\n" + "\n".join(problems))
        changed = packs.write_upstream_diff(output_dir, upstream_dir)
        baseline = run_baseline(output_dir, ports.compute, check_headroom=False)
        return (f"reproduction ok\tsession=-\tchanged=0\tsealed=-\tlint=0\tvalidate=0"
                f"\tcost_usd=0.0000\t{baseline}\tupstream_changed={len(changed)}\t{next_step}")
    sources = "\n\n".join(_read_text_files(d) for d in inputs.of_stage("literature"))
    values = {
        "requirement": requirement.read(inputs.workspace).strip(),
        "sources": sources or "（没有材料清单：文献阶段没跑，只有需求与 code/ 里的东西）",
        "upstream": _upstream_line(output_dir),
    }
    try:
        outcome = drafting.draft(
            output_dir, PROMPT_TEMPLATE, values, domain, paths.domains_root(), ports.runner,
            current=_current_files(output_dir, upstream_dir), feedback=feedback,
            max_turns=SESSION_MAX_TURNS, max_budget_usd=SESSION_MAX_BUDGET_USD)
    except drafting.DraftFailed as exc:
        raise CapabilityFailed(str(exc)) from exc
    changed = packs.write_upstream_diff(output_dir, upstream_dir)
    head = (f"session={outcome.session}\tchanged={len(outcome.changed_files)}"
            f"\tsealed={','.join(outcome.sealed) or '-'}\tlint={len(outcome.lint_problems)}"
            f"\tvalidate={len(outcome.validate_problems)}\tcost_usd={outcome.cost_usd:.4f}"
            f"\tlog={outcome.log_dir}")
    if outcome.problems:
        raise CapabilityFailed(
            f"reproduction draft\t{head}\n" + "\n".join(outcome.problems)
            + f"\nnext=把上面的问题喂回：ai4sci cap reproduction --continue {oid} "
            "--feedback @<文件>")
    baseline = run_baseline(output_dir, ports.compute, check_headroom=False)
    return f"reproduction ok\t{head}\t{baseline}\tupstream_changed={len(changed)}\t{next_step}"


def _drafted(pack: Path) -> bool:
    return (pack / packs.SCORING_NAME).is_file() and (pack / "harness" / "SHA256SUMS").is_file()


def _prepare(pack: Path, materials: Path, code: str) -> None:
    """第一次进这个目录：论文的代码搬进 code/、其余原件搬进 data/、原件里的 env/ 搬成包的 env/，
    记下上游的出处。第二次（--continue）什么都不动，只查 materials/env/ 与包里的 env/ 还对不对
    得上。"""
    if (pack / "code").exists():
        changed = _env_changed(materials / env.ENV_DIRNAME, pack / env.ENV_DIRNAME)
        if changed and _same_interpreter(materials / env.ENV_DIRNAME, pack / env.ENV_DIRNAME):
            # 现成环境补了几个包（ai4sci env add）：解释器没变、清单多了几行，刷新快照接着干——
            # 真跑时镜像环境缺 scipy，补上之后不该让执行层把壳从头再写一遍
            shutil.rmtree(pack / env.ENV_DIRNAME)
            shutil.copytree(materials / env.ENV_DIRNAME, pack / env.ENV_DIRNAME)
            LOGGER.info("reproduction_env_refreshed pack=%s changed=%s", pack, changed)
            return
        if changed:
            raise CapabilityFailed(
                f"{MATERIALS_DIRNAME}/{env.ENV_DIRNAME}/ 与这次设计的 env/ 对不上"
                f"（{', '.join(changed)}）：环境变了不能接着改，重开一次："
                "ai4sci cap reproduction")
        return
    if not materials.is_dir():
        raise CapabilityFailed(f"工作区没有 {MATERIALS_DIRNAME}/：论文的代码要先拉到那里"
                               "（ai4sci skill run download git …）")
    candidates = sorted(p.name for p in materials.iterdir()
                        if p.is_dir() and p.name not in IGNORED)
    if not code:
        raise CapabilityFailed(
            "要说清原件里哪个目录是论文的代码：--code <目录名>；"
            f"{MATERIALS_DIRNAME}/ 里有：{', '.join(candidates) or '（空）'}")
    src = materials / code
    if not src.is_dir():
        raise CapabilityFailed(
            f"{MATERIALS_DIRNAME}/{code}/ 不存在；有：{', '.join(candidates) or '（空）'}")
    spec, problems = env.read_env(materials)
    if spec is None:
        raise CapabilityFailed(
            f"{MATERIALS_DIRNAME}/{env.ENV_DIRNAME}/ 要有 {env.PYTHON_VERSION_NAME} 与 "
            f"{env.REQUIREMENTS_NAME}（按上游的 requirements 算：ai4sci env resolve --from "
            f"{MATERIALS_DIRNAME}/{code}/requirements.txt；或机器上现成的：ai4sci env use）：\n"
            + "\n".join(problems))
    # 收据不进 code/：出处已经记进 upstream.json，上游的树保持原样
    shutil.copytree(src, pack / "code", ignore=shutil.ignore_patterns(*IGNORED, RECEIPT_NAME))
    shutil.copytree(materials, pack / "data",
                    ignore=shutil.ignore_patterns(*IGNORED, code, RECEIPT_NAME))
    shutil.copytree(materials / env.ENV_DIRNAME, pack / env.ENV_DIRNAME)
    (pack / packs.UPSTREAM_NAME).write_text(
        json.dumps(_upstream_of(src, code), ensure_ascii=False, indent=2), encoding="utf-8")
    LOGGER.info("reproduction_prepare pack=%s code=%s files=%d", pack, code,
                sum(1 for p in (pack / "code").rglob("*") if p.is_file()))


def _upstream_of(src: Path, name: str) -> dict[str, str]:
    """上游的出处：download 的收据优先（来源、commit 都在）；没有收据但是 git 仓就问 git；
    都不是就只记名字——出处空着比编一个强。"""
    receipt = src / RECEIPT_NAME
    if receipt.is_file():
        doc = json.loads(receipt.read_text(encoding="utf-8"))
        return {"name": name, "source": str(doc.get("source", "")),
                "commit": str(doc.get("commit", doc.get("sha256", "")))}
    if (src / ".git").exists():
        head = subprocess.run(["git", "-C", str(src), "rev-parse", "HEAD"],
                              capture_output=True, text=True, check=False)
        origin = subprocess.run(["git", "-C", str(src), "remote", "get-url", "origin"],
                                capture_output=True, text=True, check=False)
        return {"name": name, "source": origin.stdout.strip() if origin.returncode == 0 else "",
                "commit": head.stdout.strip() if head.returncode == 0 else ""}
    return {"name": name, "source": "", "commit": ""}


def _upstream_line(pack: Path) -> str:
    doc = packs.read_upstream(pack)
    source = doc.get("source") or "（来源未记录）"
    commit = doc.get("commit") or "（commit 未记录）"
    return f"`code/` 是上游仓库 `{doc.get('name')}` 的拷贝：来源 {source}，commit {commit}。"


def _current_files(pack: Path, upstream_dir: Path) -> str:
    """磁盘现状：scoring.yaml 与 harness/ 原样贴；code/ 是整个上游仓库，只贴目录清单（有上限）与
    相对上游改过的那几个文件——整仓贴进提示既贴不下也没必要，执行层自己 Read。"""
    text = drafting.current_files(pack, dirs=("harness",))
    code = pack / "code"
    if not code.is_dir():
        return text
    listing = [p.relative_to(code).as_posix() for p in sorted(code.rglob("*"))
               if p.is_file() and not set(p.relative_to(code).parts) & set(IGNORED)]
    shown = listing[:CODE_LISTING_MAX]
    more = f"\n…（还有 {len(listing) - len(shown)} 个）" if len(listing) > len(shown) else ""
    blocks = [f"### code/（上游仓库，{len(listing)} 个文件；自己 Read 要看的）\n\n"
              + "\n".join(shown) + more]
    if upstream_dir.is_dir():
        changed = [rel for rel in _changed_files(upstream_dir, code)]
        for rel in changed:
            path = code / rel
            if not path.is_file() or b"\x00" in path.read_bytes()[:8192]:
                continue
            body = path.read_text(encoding="utf-8", errors="replace")
            if len(body) > drafting.FILE_MAX_CHARS:
                body = body[:drafting.FILE_MAX_CHARS] + f"\n…（截断，原文 {len(body)} 字符）\n"
            blocks.append(f"### code/{rel}（相对上游改过）\n\n```\n{body.rstrip()}\n```")
    joined = "\n\n".join(blocks)
    if text:
        return f"{text}\n\n{joined}"
    return "下面是现在磁盘上的文件，照它们改，别重写结构：\n\n" + joined


def _changed_files(upstream_dir: Path, code: Path) -> list[str]:
    before = {p.relative_to(upstream_dir).as_posix(): p for p in upstream_dir.rglob("*")
              if p.is_file() and not set(p.relative_to(upstream_dir).parts) & set(IGNORED)}
    after = {p.relative_to(code).as_posix(): p for p in code.rglob("*")
             if p.is_file() and not set(p.relative_to(code).parts) & set(IGNORED)}
    return [rel for rel in sorted(after)
            if rel not in before or before[rel].read_bytes() != after[rel].read_bytes()]


def _same_interpreter(source: Path, snapshot: Path) -> bool:
    """两边都是「用现成的」且指向同一台机器的同一个解释器。"""
    a, b = source / env.INTERPRETER_NAME, snapshot / env.INTERPRETER_NAME
    return a.is_file() and b.is_file() and a.read_bytes() == b.read_bytes()


def _env_changed(source: Path, snapshot: Path) -> list[str]:
    names = (env.PYTHON_VERSION_NAME, env.REQUIREMENTS_NAME, env.INTERPRETER_NAME)
    changed = []
    for name in names:
        a, b = source / name, snapshot / name
        if (a.read_bytes() if a.is_file() else None) != (b.read_bytes() if b.is_file() else None):
            changed.append(name)
    return changed


def _read_text_files(directory: Path) -> str:
    """文献产出里的文本文件原样拼起来（meta.yaml 不算）：sources.md 在前，别的随后。"""
    parts = []
    files = sorted(Path(directory).rglob("*"),
                   key=lambda p: (p.name != "sources.md", p.as_posix()))
    for path in files:
        if path.is_file() and path.suffix in (".md", ".txt") and path.name != "meta.yaml":
            parts.append(f"### {path.relative_to(directory).as_posix()}\n\n"
                         + path.read_text(encoding="utf-8").strip())
    return "\n\n".join(parts)
