"""起任务包能力（外层 #60，纲领 P-14）：搬材料、放模板、拒绝覆盖；模板里的「待填」拦住发布键。"""

from __future__ import annotations

from pathlib import Path

import pytest

from framework.capabilities import discover
from framework.capabilities import init as cap_init
from framework.contracts import env, packs, publish
from framework.contracts.capability import CapabilityFailed, Ports


def _materials(root: Path) -> Path:
    src = root / "inbox"
    (src / "sub").mkdir(parents=True)
    (src / "problem.yaml").write_text("a: 1\n", encoding="utf-8")
    (src / "sub" / "data.tsv").write_bytes(b"x\t1\r\n\x00binary")
    (src / "__pycache__").mkdir()
    (src / "__pycache__" / "junk.pyc").write_bytes(b"\x00")
    (src / ".DS_Store").write_bytes(b"\x00")
    return src


def _lock(root: Path) -> Path:
    lock = root / "freeze.txt"
    lock.write_text("numpy==2.0.0\n", encoding="utf-8")
    return lock


def test_descriptor_is_the_only_capability_that_creates_its_target():
    catalog = {name: module.DESCRIPTOR for name, module in discover().items()}
    assert catalog["init"].creates_target and catalog["init"].stage == "设计"
    assert [name for name, d in catalog.items() if d.creates_target] == ["init"]
    assert catalog["init"].inputs == () and not catalog["init"].needs_executor


def test_init_copies_materials_verbatim_and_lays_out_the_skeleton(tmp_path: Path):
    src, lock = _materials(tmp_path), _lock(tmp_path)
    (tmp_path / "tasks").mkdir()
    task = tmp_path / "tasks" / "demo"
    line = cap_init.run(task, Ports(), domain="petab", materials=str(src), python="3.14",
                        lock=str(lock))
    assert line.startswith("ok demo\tdomain=petab\tdata=3 个文件") and "待填" in line
    # 材料逐字节一致，杂物不搬，README 存根补上
    assert (task / "data" / "problem.yaml").read_bytes() == (src / "problem.yaml").read_bytes()
    copied = task / "data" / "sub" / "data.tsv"
    assert copied.read_bytes() == (src / "sub" / "data.tsv").read_bytes()
    assert not (task / "data" / "__pycache__").exists()
    assert not (task / "data" / ".DS_Store").exists()
    assert packs.PLACEHOLDER in (task / "data" / "README.md").read_text(encoding="utf-8")
    env_dir = task / env.ENV_DIRNAME
    assert (env_dir / env.PYTHON_VERSION_NAME).read_text(encoding="utf-8") == "3.14\n"
    assert (env_dir / env.REQUIREMENTS_NAME).read_bytes() == lock.read_bytes()
    manifest = (task / packs.MANIFEST_NAME).read_text(encoding="utf-8")
    assert "id: demo\n" in manifest and "domain: petab" in manifest and str(src) in manifest
    brief = (task / packs.BRIEF_NAME).read_text(encoding="utf-8")
    assert "{{" not in manifest and "{{" not in brief


def test_template_passes_schema_but_placeholders_block_publishing(tmp_path: Path):
    """模板的形状要合 schema（agent 只填内容），但「待填」还在就不给签：模板不能当需求发布。"""
    (tmp_path / "tasks").mkdir()
    task = tmp_path / "tasks" / "demo"
    cap_init.run(task, Ports(), python="3.12", lock=str(_lock(tmp_path)))
    assert sorted(p.name for p in (task / "data").iterdir()) == ["README.md"]  # 没给材料就只有存根
    problems = packs.intake_problems(task)
    assert problems and all(packs.PLACEHOLDER in p for p in problems), problems
    with pytest.raises(publish.PublishRefused, match=packs.PLACEHOLDER):
        publish.publish_task(task, by="人")
    for name in (packs.MANIFEST_NAME, packs.BRIEF_NAME):
        path = task / name
        path.write_text(path.read_text(encoding="utf-8").replace(packs.PLACEHOLDER, "x"),
                        encoding="utf-8")
    assert packs.intake_problems(task) == []


def test_init_refuses_bad_inputs_instead_of_guessing(tmp_path: Path):
    lock = _lock(tmp_path)
    (tmp_path / "tasks").mkdir()
    existing = tmp_path / "tasks" / "old"
    existing.mkdir()
    with pytest.raises(CapabilityFailed, match="已存在"):
        cap_init.run(existing, Ports(), python="3.12", lock=str(lock))
    with pytest.raises(CapabilityFailed, match="上级目录不存在"):
        cap_init.run(tmp_path / "nowhere" / "t", Ports(), python="3.12", lock=str(lock))
    with pytest.raises(CapabilityFailed, match="--python 与 --lock"):
        cap_init.run(tmp_path / "tasks" / "t", Ports(), python="", lock=str(lock))
    with pytest.raises(CapabilityFailed, match="--lock 指的文件不存在"):
        cap_init.run(tmp_path / "tasks" / "t", Ports(), python="3.12", lock=str(tmp_path / "no"))
    with pytest.raises(CapabilityFailed, match="--materials 指的文件夹不存在"):
        cap_init.run(tmp_path / "tasks" / "t", Ports(), materials=str(tmp_path / "no"),
                     python="3.12", lock=str(lock))
    assert not (tmp_path / "tasks" / "t").exists()  # 拒绝在动盘之前
