"""实验内环自己的 git 仓（`framework/experiment/gitwork.py`）不受人的全局 git 配置影响。"""

from __future__ import annotations

import hashlib

from framework.experiment import gitwork


def test_line_endings_survive_a_reset_whatever_the_persons_autocrlf(tmp_path, monkeypatch):
    """Git for Windows 缺省 core.autocrlf=true：reset 把文件改成 CRLF，评测文件的哈希
    （harness/SHA256SUMS）对不上，被当成动了评测（外层 #210，spec 3.10）。这里用一份开着 autocrlf
    的全局配置，在任何系统上造出同样的人。"""
    persons = tmp_path / "gitconfig"
    persons.write_text("[core]\n\tautocrlf = true\n", encoding="utf-8")
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(persons))
    work = tmp_path / "work"
    (work / "harness").mkdir(parents=True)
    evaluate = work / "harness" / "evaluate.py"
    evaluate.write_bytes(b"import json\nprint(json.dumps({'mse': 0.1}))\n")
    sealed = hashlib.sha256(evaluate.read_bytes()).hexdigest()
    base = gitwork.init_repo(work, "baseline")
    (work / "train.py").write_bytes(b"x = 1\n")
    gitwork.commit_paths(work, ["train.py"], "iter 1")
    evaluate.write_bytes(b"print('mse 0')\n")  # 这一轮执行层动了评测：reset 时从仓里重新检出
    gitwork.revert_to(work, base)
    assert hashlib.sha256(evaluate.read_bytes()).hexdigest() == sealed
    assert b"\r\n" not in evaluate.read_bytes()
