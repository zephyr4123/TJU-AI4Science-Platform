"""原码复现基线（纲领 P-24）：零模型的部分用剧本执行层测全——原件里的上游代码怎么搬、出处怎么记、
执行层写了壳之后改动怎么留痕、基线跑完论文值与我们的值怎么并排、「无解」那条预检不再判死。

执行层写什么由剧本决定；上游代码用夹具的 train.py 当「别人的仓库」。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from compute.local import LocalCompute
from framework.capabilities import reproduction as cap
from framework.contracts.capability import CapabilityFailed, Inputs, Ports
from framework.experiment import pack as packs
from framework.workspace import outputs
from tests.fixtures import packs_factory as pf
from tests.fixtures.scripted_backend import ScriptedRunner
from tests.test_capability_design import MAKE_RUN0_SH

UPSTREAM = "corebench"
README = "# corebench\n\n跑：python train.py\n"
RECEIPT = {"kind": "git", "source": "https://github.com/x/corebench", "commit": "abc123",
           "files": 2, "bytes": 100, "license": "LICENSE", "out": "materials/corebench"}
SOURCES_MD = "# 材料来源\n\n- 官方代码：https://github.com/x/corebench，commit abc123，MIT\n"


def _scoring(attainable: float = 0.3) -> str:
    scoring = pf.default_scoring()
    scoring.pop("domain")
    scoring["metrics"][0]["attainable"] = attainable
    return pf.to_yaml(scoring)


def _shell(attainable: float = 0.3, edit_upstream: bool = False) -> dict[str, str]:
    """执行层写的壳：评分契约、三个脚本；`edit_upstream` 时顺手改一行上游代码。"""
    moves = {
        "scoring.yaml": _scoring(attainable),
        "harness/launcher.sh": pf.LAUNCHER_SH,
        "harness/evaluate.py": pf.EVALUATE_PY,
        "harness/make_run0.sh": MAKE_RUN0_SH,
    }
    if edit_upstream:
        moves["code/train.py"] = "# 修了路径\n" + pf.TRAIN_PY
    return moves


@pytest.fixture
def ws(tmp_path):
    """需求确认过、原件里有上游仓库（带 download 收据）与 env/、文献阶段写了 sources.md
    的工作区。"""
    workspace = pf.make_workspace(tmp_path, "repro")
    upstream = workspace.materials / UPSTREAM
    upstream.mkdir()
    (upstream / "train.py").write_text(pf.TRAIN_PY, encoding="utf-8")
    (upstream / "README.md").write_text(README, encoding="utf-8")
    (upstream / cap.RECEIPT_NAME).write_text(json.dumps(RECEIPT), encoding="utf-8")
    (workspace.materials / "notes.txt").write_text("研究者的备忘\n", encoding="utf-8")
    lit, meta = outputs.open_output(workspace, "literature", title="材料来源", by="assistant",
                                    inputs=[], params={}, flow=None, step=None, requirement=1,
                                    chat_id=None)
    (lit / "sources.md").write_text(SOURCES_MD, encoding="utf-8")
    outputs.close_output(lit, meta, ok=True, line="手写")
    domains = tmp_path / "domains"
    (domains / "generic").mkdir(parents=True)
    (domains / "generic" / "profile.yaml").write_text("id: generic\n", encoding="utf-8")
    return workspace, domains, lit


def _open(workspace) -> Path:
    directory, _ = outputs.open_output(workspace, "design", title="t", by=cap.NAME,
                                       inputs=["literature/1"], params={}, flow=None, step=None,
                                       requirement=1, chat_id=None)
    return directory


def _inputs(workspace, lit: Path) -> Inputs:
    return Inputs(workspace.root, (lit,), ("literature/1",))


def test_missing_code_dir_is_named_with_what_materials_has(ws, monkeypatch):
    workspace, domains, lit = ws
    monkeypatch.setattr(cap.paths, "domains_root", lambda: domains)
    runner = ScriptedRunner([_shell()])
    with pytest.raises(CapabilityFailed, match="--code <目录名>.*corebench"):
        cap.run(_open(workspace), _inputs(workspace, lit),
                Ports(runner=runner, compute=LocalCompute()))
    with pytest.raises(CapabilityFailed, match="materials/nope/ 不存在"):
        cap.run(_open(workspace), _inputs(workspace, lit),
                Ports(runner=runner, compute=LocalCompute()), code="nope")
    assert runner.calls == 0


def test_upstream_is_moved_into_code_shell_is_drafted_baseline_runs_and_edits_are_recorded(
        ws, monkeypatch):
    """整颗能力：上游进 code/（收据不算原件）、其余原件进 data/、出处记进 upstream.json；执行层写壳
    并改了一行上游 → upstream.diff 记下；基线在本机跑出，结论行论文值与我们的值并排。"""
    workspace, domains, lit = ws
    monkeypatch.setattr(cap.paths, "domains_root", lambda: domains)
    pack = _open(workspace)
    runner = ScriptedRunner([_shell(edit_upstream=True)])
    line = cap.run(pack, _inputs(workspace, lit), Ports(runner=runner, compute=LocalCompute()),
                   code=UPSTREAM)
    assert line.startswith("reproduction ok\tsession=1\tchanged=5\t")
    assert runner.limits == (cap.SESSION_MAX_TURNS, cap.SESSION_MAX_BUDGET_USD)
    assert "Bash 只放行" in runner.prompts[0]  # 执行层通用段：别拿 Bash 去 cd / mkdir / awk
    assert "baseline=0.025\t" in line and "attainable=0.3\t" in line
    assert "upstream_changed=1\t" in line and "reproducibility --from design/1" in line
    assert (pack / "code" / "README.md").read_text(encoding="utf-8") == README
    assert not (pack / "data" / UPSTREAM).exists()
    assert (pack / "data" / "notes.txt").is_file() and not (pack / "data" / "env").exists()
    assert packs.read_upstream(pack) == {"name": UPSTREAM, "source": RECEIPT["source"],
                                         "commit": "abc123"}
    diff = (pack / packs.UPSTREAM_DIFF_NAME).read_text(encoding="utf-8")
    assert diff.startswith("# code/ 相对上游 corebench 的改动：1 个文件\n")
    assert "--- upstream/train.py" in diff and "+++ code/train.py" in diff and "修了路径" in diff
    assert (pack / "baseline" / "sigma.json").is_file()
    prompt = runner.prompts[0]
    for token in ("commit abc123", "https://github.com/x/corebench", "官方代码：", "README.md",
                  "train.py", "复现到第几级", "### code/（上游仓库，2 个文件",
                  "种子照论文", "论文的第一个种子", "不许把论文的种子换成平台的"):
        assert token in prompt, token
    # 复现不用平台的 42–46：两轮演练执行层都照它换掉了论文的种子
    assert "基线一次（seed 42）" not in prompt
    assert "不适用" not in line  # 预检的「无解」不出现在结论里


def test_reproduction_does_not_die_on_the_headroom_verdict(ws, monkeypatch):
    """设计那颗会判「离尽头不够一个门就无解」；复现的基线到论文值的距离就是结果本身，不判死。
    这里论文值就等于我们能跑出来的值（room=0）。"""
    workspace, domains, lit = ws
    monkeypatch.setattr(cap.paths, "domains_root", lambda: domains)
    pack = _open(workspace)
    runner = ScriptedRunner([_shell(attainable=0.025)])
    line = cap.run(pack, _inputs(workspace, lit), Ports(runner=runner, compute=LocalCompute()),
                   code=UPSTREAM)
    assert "baseline=0.025\t" in line and "attainable=0.025\troom=" in line
    assert "upstream_changed=0\t" in line
    assert "一字未改" in (pack / packs.UPSTREAM_DIFF_NAME).read_text(encoding="utf-8")


def test_continue_without_feedback_reruns_only_the_baseline(ws, monkeypatch):
    workspace, domains, lit = ws
    monkeypatch.setattr(cap.paths, "domains_root", lambda: domains)
    pack = _open(workspace)
    first = ScriptedRunner([_shell()])
    cap.run(pack, _inputs(workspace, lit), Ports(runner=first, compute=LocalCompute()),
            code=UPSTREAM)
    import shutil

    shutil.rmtree(pack / "baseline")
    idle = ScriptedRunner([])
    line = cap.run(pack, _inputs(workspace, lit), Ports(runner=idle, compute=LocalCompute()))
    assert idle.calls == 0 and line.startswith("reproduction ok\tsession=-\tchanged=0")
    assert (pack / "baseline" / "sigma.json").is_file()
    # 第二版：现状只贴 harness/ 与改过的上游文件，不把整个仓库贴进提示；收据不进 code/
    second = ScriptedRunner([{"code/README.md": README + "改动\n"}])
    line = cap.run(pack, _inputs(workspace, lit), Ports(runner=second, compute=LocalCompute()),
                   feedback="README 补一句")
    assert "upstream_changed=1\t" in line and "changed=1\t" in line
    prompt = second.prompts[0]
    assert "### harness/launcher.sh" in prompt and "### code/（上游仓库，2 个文件" in prompt
    assert "### code/train.py" not in prompt  # 没改过的上游文件只列名字
    assert "README 补一句" in prompt
    assert not (pack / "code" / cap.RECEIPT_NAME).exists()


def test_continue_refreshes_the_env_snapshot_after_env_add_but_refuses_a_real_change(
        ws, monkeypatch):
    """真跑时镜像环境缺 scipy：`ai4sci env add` 补了包、清单多了几行，解释器没变——接着干要刷新
    快照、不能让执行层把壳从头再写；隔离新建那种清单变了照旧拒。"""
    import sys

    workspace, domains, lit = ws
    monkeypatch.setattr(cap.paths, "domains_root", lambda: domains)
    marker = f"local:{sys.executable}\n"
    (workspace.materials / "env" / "interpreter").write_text(marker, encoding="utf-8")
    pack = _open(workspace)
    cap.run(pack, _inputs(workspace, lit), Ports(runner=ScriptedRunner([_shell()]),
                                                  compute=LocalCompute()), code=UPSTREAM)
    lock = workspace.materials / "env" / "requirements.lock"
    lock.write_text("# ai4sci env add 补装：scipy\nscipy==1.15.3\n" + lock.read_text("utf-8"),
                    encoding="utf-8")
    line = cap.run(pack, _inputs(workspace, lit), Ports(runner=ScriptedRunner([]),
                                                         compute=LocalCompute()))
    assert line.startswith("reproduction ok\tsession=-")
    assert "scipy==1.15.3" in (pack / "env" / "requirements.lock").read_text(encoding="utf-8")
    (workspace.materials / "env" / "interpreter").unlink()  # 换成隔离新建：清单变了就拒
    with pytest.raises(CapabilityFailed, match="环境变了不能接着改"):
        cap.run(pack, _inputs(workspace, lit), Ports(runner=ScriptedRunner([]),
                                                      compute=LocalCompute()))


def test_upstream_without_receipt_falls_back_to_git_or_blank(tmp_path):
    plain = tmp_path / "plain"
    plain.mkdir()
    assert cap._upstream_of(plain, "plain") == {"name": "plain", "source": "", "commit": ""}
