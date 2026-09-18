"""起任务包能力：接一个新课题的第一颗按钮——建目录、搬材料、放模板，人和协调 agent 再往里填。

task 级，不起执行层。为什么要有它（纲领 P-14 CLI 主导封装）：协调 agent 面前只有 `ai4sci`，
没有 mkdir、没有 cp；实验 #59 里它只好把研究者的 8 个数据文件一个个读进上下文再写出来，结果对、
路是歪的。按钮把"任务包长什么样"收回框架：目录表在纲领 packs §2，模板在这个子包里，agent 只填内容。

模板里没定的数写「待填」（`packs.PLACEHOLDER`），发布键看到它不给签：模板不能被当成需求签走。
它建的是工作区里的 `task/`，工作区本身由 `ai4sci workspace new` 或页面先起好（纲领 P-15）；
任务包已经在了就拒绝，不覆盖。
"""

from __future__ import annotations

import logging
import shutil
from pathlib import Path

from framework.contracts import env, packs
from framework.contracts.capability import Artifact, Capability, CapabilityFailed, Param, Ports
from framework.run.workspace import Workspace

LOGGER = logging.getLogger("ai4sci.init")
NAME = "init"
TEMPLATE_DIR = Path(__file__).resolve().parent
# 研究者的文件夹里常混着这些，不是材料
IGNORED = (".git", ".venv", "__pycache__", ".DS_Store", "*.pyc")
DATA_README = (
    "# data/ · 问题定义与输入数据\n\n"
    f"来源与许可：{packs.PLACEHOLDER}（谁给的、从哪下的、什么许可证）。\n\n"
    "这里的东西执行层不许改，裁判用它重算指标。\n"
)

DESCRIPTOR = Capability(
    name=NAME,
    level="task",
    summary="起任务包：建目录、材料搬进 data/、写 env/，manifest 与 design.md 先放带说明的模板",
    stage="设计",
    title="起任务包",
    what="把研究者给的文件搬进一个新任务包，需求和设计说明先放好模板，等你和研究者一起填。",
    inputs=(),
    outputs=(
        Artifact("manifest", packs.MANIFEST_NAME,
                 "需求模板：每个数旁边写着它是什么，没定的标「待填」"),
        Artifact("brief", packs.BRIEF_NAME, "设计说明模板：四节标题与每节该写什么"),
        Artifact("data", "data/", "研究者的材料原样搬进来，外加 README 存根"),
        Artifact("env", "env/", "python-version 与 requirements.lock"),
    ),
    params=(
        Param("domain", "str", packs.DEFAULT_DOMAIN, "领域包名（domains/ 下的目录）"),
        Param("materials", "str", "", "研究者给的文件夹，整棵搬进 data/；空就只建空目录"),
        Param("python", "str", "", "研究者脚本用的 Python 版本，写进 env/python-version（必填）"),
        Param("lock", "str", "",
              "研究者环境的 pip freeze 文件，复制成 env/requirements.lock（必填）"),
    ),
    criteria=(
        "目标目录原本不存在，跑完有 manifest.yaml、design.md、data/、env/ 四样",
        "data/ 里的文件与材料逐字节一致",
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
