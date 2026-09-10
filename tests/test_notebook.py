"""实验笔记：追加、截断、整本读回。"""

from __future__ import annotations

from framework import notebook


def test_append_then_read_keeps_order_and_marks_missing_commit(tmp_path):
    path = tmp_path / "notebook.md"
    assert "还没有笔记" in notebook.read(path)
    notebook.append(path, iter_n=1, status="keep", metric="0.018", note="改进 delta=0.012",
                    report="假设：学习率太大。改动：LR 减半。预期：更稳。",
                    diffstat=" code/train.py | 2 +-\n 1 file changed")
    notebook.append(path, iter_n=2, status="readonly_violated", metric="-", note="动了 harness",
                    report="", diffstat="")
    text = notebook.read(path)
    assert text.index("第 1 轮 · keep") < text.index("第 2 轮 · readonly_violated")
    assert "LR 减半" in text and "code/train.py | 2 +-" in text
    assert "执行层没有自述" in text and "没有产生 commit" in text


def test_report_is_capped_so_the_notebook_stays_bounded(tmp_path):
    path = tmp_path / "notebook.md"
    notebook.append(path, iter_n=1, status="discard", metric="0.03", note="持平",
                    report="x" * 5000, diffstat="\n".join(f"line{i}" for i in range(40)))
    text = notebook.read(path)
    assert text.count("x") == notebook.REPORT_CHARS and "…" in text
    assert "line5" in text and "line6" not in text
