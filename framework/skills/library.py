"""两处 skill 库的读取点：扫目录、校验 SKILL.md 与脚本、按名字找（纲领 P-22）。

一个 skill 就是一个目录：`SKILL.md`（frontmatter 只有规范的几个字段 + 正文）、可选 `scripts/`
`references/` `assets/`。校验在这里一次做完、问题一次列全（`SkillInvalid`），清单、CLI、注入都从
同一份 `Skill` 出发，不各自读文件。库里有一个坏的就整库报错：agent 拿到一份缺项的清单比拿不到更糟。

名字全局唯一：通用库与各领域包合起来不许重名——`ai4sci skill show <name>` 只认名字。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from framework import paths

SKILL_FILE = "SKILL.md"
SCRIPTS_DIRNAME = "scripts"
REFERENCES_DIRNAME = "references"
LOCK_SUFFIX = ".lock"
GENERIC_LIBRARY = "通用"  # 平台通用库在清单里的名字；领域库用领域包的目录名
# agentskills.io 规范的 frontmatter 字段。不收任何一家 agent 的专有字段：换适配器就失效
SPEC_FIELDS = ("name", "description", "license", "compatibility", "metadata")
REQUIRED_FIELDS = ("name", "description")
NAME_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
NAME_MAX = 64
DESCRIPTION_MAX = 1024
COMPATIBILITY_MAX = 500
BODY_MAX_LINES = 500  # 正文超过就该拆进 references/（规范的 progressive disclosure）
# 我们自己的 metadata 键都带这个前缀；`ai4sci-system-tools` 是 `make skills` 要探测的系统命令
METADATA_PREFIX = "ai4sci-"
SYSTEM_TOOLS_KEY = "ai4sci-system-tools"
PEP723_OPEN = "# /// script"
PEP723_CLOSE = "# ///"


class SkillInvalid(ValueError):
    """一个 skill 目录不合规范：问题一行一条，全列出来。"""


class SkillNotFound(LookupError):
    """要的 skill 不在任何一处库里；信息里带有哪些。"""


@dataclass(frozen=True)
class Skill:
    name: str
    description: str
    dir: Path
    library: str  # 通用，或领域包的名字
    body: str  # SKILL.md 正文（去 frontmatter）
    license: str = ""
    compatibility: str = ""
    metadata: dict[str, str] = field(default_factory=dict)
    scripts: tuple[Path, ...] = ()
    references: tuple[Path, ...] = ()

    @property
    def system_tools(self) -> tuple[str, ...]:
        """metadata 里声明的、uv 装不了的系统命令（空格分隔）；`make skills` 逐个 which。"""
        return tuple(self.metadata.get(SYSTEM_TOOLS_KEY, "").split())


# ── 两处库 ───────────────────────────────────────────────────────────────────
def generic_root() -> Path:
    return paths.skills_root()


def domain_skill_roots(domains_root: Path | None = None) -> list[tuple[str, Path]]:
    """每个领域包的 `skills/`（有才算），按领域名排序。"""
    root = paths.domains_root() if domains_root is None else Path(domains_root)
    return [(d.name, d / "skills") for d in sorted(root.iterdir())
            if d.is_dir() and (d / "skills").is_dir()]


def for_coordinator(generic: Path | None = None) -> list[Skill]:
    """协调层能用的：只有通用库（P-11：领域 skill 只进执行层）。"""
    return scan([(GENERIC_LIBRARY, generic_root() if generic is None else generic)])


def for_executor(domain: str, generic: Path | None = None,
                 domains_root: Path | None = None) -> list[Skill]:
    """执行层能用的：通用库 + 所选领域包的（那个领域没有 skills/ 就只有通用的）。"""
    roots = [(GENERIC_LIBRARY, generic_root() if generic is None else generic)]
    domain_root = (paths.domains_root() if domains_root is None else Path(domains_root)) / domain
    if (domain_root / "skills").is_dir():
        roots.append((domain, domain_root / "skills"))
    return scan(roots)


def all_skills(generic: Path | None = None, domains_root: Path | None = None) -> list[Skill]:
    """两处库全部：`ai4sci skill list / show / run` 按名字找用它。"""
    roots = [(GENERIC_LIBRARY, generic_root() if generic is None else generic),
             *domain_skill_roots(domains_root)]
    return scan(roots)


def find(name: str, generic: Path | None = None, domains_root: Path | None = None) -> Skill:
    skills = all_skills(generic, domains_root)
    for skill in skills:
        if skill.name == name:
            return skill
    available = ", ".join(s.name for s in skills) or "-"
    raise SkillNotFound(f"没有叫 {name!r} 的 skill；有：{available}")


def scan(roots: list[tuple[str, Path]]) -> list[Skill]:
    """扫几处库，每个子目录一个 skill；坏的与重名的合起来一次报完。"""
    skills: list[Skill] = []
    problems: list[str] = []
    seen: dict[str, str] = {}
    for library, root in roots:
        if not root.is_dir():
            continue
        for directory in sorted(p for p in root.iterdir() if p.is_dir()):
            try:
                skill = load_skill(directory, library)
            except SkillInvalid as exc:
                problems.append(str(exc))
                continue
            if skill.name in seen:
                problems.append(f"{directory}: 名字 {skill.name!r} 与 {seen[skill.name]} 重复"
                                "（两处库合起来要唯一）")
                continue
            seen[skill.name] = str(directory)
            skills.append(skill)
    if problems:
        raise SkillInvalid("\n".join(problems))
    return skills


# ── 一个 skill ───────────────────────────────────────────────────────────────
def load_skill(directory: Path, library: str = GENERIC_LIBRARY) -> Skill:
    directory = Path(directory).resolve()
    path = directory / SKILL_FILE
    if not path.is_file():
        raise SkillInvalid(f"{directory}: 没有 {SKILL_FILE}")
    text = path.read_text(encoding="utf-8")
    front, body = split_frontmatter(text)
    problems = _frontmatter_problems(front, directory.name)
    if len(body.splitlines()) > BODY_MAX_LINES:
        problems.append(f"正文 {len(body.splitlines())} 行，超过 {BODY_MAX_LINES}："
                        "细节拆进 references/")
    scripts = tuple(sorted((directory / SCRIPTS_DIRNAME).glob("*.py"))) \
        if (directory / SCRIPTS_DIRNAME).is_dir() else ()
    for script in scripts:
        problems += script_problems(script)
    if problems:
        raise SkillInvalid("\n".join(f"{path}: {p}" for p in problems))
    references = tuple(sorted(p for p in (directory / REFERENCES_DIRNAME).glob("*")
                              if p.is_file()))
    metadata = {str(k): str(v) for k, v in (front.get("metadata") or {}).items()}
    return Skill(
        name=front["name"], description=str(front["description"]).strip(), dir=directory,
        library=library, body=body.strip(), license=str(front.get("license") or "").strip(),
        compatibility=str(front.get("compatibility") or "").strip(), metadata=metadata,
        scripts=scripts, references=references,
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
    problems = [f"frontmatter 缺 {key}" for key in REQUIRED_FIELDS if not front.get(key)]
    extra = sorted(set(front) - set(SPEC_FIELDS))
    if extra:
        problems.append(f"frontmatter 有规范之外的字段 {extra}；只认 {list(SPEC_FIELDS)}"
                        "（自定义的放 metadata 里、键加 ai4sci- 前缀）")
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
    compatibility = front.get("compatibility")
    if compatibility is not None and (not isinstance(compatibility, str)
                                      or len(compatibility) > COMPATIBILITY_MAX):
        problems.append(f"compatibility 要是不超过 {COMPATIBILITY_MAX} 字的一段话")
    license_ = front.get("license")
    if license_ is not None and not isinstance(license_, str):
        problems.append("license 要是一段文字")
    metadata = front.get("metadata")
    if metadata is not None:
        if not isinstance(metadata, dict) or not all(
                isinstance(k, str) and isinstance(v, str) for k, v in metadata.items()):
            problems.append("metadata 要是字符串到字符串的映射")
        else:
            bad = [k for k in metadata
                   if k.startswith("ai4sci") and not k.startswith(METADATA_PREFIX)]
            if bad:
                problems.append(f"metadata 里我们自己的键要带 {METADATA_PREFIX} 前缀：{bad}")
    return problems


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


def lock_path(script: Path) -> Path:
    return script.with_name(script.name + LOCK_SUFFIX)
