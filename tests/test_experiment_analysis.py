"""analysis.md 契约的解析器：数据表怎么读、正文里哪些数算数、哪些不算。

边界要写明白：整数与百分比不查，行内代码与代码块不查，数据表本身不算正文。
这些不是漏洞，是 0.2.0 写在纲领里的已知边界；测试把它钉住，改边界得先改这里。
"""

from __future__ import annotations

from framework.experiment.analysis import parse_claims, prose_numbers, validate_analysis

GOOD = """# t
## 结论
best 是 experiment/1/iter_3 的 0.001，比 experiment/1/baseline 的 0.03 降了 96.7%，共 3 轮；
`code/x.py:0.5` 是文件。
## 数据
| 来源 | 指标 | 值 |
|---|---|---|
| experiment/1/baseline | val_mse | 0.03 |
| experiment/1/iter_3 | val_mse | 1e-3 |
## 证伪与未决
```
loss 0.777 在代码块里
```
无。
"""


def test_validate_ok_and_claims_parse():
    assert validate_analysis(GOOD) == []
    claims, problems = parse_claims(GOOD)
    assert problems == []
    assert [(c.source, c.metric, c.value) for c in claims] == [
        ("experiment/1/baseline", "val_mse", 0.03), ("experiment/1/iter_3", "val_mse", 0.001)]
    assert [c.line_no for c in claims] == [8, 9]


def test_prose_numbers_skip_integers_percent_code_and_the_table():
    tokens = [n.token for n in prose_numbers(GOOD)]
    assert tokens == ["0.001", "0.03"]


def test_missing_headings_are_listed():
    problems = validate_analysis("## 结论\n只有一节\n")
    assert problems == ["缺少小节 ## 数据", "缺少小节 ## 证伪与未决"]


def test_data_section_without_table_is_a_problem():
    text = "## 结论\nx\n## 数据\n没有表\n## 证伪与未决\ny\n"
    assert validate_analysis(text) == ["## 数据 里没有数据表，或表里一行都没有"]


def test_wrong_header_stops_parsing_with_a_problem():
    text = "## 数据\n| run | metric | value |\n|---|---|---|\n| experiment/1/baseline | m | 1.0 |\n"
    claims, problems = parse_claims(text)
    assert claims == []
    assert problems == ["第 2 行：数据表表头必须是 | 来源 | 指标 | 值 |"]


def test_bad_rows_are_reported_not_skipped():
    text = ("## 数据\n| 来源 | 指标 | 值 |\n|---|---|---|\n"
            "| run_1 | m | 1.0 |\n| experiment/1/iter_1 | m | 很小 |\n"
            "| experiment/1/iter_1 | m |\n")
    claims, problems = parse_claims(text)
    assert claims == []
    assert problems == [
        "第 4 行：来源列要形如 experiment/<n>/baseline 或 experiment/<n>/iter_N，得到 'run_1'",
        "第 5 行：值列不是数字：'很小'",
        "第 6 行：数据表要三列，得到 2 列",
    ]


def test_scientific_and_signed_numbers_and_identifiers():
    text = "## 结论\n-1.5e-3 与 2E5 算，iter_0.5 与 v1.2.3 不算，12.5 % 也不算。\n"
    assert [n.value for n in prose_numbers(text)] == [-0.0015, 200000.0]
