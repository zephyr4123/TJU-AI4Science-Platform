"""三处 skill 库的读取点：扫目录、校验 SKILL.md 与脚本、按名字找（纲领 P-22）。

一个 skill 就是一个目录：`SKILL.md`（frontmatter + 正文）、可选 `scripts/` `references/` `assets/`。
三处库，名字合起来唯一（`ai4sci skill show <name>` 只认名字）：

- **平台自带** `skills/<name>/`：常驻，项目里的会话一直装载（纲领 P-26）。
- **收录** `skills-curated/<架>/<name>/`：社区整合包按七个研究阶段加 `general`（通用）分拣进来，
  架就是阶段的 slug；挂到流程实例上才装载。来源与改动记在台账 `provenance.yaml`（`provenance.py`）。
- **领域包** `domains/<包>/skills/<name>/`：挂到流程实例上才装载。

宽进：格式照 agentskills.io，规范外的 frontmatter 字段、超长正文、类型不对的可选字段只记一条提醒
（`Skill.notes`），不拦。不合格的——没有 SKILL.md、frontmatter 坏、缺 name / description、name 与目录
对不上、脚本没有 PEP 723 头或锁文件——隔离出去带原因（`Invalid`），不拖垮别的：装载一个项目时只碰
它要的那几个（`workspace/loadout.py`），整库扫描只在门禁与查库时做；门禁（`make skills`）对出厂的
三处库仍要求全部合格。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from framework import paths
from framework.contracts.stages import STAGE_SLUGS, name_of

SKILL_FILE = "SKILL.md"
SCRIPTS_DIRNAME = "scripts"
REFERENCES_DIRNAME = "references"
LOCK_SUFFIX = ".lock"
RESIDENT = "平台"  # 平台自带的那处库在清单里的名字；收录的叫「收录」；领域库用领域包的目录名
CURATED = "收录"
GENERAL_SHELF = "general"  # 收录库里不属于某个研究阶段的那一架：画图、格式转换这类通用工具
CURATED_SHELVES = (*STAGE_SLUGS, GENERAL_SHELF)
# agentskills.io 规范的 frontmatter 字段（`allowed-tools` 是规范里的实验字段、各家 agent 的权限
# 写法；平台的权限由适配器定，读了也不用，所以和其它规范外的字段一样只提醒）
SPEC_FIELDS = ("name", "description", "license", "compatibility", "metadata")
REQUIRED_FIELDS = ("name", "description")
NAME_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
NAME_MAX = 64
DESCRIPTION_MAX = 1024
COMPATIBILITY_MAX = 500
BODY_MAX_LINES = 500  # 规范的建议：正文超过就该拆进 references/（progressive disclosure）
# 我们自己的 metadata 键都带这个前缀；`ai4sci-system-tools` 是 `make skills` 要探测的系统命令
METADATA_PREFIX = "ai4sci-"
SYSTEM_TOOLS_KEY = "ai4sci-system-tools"
PEP723_OPEN = "# /// script"
PEP723_CLOSE = "# ///"
# 零 key（纲领 P-27）：出厂的三处库里不许出现第三方凭据，门禁逐个文件查。两条：说法（不分大小写）与
# 环境变量名（只认大写，`pad_token` `eos_token` 这类分词器的词不算）
KEY_RE = re.compile(r"api[ _-]?key|access[ _-]?token|auth[ _-]?token|secret[ _-]?key",
                    re.IGNORECASE)
KEY_ENV_RE = re.compile(r"\b[A-Z][A-Z0-9_]*_(?:TOKEN|SECRET|API_KEY)\b")
KEY_SCAN_SUFFIXES = (".md", ".py", ".sh", ".yaml", ".yml", ".json", ".toml", ".txt", ".R", ".r")


class SkillInvalid(ValueError):
    """一个 skill 目录不合规范：问题一行一条，全列出来。"""


class SkillNotFound(LookupError):
    """要的 skill 不在任何一处库里。"""


@dataclass(frozen=True)
class Skill:
    name: str
    description: str
    dir: Path
    library: str  # 平台 / 收录 / 领域包的名字
    body: str  # SKILL.md 正文（去 frontmatter）
    shelf: str = ""  # 收录库的架（阶段 slug 或 general）；另两处库没有架
    license: str = ""
    compatibility: str = ""
    metadata: dict[str, str] = field(default_factory=dict)
    scripts: tuple[Path, ...] = ()
    references: tuple[Path, ...] = ()
    notes: tuple[str, ...] = ()  # 宽进的提醒：规范外的字段、超长正文……不拦，门禁打出来

    @property
    def system_tools(self) -> tuple[str, ...]:
        """metadata 里声明的、uv 装不了的系统命令（空格分隔）；`make skills` 逐个 which。"""
        return tuple(self.metadata.get(SYSTEM_TOOLS_KEY, "").split())

    @property
    def where(self) -> str:
        return where(self.library, self.shelf)

    def files(self) -> list[str]:
        """目录里正文以外的文件（相对路径）：`ai4sci skill show <name> <文件>` 能读的就是这些。
        锁文件是给 uv 的，不列。"""
        return sorted(p.relative_to(self.dir).as_posix() for p in self.dir.rglob("*")
                      if p.is_file() and p.name != SKILL_FILE and not p.name.endswith(LOCK_SUFFIX)
                      and "__pycache__" not in p.parts)

    def read(self, relative: str) -> str:
        """skill 目录里的一个文件；不许跳出目录（`..`、绝对路径、符号链接指到外面都拒）。"""
        target = (self.dir / relative).resolve()
        if not target.is_relative_to(self.dir) or not target.is_file():
            raise SkillNotFound(f"skill {self.name!r} 里没有文件 {relative!r}"
                                f"（有：{', '.join(self.files()) or '-'}）")
        return target.read_text(encoding="utf-8", errors="replace")


@dataclass(frozen=True)
class Invalid:
    """一个不合格的 skill 目录：不装载、不进清单，带着原因留给门禁与查库的人看。"""

    dir: Path
    library: str
    problems: tuple[str, ...]
    shelf: str = ""

    @property
    def name(self) -> str:
        return self.dir.name

    @property
    def where(self) -> str:
        return where(self.library, self.shelf)


@dataclass(frozen=True)
class Scan:
    """扫一遍库的结果：合格的照常用，不合格的带原因隔离在一边。"""

    skills: tuple[Skill, ...]
    invalid: tuple[Invalid, ...]


@dataclass(frozen=True)
class Root:
    """一处库（或收录库的一架）：名字、架、目录。"""

    library: str
    path: Path
    shelf: str = ""


def where(library: str, shelf: str) -> str:
    """给人看的出处：平台 / 收录·文献 / 收录·通用 / 领域包名。"""
    if library != CURATED:
        return library
    return f"{CURATED}·{'通用' if shelf == GENERAL_SHELF else name_of(shelf)}"


def shelf_of(text: str) -> str:
    """阶段名、slug 或「通用」→ 架；认不出就炸（调用方先给用户说清有哪些）。"""
    if text in ("通用", GENERAL_SHELF):
        return GENERAL_SHELF
    if text in CURATED_SHELVES:
        return text
    for slug in STAGE_SLUGS:
        if name_of(slug) == text:
            return slug
    raise ValueError(f"不是阶段：{text!r}（七个阶段的名字，或「通用」）")


# ── 三处库 ───────────────────────────────────────────────────────────────────
def roots(domains_root: Path | None = None) -> list[Root]:
    """全部库，按「平台 → 收录各架（阶段序，最后通用）→ 领域包（按名）」排；不存在的架跳过。"""
    curated = paths.curated_skills_root()
    out = [Root(RESIDENT, paths.skills_root())]
    out += [Root(CURATED, curated / shelf, shelf) for shelf in CURATED_SHELVES
            if (curated / shelf).is_dir()]
    root = paths.domains_root() if domains_root is None else Path(domains_root)
    out += [Root(d.name, d / "skills") for d in sorted(root.iterdir())
            if d.is_dir() and (d / "skills").is_dir()]
    return out


def resident() -> Scan:
    """平台自带的：常驻（纲领 P-26）。"""
    return scan([Root(RESIDENT, paths.skills_root())])


def everything(domains_root: Path | None = None) -> Scan:
    """三处库全部：门禁、查库（`ai4sci show skills`）、页面的能力库用它。"""
    return scan(roots(domains_root))


def names(domains_root: Path | None = None) -> frozenset[str]:
    """三处库里有哪些 skill 的名字：只看目录名、不解析（合格不合格都算）。流程里挂的名字是不是
    skill 看目录在不在——每条 `cap` / `show flows` 都要问，几百个 SKILL.md 不能每次都读一遍。"""
    return frozenset(d.name for root in roots(domains_root) if root.path.is_dir()
                     for d in root.path.iterdir() if d.is_dir())


def find(name: str, domains_root: Path | None = None) -> Skill:
    """按名字找一个：只看目录名，不扫全库；不合格就带原因抛 SkillInvalid，重名也抛。"""
    hits = [(root, root.path / name) for root in roots(domains_root)
            if (root.path / name).is_dir()]
    if not hits:
        raise SkillNotFound(f"没有叫 {name!r} 的 skill（ai4sci show skills <词> 查库）")
    if len(hits) > 1:
        raise SkillInvalid(f"skill {name!r} 重名：" + "、".join(str(d) for _, d in hits)
                           + "（三处库合起来要唯一）")
    root, directory = hits[0]
    return load_skill(directory, root.library, root.shelf)


def scan(found_roots: list[Root]) -> Scan:
    """扫几处库，每个子目录一个 skill；坏的与重名的（后到的那个）隔离出去带原因，不抛。"""
    skills: list[Skill] = []
    invalid: list[Invalid] = []
    seen: dict[str, Path] = {}
    for root in found_roots:
        if not root.path.is_dir():
            continue
        for directory in sorted(p for p in root.path.iterdir() if p.is_dir()):
            if directory.name in seen:
                clash = f"名字与 {seen[directory.name]} 重复（三处库合起来要唯一）"
                invalid.append(Invalid(directory, root.library, (clash,), root.shelf))
                continue
            seen[directory.name] = directory
            try:
                skills.append(load_skill(directory, root.library, root.shelf))
            except SkillInvalid as exc:
                invalid.append(Invalid(directory, root.library, tuple(str(exc).splitlines()),
                                       root.shelf))
    return Scan(tuple(skills), tuple(invalid))


# ── 一个 skill ───────────────────────────────────────────────────────────────
def load_skill(directory: Path, library: str = RESIDENT, shelf: str = "") -> Skill:
    directory = Path(directory).resolve()
    path = directory / SKILL_FILE
    if not path.is_file():
        raise SkillInvalid(f"{directory}: 没有 {SKILL_FILE}")
    try:
        front, body = split_frontmatter(path.read_text(encoding="utf-8"))
    except SkillInvalid as exc:
        raise SkillInvalid(f"{path}: {exc}") from exc
    problems = _frontmatter_problems(front, directory.name)
    scripts = tuple(sorted((directory / SCRIPTS_DIRNAME).glob("*.py"))) \
        if (directory / SCRIPTS_DIRNAME).is_dir() else ()
    for script in scripts:
        problems += script_problems(script)
    if problems:
        raise SkillInvalid("\n".join(f"{path}: {p}" for p in problems))
    notes = _frontmatter_notes(front)
    if len(body.splitlines()) > BODY_MAX_LINES:
        notes.append(f"正文 {len(body.splitlines())} 行，规范建议 {BODY_MAX_LINES} 行以内")
    references = tuple(sorted(p for p in (directory / REFERENCES_DIRNAME).glob("*")
                              if p.is_file()))
    raw_meta = front.get("metadata")
    metadata = ({str(k): v for k, v in raw_meta.items() if isinstance(v, str)}
                if isinstance(raw_meta, dict) else {})
    license_, compatibility = front.get("license"), front.get("compatibility")
    return Skill(
        name=front["name"], description=str(front["description"]).strip(), dir=directory,
        library=library, shelf=shelf, body=body.strip(),
        license=license_.strip() if isinstance(license_, str) else "",
        compatibility=compatibility.strip() if isinstance(compatibility, str) else "",
        metadata=metadata, scripts=scripts, references=references, notes=tuple(notes),
    )


def split_frontmatter(text: str) -> tuple[dict, str]:
    """`---` 块解析成字典，其余是正文。没有 frontmatter 就是空字典（校验会报缺 name）。"""
    if not text.startswith("---"):
        return {}, text
    end = text.find("\n---", 3)
    if end == -1:
        raise SkillInvalid("frontmatter 没有结尾的 ---")
    try:
        front = yaml.safe_load(text[3:end]) or {}
    except yaml.YAMLError as exc:
        raise SkillInvalid(f"frontmatter 不是合法 YAML：{exc}") from exc
    if not isinstance(front, dict):
        raise SkillInvalid("frontmatter 要是键值对")
    return front, text[end + 4:]


def _frontmatter_problems(front: dict, dirname: str) -> list[str]:
    """拦下的：没有它们 agent 认不出、叫不到这个 skill。"""
    problems = [f"frontmatter 缺 {key}" for key in REQUIRED_FIELDS if not front.get(key)]
    name = front.get("name")
    if name is not None:
        if not isinstance(name, str) or not NAME_RE.match(name) or len(name) > NAME_MAX:
            problems.append(f"name {name!r} 要是小写字母数字连字符、不超过 {NAME_MAX} 字")
        elif name != dirname:
            problems.append(f"name {name!r} 与目录名 {dirname!r} 不一致")
    description = front.get("description")
    if description is not None:
        if not isinstance(description, str) or not description.strip():
            problems.append("description 要是一句非空的话")
        elif len(description) > DESCRIPTION_MAX:
            problems.append(f"description {len(description)} 字，超过 {DESCRIPTION_MAX}")
    return problems


def _frontmatter_notes(front: dict) -> list[str]:
    """只提醒的：规范外的字段、类型不对的可选字段（读不了就不读）。"""
    notes: list[str] = []
    extra = sorted(set(front) - set(SPEC_FIELDS))
    if extra:
        notes.append(f"frontmatter 有规范之外的字段 {extra}，不读")
    if "license" in front and not isinstance(front["license"], str):
        notes.append("license 不是一段文字，不读")
    compatibility = front.get("compatibility")
    if compatibility is not None and (not isinstance(compatibility, str)
                                      or len(compatibility) > COMPATIBILITY_MAX):
        notes.append(f"compatibility 不是 {COMPATIBILITY_MAX} 字以内的一段话，不读")
    metadata = front.get("metadata")
    if metadata is not None:
        if not isinstance(metadata, dict):
            notes.append("metadata 不是映射，不读")
        else:
            nested = sorted(str(k) for k, v in metadata.items() if not isinstance(v, str))
            if nested:
                notes.append(f"metadata 里 {nested} 的值不是字符串，不读")
            bad = sorted(str(k) for k in metadata
                         if str(k).startswith("ai4sci") and not str(k).startswith(METADATA_PREFIX))
            if bad:
                notes.append(f"metadata 里我们自己的键要带 {METADATA_PREFIX} 前缀：{bad}")
    return notes


def script_problems(script: Path) -> list[str]:
    """一个脚本的两条门禁：头部有 PEP 723 块、旁边有 `uv lock --script` 出的锁文件。"""
    problems: list[str] = []
    head = script.read_text(encoding="utf-8")
    if PEP723_OPEN not in head or PEP723_CLOSE not in head.split(PEP723_OPEN, 1)[-1]:
        problems.append(f"{script.name} 头部没有 PEP 723 块（# /// script … # ///）："
                        "用 uv add --script 写依赖")
    if not lock_path(script).is_file():
        problems.append(f"{script.name} 旁边没有锁文件 {lock_path(script).name}："
                        f"uv lock --script {script.name}")
    return problems


def key_mentions(skill: Skill) -> list[str]:
    """零 key（纲领 P-27）：skill 目录里提到第三方凭据的地方，一处一行 `文件:行`。"""
    hits: list[str] = []
    for path in sorted(p for p in skill.dir.rglob("*") if p.is_file()):
        if path.suffix not in KEY_SCAN_SUFFIXES and path.name != SKILL_FILE:
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        for number, line in enumerate(text.splitlines(), 1):
            if KEY_RE.search(line) or KEY_ENV_RE.search(line):
                hits.append(f"{path.relative_to(skill.dir)}:{number}: {line.strip()[:120]}")
    return hits


def lock_path(script: Path) -> Path:
    return script.with_name(script.name + LOCK_SUFFIX)
