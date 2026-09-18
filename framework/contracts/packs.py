"""任务包的发现与校验。

在四层的最底层 contracts：本模块不 import framework 的任何其它包，也不知道 run 与
能力的存在——它只回答"这个包合不合约"。

为什么在 framework/ 而不是跟任务走：契约校验是框架的活，删掉全部 `tasks/` 与
`domains/` 之后本模块的测试也要照过（纲领 P-5）。所以这里不 import 任何任务包的
东西，任务目录、领域目录一律由调用方以参数传入。

为什么 `validate_task` 返回清单而不是抛异常：它的产物是给人看的问题列表，一次要把
所有毛病都摊出来，中途抛栈只能报第一个。程序自身的缺陷（比如 schema 文件读不出来）
仍然照抛不误——不吞异常这条红线管的是失败被无声吃掉，不是把用户输入错误包装成人话。
"""

from __future__ import annotations

import ast
import hashlib
import json
import math
import re
from pathlib import Path
from typing import Any

import jsonschema
import yaml

from framework.contracts.env import GUARANTEED_ENV, read_env

SCHEMA_DIR = Path(__file__).resolve().parent / "schemas"
MANIFEST_NAME = "manifest.yaml"
# 协调层写给执行层的产物契约与基线策略（"怎么算好"的人话版），放任务根：它和 manifest 一起
# 就是需求看板上的东西，发布签的就是这两个文件（contracts/publish.py）
BRIEF_NAME = "design.md"
# `cap init` 的模板里没定的值都写它；发布前看到它就不给签，模板不能被当成需求签走
PLACEHOLDER = "待填"
PROFILE_NAME = "profile.yaml"

# manifest 不写 domain 时的兜底领域（packs.md §2）。
DEFAULT_DOMAIN = "generic"
# harness/ 里框架强制要有的三个文件（packs.md §2）。
HARNESS_REQUIRED = ("launcher.sh", "evaluate.py", "SHA256SUMS")
# 超预算多少倍算跑飞（workflow.md §2：超时 1.5 倍必杀）。
BUDGET_OVERRUN_RATIO = 1.5
# 框架认得的任务包契约版本；改契约时加新版本、写迁移，不直接把旧版本判死（红线 6）。
SUPPORTED_FORMAT_VERSIONS = (1,)
# harness 脚本里的裸 python 命令：任务必须跑在自己的 venv 里，
# 只准经 $AI4SCI_PYTHON 起解释器（packs.md §2）。
_BARE_PYTHON_RE = re.compile(r"(?<![\w/.$\"'-])python3?(?:\.\d+)?(?=\s|$|[;)|&])")
# launcher.sh 里给保证变量写默认值：${AI4SCI_INNER_K:-3} / ${AI4SCI_BUDGET_S-30} 这类展开。
# make_run0.sh 不查：它是人手工起的入口，给 AI4SCI_PYTHON 一个指向任务自己 .venv 的默认值是约定
_ENV_DEFAULT_RE = re.compile(r"\$\{(" + "|".join(GUARANTEED_ENV) + r")(?::?-|:?=)")

_SCHEMA_CACHE: dict[str, dict[str, Any]] = {}


# --------------------------------------------------------------------------
# 小工具
# --------------------------------------------------------------------------
def _load_schema(name: str) -> dict[str, Any]:
    """读 framework/contracts/schemas/<name>；读不出来是框架自己坏了，直接抛。"""
    if name not in _SCHEMA_CACHE:
        with (SCHEMA_DIR / name).open(encoding="utf-8") as fh:
            _SCHEMA_CACHE[name] = json.load(fh)
    return _SCHEMA_CACHE[name]


def _one_line(exc: BaseException) -> str:
    """把多行异常信息压成一行，问题清单是一行一条。"""
    return " ".join(str(exc).split())


def _reject_constant(token: str) -> float:
    """json 模块默认认 NaN / Infinity / -Infinity，这里把它们打回去。

    为什么不靠 schema：schema 只能约束"是数字"，而 float('nan') 在 Python 里就是数字，
    NaN 会一路飘到比较逻辑里变成永远为假的比较（workflow.md §2 的失败分类第五类）。
    """
    raise ValueError(f"不合法的 JSON 常量 {token}（NaN / Infinity 不允许出现在指标里）")


def _read_json(path: Path, label: str) -> tuple[Any, list[str]]:
    """读 JSON；文件缺失与语法错都变成问题项。"""
    if not path.is_file():
        return None, [f"{label}: 文件缺失，期望存在 {path}"]
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        return None, [f"{label}: 读不出来：{_one_line(exc)}"]
    try:
        return json.loads(text, parse_constant=_reject_constant), []
    except ValueError as exc:  # JSONDecodeError 是 ValueError 的子类，NaN 也走这里
        return None, [f"{label}: JSON 解析失败：{_one_line(exc)}"]


def _schema_problems(data: Any, schema_name: str, label: str) -> list[str]:
    """跑 JSON Schema，把每条 error 变成一行带定位的问题。"""
    validator = jsonschema.Draft202012Validator(_load_schema(schema_name))
    problems = []
    for err in sorted(validator.iter_errors(data), key=lambda e: list(e.absolute_path)):
        loc = "/".join(str(p) for p in err.absolute_path) or "<顶层>"
        problems.append(f"{label}: 字段 {loc}: {_one_line(err.message)}")
    return problems


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def task_id_of(task_dir: Path) -> str:
    """任务包的 id 就是它所在工作区的名字：包住在 `workspaces/<id>/task/`（纲领 P-15）。"""
    return Path(task_dir).resolve().parent.name


def intake_problems(task_dir: Path) -> list[str]:
    """需求看板发布前要过的最小检查：manifest 合 schema、design.md 在且非空。

    比 `validate_task` 早得多：此时 harness/ code/ run_0/ 都还没有，那些是发布**之后**
    能力产出的东西。这里只管人和 agent 聊出来的两个文件。
    """
    task_dir = Path(task_dir)
    _, problems = _check_manifest(task_dir)
    brief = task_dir / BRIEF_NAME
    if not brief.is_file() or not brief.read_text(encoding="utf-8").strip():
        problems.append(
            f"{task_dir.name}/{BRIEF_NAME}: 缺失或为空，需求看板要先写清产物契约与"
            "「怎么算好」（code/ 写什么文件、evaluate.py 查什么与怎么重算指标、基线策略）"
        )
    for name in (MANIFEST_NAME, BRIEF_NAME):
        path = task_dir / name
        if path.is_file() and PLACEHOLDER in path.read_text(encoding="utf-8"):
            problems.append(
                f"{task_dir.name}/{name}: 还有「{PLACEHOLDER}」没填，模板不能当需求发布")
    return problems


# --------------------------------------------------------------------------
# 逐条校验：每条一个小函数，manifest 读不出来时后续检查各自安全退场
# --------------------------------------------------------------------------
def _check_manifest(task_dir: Path) -> tuple[dict[str, Any] | None, list[str]]:
    """schema 校验，外加两条 JSON Schema 表达不了的：id 等于工作区名、恰好一个 primary。"""
    label = f"{task_dir.name}/{MANIFEST_NAME}"
    path = task_dir / MANIFEST_NAME
    if not path.is_file():
        return None, [f"{label}: 文件缺失，任务包必须有 {MANIFEST_NAME}（期望 {path}）"]
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        return None, [f"{label}: YAML 语法错误：{_one_line(exc)}"]
    if not isinstance(raw, dict):
        return None, [f"{label}: 字段 <顶层>: 期望映射（mapping），实际 {type(raw).__name__}"]

    problems = _schema_problems(raw, "manifest.schema.json", label)

    version = raw.get("format_version")
    if isinstance(version, int) and version not in SUPPORTED_FORMAT_VERSIONS:
        problems.append(
            f"{label}: 字段 format_version: 本框架只认 {SUPPORTED_FORMAT_VERSIONS}，实际 {version}"
        )

    task_id = raw.get("id")
    if isinstance(task_id, str) and task_id != task_id_of(task_dir):
        problems.append(
            f"{label}: 字段 id: 期望等于工作区名 {task_id_of(task_dir)!r}，实际 {task_id!r}"
        )

    metrics = raw.get("metrics")
    if isinstance(metrics, list):
        entries = [m for m in metrics if isinstance(m, dict)]
        primaries = [m.get("name") for m in entries if m.get("primary") is True]
        if len(primaries) != 1:
            problems.append(
                f"{label}: 字段 metrics: 期望恰好 1 个 primary 指标，"
                f"实际 {len(primaries)} 个（{primaries}）"
            )
        names = [m.get("name") for m in entries]
        dupes = sorted({n for n in names if names.count(n) > 1})
        if dupes:
            problems.append(f"{label}: 字段 metrics: 指标名重复：{dupes}")

    requirements = raw.get("requirements")
    if isinstance(requirements, list):
        ids = [r.get("id") for r in requirements if isinstance(r, dict)]
        dupes = sorted({i for i in ids if ids.count(i) > 1})
        if dupes:
            problems.append(f"{label}: 字段 requirements: 验收条件 id 重复：{dupes}")

    return raw, problems


def _check_domain(manifest: dict[str, Any] | None, task_dir: Path, domains_root: Path) -> list[str]:
    """domain 的读取点：manifest 不写就落到 generic，落到哪个都必须有 profile.yaml。"""
    if manifest is None:
        return []
    label = f"{task_dir.name}/{MANIFEST_NAME}"
    domain = manifest.get("domain", DEFAULT_DOMAIN)
    if not isinstance(domain, str) or not domain:
        return [f"{label}: 字段 domain: 期望非空字符串，实际 {domain!r}"]
    profile = Path(domains_root) / domain / PROFILE_NAME
    if not profile.is_file():
        return [f"{label}: 字段 domain: 领域包 {domain!r} 不存在，期望文件 {profile}"]
    return []


def _check_env(task_dir: Path) -> list[str]:
    """env/ 的读取点在 contracts.env；这里只把它的问题清单并进来。"""
    _, problems = read_env(task_dir)
    return problems


def _bare_python_lines(script: Path) -> list[int]:
    """脚本里裸调 python / python3 的行号；注释行不算。"""
    hits = []
    for lineno, line in enumerate(script.read_text(encoding="utf-8").splitlines(), start=1):
        if line.lstrip().startswith("#"):
            continue
        if _BARE_PYTHON_RE.search(line):
            hits.append(lineno)
    return hits


def _env_default_lines(script: Path) -> list[tuple[int, str]]:
    """harness 的 Python 里给保证变量写默认值的位置：`environ.get(NAME, x)` / `getenv(NAME, x)`。

    只认这两种直接写法，且只认 GUARANTEED_ENV 里的名字：这是裁判文件的安检，不是通用静态警察，
    范围收到"框架保证会给、拿不到必须停"的那几个变量。读不出 AST 的文件不在这里报——语法错
    lint 会报。
    """
    try:
        tree = ast.parse(script.read_text(encoding="utf-8"), filename=str(script))
    except SyntaxError:
        return []
    hits: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or len(node.args) < 2:
            continue
        func = node.func
        if not isinstance(func, ast.Attribute) or func.attr not in ("get", "getenv"):
            continue
        first = node.args[0]
        if isinstance(first, ast.Constant) and first.value in GUARANTEED_ENV:
            hits.append((node.lineno, first.value))
    return hits


def _check_harness(task_dir: Path) -> list[str]:
    """harness 三件套齐全，且 SHA256SUMS 与磁盘一致——它是「评测没被改」的唯一证据。"""
    hdir = task_dir / "harness"
    if not hdir.is_dir():
        return [f"harness/: 目录缺失，期望 {hdir}"]

    problems = [
        f"harness/{name}: 文件缺失，期望 {hdir / name}"
        for name in HARNESS_REQUIRED
        if not (hdir / name).is_file()
    ]
    for script in sorted(hdir.glob("*.sh")):
        for lineno in _bare_python_lines(script):
            problems.append(
                f"harness/{script.name}:{lineno}: 裸调 python，任务必须跑在自己的 venv 里，"
                f"期望经 \"$AI4SCI_PYTHON\" 起解释器"
            )
    launcher = hdir / "launcher.sh"
    if launcher.is_file():
        for lineno, line in enumerate(launcher.read_text(encoding="utf-8").splitlines(), 1):
            if (m := _ENV_DEFAULT_RE.search(line)) and not line.lstrip().startswith("#"):
                problems.append(
                    f"harness/launcher.sh:{lineno}: 给 {m.group(1)} 写了默认值；"
                    "框架保证给出这个变量，拿不到必须停（用 ${VAR:?}），不许自己兜底"
                )
    for script in sorted(hdir.glob("*.py")):
        for lineno, name in _env_default_lines(script):
            problems.append(
                f"harness/{script.name}:{lineno}: 给 {name} 写了默认值；"
                "框架保证给出这个变量，拿不到必须退非零，不许自己兜底"
            )

    sums_path = hdir / "SHA256SUMS"
    if not sums_path.is_file():
        return problems

    listed: set[str] = set()
    for lineno, line in enumerate(sums_path.read_text(encoding="utf-8").splitlines(), start=1):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        parts = stripped.split(None, 1)
        if len(parts) != 2 or len(parts[0]) != 64:
            problems.append(
                f"harness/SHA256SUMS:{lineno}: 期望格式 '<64 位 sha256>  <文件名>'，"
                f"实际 {stripped!r}"
            )
            continue
        expected, name = parts[0].lower(), parts[1].lstrip("*").strip()
        if name.startswith("/") or ".." in Path(name).parts:
            problems.append(f"harness/SHA256SUMS:{lineno}: 文件名越界，实际 {name!r}")
            continue
        target = hdir / name
        if not target.is_file():
            problems.append(f"harness/SHA256SUMS:{lineno}: 登记的 {name} 不存在，期望 {target}")
            continue
        listed.add(name)
        actual = _sha256(target)
        if actual != expected:
            problems.append(
                f"harness/{name}: sha256 不一致，期望 {expected}，实际 {actual}"
            )

    for name in ("launcher.sh", "evaluate.py"):
        if (hdir / name).is_file() and name not in listed:
            problems.append(
                f"harness/SHA256SUMS: 未登记 {name}，harness 下每个可执行文件都要能对账"
            )
    return problems


def _check_code(task_dir: Path) -> list[str]:
    """code/ 是执行层唯一能改的地方，空的等于没基线。"""
    cdir = task_dir / "code"
    if not cdir.is_dir():
        return [f"code/: 目录缺失，期望 {cdir}"]
    if not any(p.is_file() for p in cdir.rglob("*")):
        return [f"code/: 目录为空，期望至少有一个基线文件（{cdir}）"]
    return []


def _check_budget(manifest: dict[str, Any] | None, task_dir: Path) -> list[str]:
    """budget 四个字段的断言点。

    wall_clock_s 与 repeat_k 在 _check_run0 里有硬读取点（比 elapsed、数 repeats）；
    max_iterations 与 accept_sigma 的消费者是实验内环（workflow.md §2 的轮数上限与统计
    门），本轮内环还没落地，所以这里先给出取值断言，保证协调层填的值到内环时是可用的。
    """
    if manifest is None:
        return []
    label = f"{task_dir.name}/{MANIFEST_NAME}"
    budget = manifest.get("budget")
    if not isinstance(budget, dict):
        return []  # schema 已经报过了
    problems = []
    wall = budget.get("wall_clock_s")
    if isinstance(wall, (int, float)) and not math.isfinite(wall):
        problems.append(f"{label}: 字段 budget/wall_clock_s: 期望有限数，实际 {wall!r}")
    accept_sigma = budget.get("accept_sigma")
    if isinstance(accept_sigma, (int, float)) and not math.isfinite(accept_sigma):
        problems.append(f"{label}: 字段 budget/accept_sigma: 期望有限数，实际 {accept_sigma!r}")
    return problems


def _metric_names(manifest: dict[str, Any] | None) -> list[str]:
    metrics = manifest.get("metrics") if isinstance(manifest, dict) else None
    if not isinstance(metrics, list):
        return []
    return [m["name"] for m in metrics if isinstance(m, dict) and isinstance(m.get("name"), str)]


def _check_results_doc(
    path: Path, label: str, metric_names: list[str], wall_clock_s: float | None
) -> tuple[dict[str, Any] | None, list[str]]:
    """一份 results.json：schema、指标齐全、指标有限、elapsed 没超预算。"""
    doc, problems = _read_json(path, label)
    if doc is None:
        return None, problems
    problems += _schema_problems(doc, "results.schema.json", label)
    if not isinstance(doc, dict):
        return None, problems

    metrics = doc.get("metrics")
    if isinstance(metrics, dict):
        missing = [n for n in metric_names if n not in metrics]
        if missing:
            problems.append(
                f"{label}: 字段 metrics: 缺少 manifest 声明的指标 {missing}，"
                f"实际有 {sorted(metrics)}"
            )
        for name, value in sorted(metrics.items()):
            if isinstance(value, (int, float)) and not math.isfinite(value):
                problems.append(f"{label}: 字段 metrics/{name}: 期望有限数，实际 {value!r}")

    elapsed = doc.get("elapsed_s")
    if isinstance(elapsed, (int, float)) and isinstance(wall_clock_s, (int, float)):
        limit = wall_clock_s * BUDGET_OVERRUN_RATIO
        if elapsed > limit:
            problems.append(
                f"{label}: 字段 elapsed_s: 超预算，期望不超过 wall_clock_s×"
                f"{BUDGET_OVERRUN_RATIO}={limit:g}s，实际 {elapsed:g}s"
            )
    return doc, problems


def _check_run0(manifest: dict[str, Any] | None, task_dir: Path) -> list[str]:
    """run_0 是改进率的分母，也是统计门的基线：基线一次 + repeat_k 次重复 + σ。"""
    run0 = task_dir / "run_0"
    if not run0.is_dir():
        return [f"run_0/: 目录缺失，期望 {run0}（基线跑一次的产物）"]

    metric_names = _metric_names(manifest)
    budget = manifest.get("budget") if isinstance(manifest, dict) else None
    budget = budget if isinstance(budget, dict) else {}
    wall_clock_s = budget.get("wall_clock_s")
    wall_clock_s = wall_clock_s if isinstance(wall_clock_s, (int, float)) else None
    repeat_k = budget.get("repeat_k")

    problems: list[str] = []
    _, base_problems = _check_results_doc(
        run0 / "results.json", "run_0/results.json", metric_names, wall_clock_s
    )
    problems += base_problems

    # repeats：文件数必须恰好等于 repeat_k，文件名里的 seed 必须与文件内的 seed 一致
    repeats_dir = run0 / "repeats"
    seen_seeds: list[int] = []
    if not repeats_dir.is_dir():
        problems.append(f"run_0/repeats/: 目录缺失，期望 {repeats_dir}（统计门的重复跑）")
    else:
        repeat_files = sorted(repeats_dir.glob("results-*.json"))
        if isinstance(repeat_k, int) and len(repeat_files) != repeat_k:
            problems.append(
                f"run_0/repeats/: 期望恰好 budget.repeat_k={repeat_k} 个 results-<seed>.json，"
                f"实际 {len(repeat_files)} 个（{[p.name for p in repeat_files]}）"
            )
        for path in repeat_files:
            label = f"run_0/repeats/{path.name}"
            doc, doc_problems = _check_results_doc(path, label, metric_names, wall_clock_s)
            problems += doc_problems
            stem_seed = path.stem[len("results-") :]
            try:
                file_seed = int(stem_seed)
            except ValueError:
                problems.append(f"{label}: 文件名里的 seed 不是整数，实际 {stem_seed!r}")
                continue
            seen_seeds.append(file_seed)
            if isinstance(doc, dict) and doc.get("seed") != file_seed:
                problems.append(
                    f"{label}: 字段 seed: 期望与文件名一致 {file_seed}，实际 {doc.get('seed')!r}"
                )

    problems += _check_sigma(run0, metric_names, sorted(seen_seeds))
    return problems


def _check_sigma(run0: Path, metric_names: list[str], repeat_seeds: list[int]) -> list[str]:
    """σ 是统计门的分母：每个指标一条，seeds 必须与 repeats 目录对得上。"""
    label = "run_0/sigma.json"
    doc, problems = _read_json(run0 / "sigma.json", label)
    if doc is None:
        return problems
    if not isinstance(doc, dict):
        return problems + [f"{label}: 字段 <顶层>: 期望映射，实际 {type(doc).__name__}"]

    for name in metric_names:
        entry = doc.get(name)
        if not isinstance(entry, dict):
            problems.append(f"{label}: 字段 {name}: 缺失或不是映射，实际 {entry!r}")
            continue
        sigma = entry.get("sigma")
        if not isinstance(sigma, (int, float)) or isinstance(sigma, bool):
            problems.append(f"{label}: 字段 {name}/sigma: 期望数字，实际 {sigma!r}")
        elif not math.isfinite(sigma) or sigma < 0:
            problems.append(f"{label}: 字段 {name}/sigma: 期望有限且 >=0，实际 {sigma!r}")
        seeds = entry.get("seeds")
        values = entry.get("values")
        if not isinstance(seeds, list) or not all(isinstance(s, int) for s in seeds):
            problems.append(f"{label}: 字段 {name}/seeds: 期望整数数组，实际 {seeds!r}")
        elif sorted(seeds) != repeat_seeds:
            problems.append(
                f"{label}: 字段 {name}/seeds: 与 run_0/repeats/ 对不上，"
                f"期望 {repeat_seeds}，实际 {sorted(seeds)}"
            )
        if not isinstance(values, list):
            problems.append(f"{label}: 字段 {name}/values: 期望数组，实际 {values!r}")
        elif isinstance(seeds, list) and len(values) != len(seeds):
            problems.append(
                f"{label}: 字段 {name}/values: 长度应与 seeds 一致，"
                f"期望 {len(seeds)}，实际 {len(values)}"
            )
        elif not all(
            isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)
            for v in values
        ):
            problems.append(f"{label}: 字段 {name}/values: 期望全是有限数，实际 {values!r}")
    return problems


def validate_task(
    task_dir: Path, domains_root: Path, *, require_run0: bool = True
) -> list[str]:
    """校验一个任务包，返回问题清单；空清单表示通过。

    每条问题都要能定位：文件（必要时带行号）、字段、期望 vs 实际。

    `require_run0=False` 是设计步骤的读取点：执行层刚写完草稿、人还没签 `evaluate.py`，
    基线不该跑（签字前不跑基线），这时只查 run_0 之外的一切。开跑（`run new`）永远查全。
    """
    task_dir = Path(task_dir)
    if not task_dir.is_dir():
        return [f"{task_dir}: 任务目录不存在"]

    manifest, problems = _check_manifest(task_dir)
    problems += _check_domain(manifest, task_dir, Path(domains_root))
    problems += _check_budget(manifest, task_dir)
    problems += _check_env(task_dir)
    problems += _check_harness(task_dir)
    problems += _check_code(task_dir)
    if require_run0:
        problems += _check_run0(manifest, task_dir)
    return problems


def seal_harness(task_dir: Path) -> list[str]:
    """给 harness/ 上锁：`*.sh` 加执行位，除 SHA256SUMS 外每个文件登记进 SHA256SUMS。

    返回登记的文件名。

    执行层的隔离会话没有 Bash，做不了这两步（第一个真任务时靠协调层手敲，漏过 chmod）；
    由框架做也正好把"校验和是谁算的"这个信任点收回框架：登记的是框架看到的文件，不是谁
    自报的。harness/ 不存在就返回空清单，让 validate 去报"目录缺失"，这里不替它说话。
    """
    hdir = Path(task_dir) / "harness"
    if not hdir.is_dir():
        return []
    names: list[str] = []
    for path in sorted(hdir.iterdir()):
        if not path.is_file() or path.name == "SHA256SUMS":
            continue
        if path.suffix == ".sh":
            path.chmod(path.stat().st_mode | 0o111)
        names.append(path.name)
    lines = [f"{_sha256(hdir / name)}  {name}" for name in names]
    (hdir / "SHA256SUMS").write_text("".join(f"{line}\n" for line in lines), encoding="utf-8")
    return names
