"""设计步骤：起一次执行层会话给任务包写 harness 与基线草稿，回来后框架封 harness、跑 lint、跑校验。

在 executor 层：和 `session.run_session` 一样只碰端口不碰模型。它**不是** `capabilities/`
里的能力——能力的入口形状是 run 目录（`run(run_dir, ports)`），设计动的是任务包，还没有 run；
等面板要把它当节点画时再升格成能力，那时才有真实调用点（P-8，有第二个用例才抽象）。

从两个手工实例（mlp-regression 手写、boehm-nll 执行层写了两个会话）抽出来的固定动作只有
这几步：组提示、起会话、判越界、封 harness、lint、校验。判断不在这里：评分脚本对不对由人
签字（`evaluate.py` 是唯一不许 AI 碰的东西），基线好不好由 `make_run0.sh` 跑出来的数说话。
本模块只保证草稿是**能被校验**的形状，以及每一步都留了证据（提示、事件流、改了哪些文件）。
"""

from __future__ import annotations

import logging
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from backends import Runner
from framework.contracts import packs
from framework.executor import prompting, session
from framework.run.context import strip_frontmatter

LOGGER = logging.getLogger("ai4sci.design")
TEMPLATE = Path(__file__).resolve().parent / "design_prompt.md"
# 协调层写给执行层的产物契约与基线策略；文件名归 contracts（发布签的就是它），这里只是转出
BRIEF_NAME = packs.BRIEF_NAME
# 执行层只许改这两个目录（纲领 packs.md §2：harness 由设计步骤写、之后锁死；code 是唯一可改处）
WRITABLE_DIRS = ("harness", "code")
# lint 规则与 pyproject [tool.ruff] 一致；同一组常数渲染进提示第 7 条，执行层被告知的就是被检查的
LINT_SELECT = "E,F,W,B,I,BLE,UP"
LINT_LINE_LENGTH = 100
# 第二个会话把现状文件贴回去；单个文件超过这个长度就截断（草稿都很短，超了本身就是问题）
FILE_MAX_CHARS = 20_000
LOG_DIR_PREFIX = "design-"


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


def design_task(
    task_dir: Path, domains_root: Path, runner: Runner, log_root: Path, *,
    feedback: str = "", timeout_s: float | None = None,
) -> DesignOutcome:
    """组提示 → 起会话（只放行 harness/ code/）→ 判越界 → 封 harness → ruff → validate。

    validate 这一步不查 run_0：签字前不跑基线。

    `log_root` 下按 `design-<task_id>/executor/session-N/` 留档：提示原文、事件流、stderr。
    `feedback` 非空或磁盘上已有草稿时，提示带上现状文件，让执行层照着改而不是重写。
    """
    task_dir = Path(task_dir).resolve()
    domains_root = Path(domains_root).resolve()
    manifest_text, domain = _read_manifest(task_dir)
    domain_dir = domains_root / domain
    if not (domain_dir / packs.PROFILE_NAME).is_file():
        raise DesignFailed(f"manifest 的 domain {domain!r} 在 {domains_root} 下没有领域包")
    brief_path = task_dir / BRIEF_NAME
    if not brief_path.is_file() or not brief_path.read_text(encoding="utf-8").strip():
        raise DesignFailed(
            f"缺 {task_dir.name}/{BRIEF_NAME}：协调层先写产物契约与基线策略"
            "（code/ 写什么文件、什么形状；evaluate.py 查什么、怎么重算指标；基线用什么策略），"
            "执行层照它写 harness"
        )
    current = _current_files(task_dir)
    values = {
        "manifest": manifest_text.strip(),
        "brief": brief_path.read_text(encoding="utf-8").strip(),
        "skills": _read_skills(domain_dir / "skills"),
        "current": current or "harness/ 与 code/ 还是空的，从零写。",
        "feedback": f"## 这次要改什么\n\n{feedback.strip()}" if feedback.strip() else "",
        "lint_select": LINT_SELECT, "lint_line_length": LINT_LINE_LENGTH,
    }
    prompt = prompting.build_prompt(TEMPLATE, values)

    log_dir, number = _next_session_dir(Path(log_root) / f"{LOG_DIR_PREFIX}{task_dir.name}")
    log_dir.mkdir(parents=True)
    (log_dir / "prompt.md").write_text(prompt, encoding="utf-8")  # 先落盘：会话死了也知道喂了什么
    result = session.run_session(
        runner, prompt, cwd=task_dir,
        allowed_paths=[task_dir / name for name in WRITABLE_DIRS],
        log_dir=log_dir, timeout_s=timeout_s,
    )

    outside = [f for f in result.changed_files
               if not f.startswith(tuple(f"{name}/" for name in WRITABLE_DIRS))]
    if outside:  # 文件留着当证据，不回滚：协调层要看它到底动了什么
        raise DesignFailed(
            f"执行层改了 {' / '.join(WRITABLE_DIRS)} 之外的文件：{', '.join(sorted(outside))}"
        )
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

    sealed = packs.seal_harness(task_dir)
    lint = _ruff(task_dir)
    validate = packs.validate_task(task_dir, domains_root, require_run0=False)
    outcome = DesignOutcome(
        session=number, log_dir=log_dir, changed_files=sorted(result.changed_files),
        cost_usd=result.cost_usd, duration_s=result.duration_s,
        report=session.executor_report(result), sealed=sealed,
        lint_problems=lint, validate_problems=validate,
    )
    LOGGER.info(
        "design_done task=%s session=%d changed=%d sealed=%s lint=%d validate=%d cost_usd=%s",
        task_dir.name, number, len(outcome.changed_files), ",".join(sealed) or "-",
        len(lint), len(validate), result.cost_usd,
    )
    return outcome


def _read_manifest(task_dir: Path) -> tuple[str, str]:
    """manifest 原文（原样贴进提示）与 domain；读不出来在起会话前就停，别花模型的钱。"""
    path = task_dir / packs.MANIFEST_NAME
    if not path.is_file():
        raise DesignFailed(f"缺 {task_dir.name}/{packs.MANIFEST_NAME}：协调层先填任务声明")
    text = path.read_text(encoding="utf-8")
    try:
        raw = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise DesignFailed(f"{packs.MANIFEST_NAME} 不是合法 YAML：{exc}") from exc
    if not isinstance(raw, dict):
        raise DesignFailed(f"{packs.MANIFEST_NAME} 顶层不是映射")
    domain = raw.get("domain", packs.DEFAULT_DOMAIN)
    if not isinstance(domain, str) or not domain:
        raise DesignFailed(f"{packs.MANIFEST_NAME} 的 domain 要是非空字符串，实际 {domain!r}")
    return text, domain


def _read_skills(skills_dir: Path) -> str:
    """领域包全部 skill 正文，去 frontmatter；与 run 快照里的注入同一格式（`### skill: <名>`）。"""
    parts = []
    for skill in sorted(skills_dir.glob("*/SKILL.md")):
        body = strip_frontmatter(skill.read_text(encoding="utf-8")).strip()
        if body:
            parts.append(f"### skill: {skill.parent.name}\n\n{body}")
    return "\n\n".join(parts) or (
        "（这个领域包没有 skill：只用标准库与 env/requirements.lock 里列出的库。）"
    )


def _current_files(task_dir: Path) -> str:
    """磁盘上已有的 harness/ 与 code/ 文件，原样贴回去；SHA256SUMS 是框架的，不给。"""
    blocks = []
    for name in WRITABLE_DIRS:
        for path in sorted((task_dir / name).rglob("*")):
            if not path.is_file() or path.name == "SHA256SUMS" or "__pycache__" in path.parts:
                continue
            text = path.read_text(encoding="utf-8", errors="replace")
            if len(text) > FILE_MAX_CHARS:
                text = text[:FILE_MAX_CHARS] + f"\n…（截断，原文 {len(text)} 字符）\n"
            rel = path.relative_to(task_dir).as_posix()
            lang = {"py": "python", "sh": "bash"}.get(path.suffix.lstrip("."), "")
            blocks.append(f"### {rel}\n\n```{lang}\n{text.rstrip()}\n```")
    if not blocks:
        return ""
    return "下面是现在磁盘上的文件，照它们改，别重写结构：\n\n" + "\n\n".join(blocks)


def _next_session_dir(design_root: Path) -> tuple[Path, int]:
    """`<design_root>/executor/session-N`，N 从 1 起、接着已有的编号；旧会话永远不覆盖。"""
    executor_root = design_root / "executor"
    taken = [int(p.name.split("-", 1)[1]) for p in executor_root.glob("session-*")
             if p.is_dir() and p.name.split("-", 1)[1].isdigit()]
    number = max(taken, default=0) + 1
    return executor_root / f"session-{number}", number


def _ruff(task_dir: Path) -> list[str]:
    """对 harness/ 跑 ruff，一行一条问题。ruff 不在就报错，不静默当作没问题（P-7）。

    `--isolated` 不读任何配置文件：规则由上面的常数定，跟任务包放在哪个目录无关，
    也正是提示第 7 条告诉执行层的那一组。
    """
    hdir = task_dir / "harness"
    if not hdir.is_dir():
        return []
    proc = subprocess.run(
        [sys.executable, "-m", "ruff", "check", "--isolated", "--no-cache",
         "--output-format", "concise", "--select", LINT_SELECT,
         "--line-length", str(LINT_LINE_LENGTH), "harness"],
        cwd=task_dir, capture_output=True, text=True, check=False,
    )
    if proc.returncode not in (0, 1) or "No module named ruff" in proc.stderr:
        raise DesignFailed(
            f"ruff 跑不起来（退出码 {proc.returncode}）："
            f"{proc.stderr.strip().splitlines()[-1:] or '无输出'}；"
            "平台 venv 里要有 ruff（requirements.lock）"
        )
    return [line for line in proc.stdout.splitlines()
            if line.strip() and not line.startswith(("Found ", "[*]", "All checks passed"))]
