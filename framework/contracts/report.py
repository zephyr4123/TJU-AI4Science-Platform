"""`verify/report.json` 的读取与校验：验证能力产物这一侧的契约。

写报告的（验证能力）落盘前先过一遍 schema，读报告的（`ai4sci status`、以后的写作能力）
用同一个函数读——报告本身不合约就当没有报告，不猜。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import jsonschema

from framework.contracts.packs import SCHEMA_DIR

SCHEMA_PATH = SCHEMA_DIR / "report.schema.json"


def validate_report(doc: Any) -> list[str]:
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    return [
        f"report.json 不合 schema：{' '.join(str(e.message).split())}"
        for e in jsonschema.Draft202012Validator(schema).iter_errors(doc)
    ]


def read_report(path: Path) -> dict[str, Any]:
    """读并校验；不合约就抛 ValueError 带原因，调用方决定怎么报。"""
    doc = json.loads(Path(path).read_text(encoding="utf-8"))
    problems = validate_report(doc)
    if problems:
        raise ValueError(f"{path}：" + "；".join(problems))
    return doc
