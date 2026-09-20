"""设计的前半段：起一次执行层会话，按需求写评分契约、harness 与基线代码的草稿；回来后框架封
harness、跑 lint、跑校验。

只碰端口不碰模型（与 `executor.session` 一样）。判断不在这里：评分脚本对不对由人在断点上签字，
基线好不好由 `make_run0.sh` 跑出来的数说话。本模块只保证草稿是**能被校验**的形状，以及每一步都留了
证据（提示、事件流、改了哪些文件）。
"""

from __future__ import annotations

import logging
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from backends import Runner
from framework import skills
from framework.executor import prompting, session
from framework.experiment import pack as packs

LOGGER = logging.getLogger("ai4sci.design")
TEMPLATE = Path(__file__).resolve().parent / "prompt.md"
# 执行层只许写这些：评分契约、评分脚本、基线代码；data/ env/ 是研究者带来的，锁死
WRITABLE_DIRS = ("harness", "code")
WRITABLE_FILES = (packs.SCORING_NAME,)
# lint 规则与 pyproject [tool.ruff] 一致；同一组常数渲染进提示第 7 条，执行层被告知的就是被检查的
LINT_SELECT = "E,F,W,B,I,BLE,UP"
LINT_LINE_LENGTH = 100
# 第二个会话把现状文件贴回去；单个文件超过这个长度就截断（草稿都很短，超了本身就是问题）
FILE_MAX_CHARS = 20_000
LOG_DIRNAME = "executor"


class DesignFailed(RuntimeError):
    """设计步骤没能交出可校验的草稿。信息直接给协调层看，不留半个栈让人猜（P-7）。"""


@dataclass
class DesignOutcome:
    """一次设计会话的全部可取证结果。lint 与 validate 的问题是清单不是异常：草稿已经在磁盘上，
    协调层要拿着清单决定是喂回执行层改第二版还是找人。"""

    session: int
    log_dir: Path
    changed_files: list[str]
    cost_usd: float
    duration_s: float
    report: str
    sealed: list[str]
    lint_problems: list[str] = field(default_factory=list)
    validate_problems: list[str] = field(default_factory=list)

    @property
    def problems(self) -> list[str]:
        return self.lint_problems + self.validate_problems


def draft(
    pack: Path, requirement: str, hypothesis: str, domain: str, domains_root: Path,
    runner: Runner, *, feedback: str = "", timeout_s: float | None = None,
) -> DesignOutcome:
    """组提示 → 起会话（只放行 scoring.yaml、harness/、code/）→ 判越界 → 补 domain → 封 harness →
    ruff → validate。

    validate 这一步不查 baseline/：草稿刚写完，基线还没跑。
    `pack` 下按 `executor/session-N/` 留档：提示原文、事件流、stderr。
    `feedback` 非空或磁盘上已有草稿时，提示带上现状文件，让执行层照着改而不是重写。
    """
    pack = Path(pack).resolve()
    domains_root = Path(domains_root).resolve()
    domain_dir = domains_root / domain
    if not (domain_dir / packs.PROFILE_NAME).is_file():
        raise DesignFailed(f"--domain {domain!r} 在 {domains_root} 下没有领域包")
    current = _current_files(pack)
    values = {
        "requirement": requirement.strip(),
        "hypothesis": (f"## 假设（假设阶段的产出，设计要能检验它）\n\n{hypothesis.strip()}"
                       if hypothesis.strip() else ""),
        "current": current or "scoring.yaml、harness/ 与 code/ 还是空的，从零写。",
        "feedback": f"## 这次要改什么\n\n{feedback.strip()}" if feedback.strip() else "",
        "lint_select": LINT_SELECT, "lint_line_length": LINT_LINE_LENGTH,
    }
    prompt = prompting.build_prompt(
        TEMPLATE, values, skills=skills.for_executor(domain, domains_root=domains_root))

    log_dir, number = _next_session_dir(pack / LOG_DIRNAME)
    log_dir.mkdir(parents=True)
    (log_dir / "prompt.md").write_text(prompt, encoding="utf-8")  # 先落盘：会话死了也知道喂了什么
    result = session.run_session(
        runner, prompt, cwd=pack,
        allowed_paths=[pack / name for name in (*WRITABLE_DIRS, *WRITABLE_FILES)],
        log_dir=log_dir, timeout_s=timeout_s,
    )

    allowed = tuple(f"{name}/" for name in WRITABLE_DIRS)
    outside = [f for f in result.changed_files
               if not f.startswith(allowed) and f not in WRITABLE_FILES]
    if outside:  # 文件留着当证据，不回滚：协调层要看它到底动了什么
        raise DesignFailed(
            f"执行层改了 {' / '.join((*WRITABLE_DIRS, *WRITABLE_FILES))} 之外的文件："
            f"{', '.join(sorted(outside))}")
    if result.timed_out or result.exit_code != 0:
        tail = result.stdout_tail.strip().splitlines()
        why = "超时" if result.timed_out else f"退出码 {result.exit_code}"
        raise DesignFailed(
            f"执行层会话没走完（{why}）：{tail[-1] if tail else '无输出'}；日志在 {log_dir}"
        )
    if not result.changed_files:
        raise DesignFailed(
            f"执行层什么都没写；它的自述：{session.executor_report(result) or '（空）'}"
        )

    _stamp_domain(pack, domain)
    _ruff_fix_imports(pack)  # 封之前修：SHA256SUMS 记的得是修完的文件
    sealed = packs.seal_harness(pack)
    lint = _ruff(pack)
    validate = packs.validate_pack(pack, domains_root, require_baseline=False)
    outcome = DesignOutcome(
        session=number, log_dir=log_dir, changed_files=sorted(result.changed_files),
        cost_usd=result.cost_usd, duration_s=result.duration_s,
        report=session.executor_report(result), sealed=sealed,
        lint_problems=lint, validate_problems=validate,
    )
    LOGGER.info(
        "design_draft pack=%s session=%d changed=%d sealed=%s lint=%d validate=%d cost_usd=%s",
        pack, number, len(outcome.changed_files), ",".join(sealed) or "-",
        len(lint), len(validate), result.cost_usd,
    )
    return outcome


def _stamp_domain(pack: Path, domain: str) -> None:
    """`domain` 是框架定的（--domain），写进 scoring.yaml：实验按它快照领域包，执行层不用猜。
    scoring.yaml 不在或读不出来就不动它，让 validate 去报。"""
    path = pack / packs.SCORING_NAME
    if not path.is_file():
        return
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError:
        return
    if not isinstance(raw, dict):
        return
    raw["domain"] = domain
    path.write_text(yaml.safe_dump(raw, allow_unicode=True, sort_keys=False), encoding="utf-8")


def _current_files(pack: Path) -> str:
    """磁盘上已有的 scoring.yaml、harness/ 与 code/ 文件，原样贴回去；SHA256SUMS 是框架的，不给。"""
    blocks = []
    paths = [pack / name for name in WRITABLE_FILES]
    for name in WRITABLE_DIRS:
        paths += sorted((pack / name).rglob("*"))
    for path in paths:
        if not path.is_file() or path.name == "SHA256SUMS" or "__pycache__" in path.parts:
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        if len(text) > FILE_MAX_CHARS:
            text = text[:FILE_MAX_CHARS] + f"\n…（截断，原文 {len(text)} 字符）\n"
        rel = path.relative_to(pack).as_posix()
        lang = {"py": "python", "sh": "bash", "yaml": "yaml"}.get(path.suffix.lstrip("."), "")
        blocks.append(f"### {rel}\n\n```{lang}\n{text.rstrip()}\n```")
    if not blocks:
        return ""
    return "下面是现在磁盘上的文件，照它们改，别重写结构：\n\n" + "\n\n".join(blocks)


def _next_session_dir(executor_root: Path) -> tuple[Path, int]:
    """`<pack>/executor/session-N`，N 从 1 起、接着已有的编号；旧会话永远不覆盖。"""
    taken = [int(p.name.split("-", 1)[1]) for p in executor_root.glob("session-*")
             if p.is_dir() and p.name.split("-", 1)[1].isdigit()]
    number = max(taken, default=0) + 1
    return executor_root / f"session-{number}", number


# 封 harness 之前自动修的规则：只有 import 排序这类纯格式、ruff 能安全改的。真跑时两版草稿都只因
# 一条 I001 被判失败、各让执行层重来 13 分钟（外层 #116）——格式不是执行层该花一轮的事
LINT_AUTOFIX = "I"


def _ruff_fix_imports(pack: Path) -> None:
    """对 harness/ 跑 `ruff --fix-only --select I`：只修 import 排序，别的规则不动、留给检查报。"""
    hdir = pack / "harness"
    if not hdir.is_dir():
        return
    proc = subprocess.run(
        [sys.executable, "-m", "ruff", "check", "--isolated", "--no-cache", "--fix-only",
         "--select", LINT_AUTOFIX, "--line-length", str(LINT_LINE_LENGTH), "harness"],
        cwd=pack, capture_output=True, text=True, check=False,
    )
    if proc.returncode != 0 or "No module named ruff" in proc.stderr:
        raise DesignFailed(
            f"ruff --fix-only 跑不起来（退出码 {proc.returncode}）："
            f"{proc.stderr.strip().splitlines()[-1:] or '无输出'}；"
            "平台 venv 里要有 ruff（requirements.lock）"
        )
    if proc.stdout.strip():
        LOGGER.info("design_ruff_fix pack=%s %s", pack, proc.stdout.strip().splitlines()[-1])


def _ruff(pack: Path) -> list[str]:
    """对 harness/ 跑 ruff，一行一条问题。ruff 不在就报错，不静默当作没问题（P-7）。

    `--isolated` 不读任何配置文件：规则由上面的常数定，跟目录放在哪无关，
    也正是提示第 7 条告诉执行层的那一组。
    """
    hdir = pack / "harness"
    if not hdir.is_dir():
        return []
    proc = subprocess.run(
        [sys.executable, "-m", "ruff", "check", "--isolated", "--no-cache",
         "--output-format", "concise", "--select", LINT_SELECT,
         "--line-length", str(LINT_LINE_LENGTH), "harness"],
        cwd=pack, capture_output=True, text=True, check=False,
    )
    if proc.returncode not in (0, 1) or "No module named ruff" in proc.stderr:
        raise DesignFailed(
            f"ruff 跑不起来（退出码 {proc.returncode}）："
            f"{proc.stderr.strip().splitlines()[-1:] or '无输出'}；"
            "平台 venv 里要有 ruff（requirements.lock）"
        )
    return [line for line in proc.stdout.splitlines()
            if line.strip() and not line.startswith(("Found ", "[*]", "All checks passed"))]
