"""说清课题：假设阶段里的那颗能力——建任务包目录、搬材料、放模板，然后人和助理在对话里把课题说清。

task 级，不起执行层。为什么要有它（纲领 P-14 CLI 主导封装）：协调 agent 面前只有 `ai4sci`，
没有 mkdir、没有 cp；实验 #59 里它只好把研究者的 8 个数据文件一个个读进上下文再写出来，结果对、
路是歪的。这条命令把"任务包长什么样"收回框架：目录表在纲领 packs §2，模板在这个子包里，agent 只填
内容。

模板里没定的数写「待填」（`packs.PLACEHOLDER`），发布键看到它不给签：模板不能被当成需求签走。
它建的是工作区里的 `task/`，工作区本身由 `ai4sci workspace new` 或页面先起好（纲领 P-15）；
任务包已经在了就拒绝，不覆盖。
"""

from __future__ import annotations

import logging
import shutil
from pathlib import Path

from framework.contracts import env, packs
from framework.contracts.capability import Capability, CapabilityFailed, Param, Ports
from framework.run.workspace import Workspace

LOGGER = logging.getLogger("ai4sci.init")
NAME = "init"
TEMPLATE_DIR = Path(__file__).resolve().parent
# 研究者的文件夹里常混着这些，不是材料
IGNORED = (".git", ".venv", "__pycache__", ".DS_Store", "*.pyc")
DATA_README = (
    "# data/ · 问题定义与输入数据\n\n"
    f"来源与许可：{packs.PLACEHOLDER}（谁给的、从哪下的、什么许可证）。\n\n"
    "这里的东西执行层不许改，评分脚本 evaluate.py 用它重算指标。\n"
)

DESCRIPTOR = Capability(
    name=NAME,
    level="task",
    stage="假设",
    title="说清课题",
    does=(
        "起一个任务包：在工作区里建 task/，研究者给的文件夹整棵搬进 data/（跳过 .git、"
        ".venv 这类），把脚本用的 Python 版本与 pip freeze 写进 env/（之后评分脚本与内环都按它建"
        "环境），manifest.yaml 与 design.md 先放带说明的模板——每个数旁边写着它是什么，"
        "没定的标「待填」。命令跑完，助理在对话里和研究者把课题说清：研究问题、主指标与方向、"
        "预算、统计门、产物契约与「怎么算好」，逐项填进这两个文件。"
    ),
    does_not=(
        "不替研究者定指标与预算，不猜「待填」；不写代码、不跑任何东西；"
        "不发布——需求要研究者自己看过、署名。任务包已经在了就拒绝，不覆盖：改需求直接改文件，"
        "另一份需求另起工作区。"
    ),
    brings=(
        "研究者的材料文件夹（数据、模型定义、现在能跑的脚本）、脚本用的 Python 版本、"
        "pip freeze 出来的锁文件；领域包名（domains/ 下的目录，缺省 generic）。"
    ),
    leaves=(
        "task/manifest.yaml（需求：指标、方向、预算、统计门，先是模板）、"
        "task/design.md（设计说明：四节标题）、task/data/（材料原样 + README 存根）、"
        "task/env/（python-version、requirements.lock）。填完、发布过（publish.json）"
        "的任务包才算这个阶段做完。"
    ),
    stops=(
        "缺 --python 或 --lock、材料文件夹不存在、任务包已在：不建。建好就退出，"
        "结论行说下一步是填两个文件里的「待填」；填得对不对由 ai4sci show task 按契约查。"
    ),
    params=(
        Param("domain", "str", packs.DEFAULT_DOMAIN, "领域包名（domains/ 下的目录）"),
        Param("materials", "str", "", "研究者给的文件夹，整棵搬进 data/；空就只建空目录"),
        Param("python", "str", "", "研究者脚本用的 Python 版本，写进 env/python-version（必填）"),
        Param("lock", "str", "",
              "研究者环境的 pip freeze 文件，复制成 env/requirements.lock（必填）"),
    ),
)


def _render(name: str, fill: dict[str, str]) -> str:
    """模板里的 `{{key}}` 换成值。不用 string.Template：design.md 里有 `$AI4SCI_PYTHON` 这类给
    执行层看的原文，`$` 语法会把它们当占位符。"""
    text = (TEMPLATE_DIR / name).read_text(encoding="utf-8")
    for key, value in fill.items():
        text = text.replace("{{" + key + "}}", value)
    assert "{{" not in text, f"模板 {name} 有没填的占位符"
    return text


def run(workspace: Workspace, ports: Ports, *, domain: str = packs.DEFAULT_DOMAIN,
        materials: str = "", python: str = "", lock: str = "") -> str:
    task_dir = workspace.task
    if task_dir.exists():
        raise CapabilityFailed(
            f"这个工作区已经有任务包了：{task_dir}。改需求直接改它的文件；另一份需求另起一个工作区")
    if not python.strip() or not lock.strip():
        raise CapabilityFailed(
            "要 --python 与 --lock：问研究者脚本用哪个 Python、pip freeze 存在哪个文件")
    lock_path = Path(lock)
    if not lock_path.is_file():
        raise CapabilityFailed(f"--lock 指的文件不存在：{lock_path}")
    source = Path(materials) if materials.strip() else None
    if source is not None and not source.is_dir():
        raise CapabilityFailed(f"--materials 指的文件夹不存在：{source}")

    task_dir.mkdir()
    data = task_dir / "data"
    if source is None:
        data.mkdir()
    else:
        shutil.copytree(source, data, ignore=shutil.ignore_patterns(*IGNORED))
    readme = data / "README.md"
    if not readme.is_file():
        readme.write_text(DATA_README, encoding="utf-8")
    env_dir = task_dir / env.ENV_DIRNAME
    env_dir.mkdir()
    (env_dir / env.PYTHON_VERSION_NAME).write_text(python.strip() + "\n", encoding="utf-8")
    shutil.copyfile(lock_path, env_dir / env.REQUIREMENTS_NAME)
    fill = {"id": workspace.id, "domain": domain, "todo": packs.PLACEHOLDER,
            "source": materials.strip() or packs.PLACEHOLDER}
    for name in (packs.MANIFEST_NAME, packs.BRIEF_NAME):
        (task_dir / name).write_text(_render(name, fill), encoding="utf-8")
    n_files = sum(1 for p in data.rglob("*") if p.is_file())
    LOGGER.info("init_done workspace=%s domain=%s data_files=%d materials=%s",
                workspace.id, domain, n_files, source)
    return (f"ok {workspace.id}\tdomain={domain}\tdata={n_files} 个文件"
            f"\tnext=填 task/{packs.MANIFEST_NAME} 与 task/{packs.BRIEF_NAME} 里的"
            f"「{packs.PLACEHOLDER}」，然后 ai4sci show task")
