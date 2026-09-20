# /// script
# requires-python = ">=3.12"
# dependencies = [
#     "pymupdf4llm>=1.28.2",
# ]
# ///
"""一篇论文 PDF → `paper.md` + `images/` + `structured.json`（skill `pdf`，契约在 SKILL.md）。

后端是 pymupdf4llm 的版面模式（pymupdf-layout，纯 CPU、ONNX 小模型）：分出标题、节标题、正文、
列表、公式、图、表、图注、脚注、页眉页脚。公式不出 LaTeX，切成图片；表格出单元格文本。
依赖写在头部的 PEP 723 块里，锁在旁边的 `extract.py.lock`；框架用 `uv run --locked --offline` 起它。

只做一件事：读一个 PDF（本地路径或 URL），把三样产物写进 `--out`。不猜路径、不写别处；
结果一行 JSON 到 stdout，诊断到 stderr；退出码 0 成、2 输入不在、3 下载失败、4 不是能解析的 PDF。
"""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import json
import os
import re
import shutil
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

EXIT_OK = 0
EXIT_MISSING = 2
EXIT_DOWNLOAD = 3
EXIT_UNREADABLE = 4

PAPER_NAME = "paper.md"
IMAGES_DIRNAME = "images"
STRUCTURED_NAME = "structured.json"
SOURCE_NAME = "source.pdf"  # 从 URL 取回的原件留一份，materials/ 里就有据可查
DOWNLOAD_TIMEOUT_S = 120
# 论文 PDF 少有超过这个的；超了多半是拿错了链接（整本书、数据集）
DOWNLOAD_MAX_BYTES = 200 * 1024 * 1024
_DOI_RE = re.compile(r"\b(10\.\d{4,9}/[^\s\"<>]+)")
_ARXIV_RE = re.compile(r"(?:arXiv:\s*|arxiv\.org/(?:abs|pdf)/)(\d{4}\.\d{4,5}(?:v\d+)?)", re.I)
_YEAR_RE = re.compile(r"\b(19[5-9]\d|20\d\d)\b")
_REF_SPLIT_RE = re.compile(r"(?=\[\d{1,3}\]\s)")
_REFERENCES_HEADINGS = ("references", "bibliography", "参考文献")


@dataclass(frozen=True)
class Source:
    path: Path
    url: str | None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="ai4sci skill run pdf",
        description="解析一篇论文 PDF：paper.md（正文）、images/（图与公式）、"
                    "structured.json（分节、表、图、引用、元数据）",
    )
    parser.add_argument("--input", required=True, help="PDF 的本地路径，或 http(s) 链接")
    parser.add_argument("--out", help="产物目录；缺省是输入文件旁的同名目录（输入是链接时必须给）")
    args = parser.parse_args(argv)

    out = _resolve_out(args.input, args.out)
    if isinstance(out, int):
        return out
    if not _is_url(args.input) and not Path(args.input).is_file():
        print(f"输入文件不存在：{Path(args.input).resolve()}", file=sys.stderr)
        return EXIT_MISSING
    out.mkdir(parents=True, exist_ok=True)
    source = _fetch(args.input, out)
    if isinstance(source, int):
        return source

    try:
        # 依赖只在真要解析时才导入：--help 与参数错误不用碰它
        import pymupdf
        import pymupdf4llm
        from pymupdf4llm.helpers import document_layout
    except ImportError as exc:
        print(f"pdf skill 的依赖没装好（{exc}）：跑 make skills 预热环境", file=sys.stderr)
        return EXIT_UNREADABLE

    try:
        doc = pymupdf.open(str(source.path))
    except (RuntimeError, ValueError, OSError) as exc:  # pymupdf 打不开就抛这几种
        print(f"读不了这个文件（不是 PDF 或已损坏）：{source.path}：{exc}", file=sys.stderr)
        return EXIT_UNREADABLE
    if not doc.is_pdf:
        print(f"不是 PDF：{source.path}（格式 {doc.metadata.get('format')!r}）", file=sys.stderr)
        return EXIT_UNREADABLE

    images = out / IMAGES_DIRNAME
    if images.exists():  # 幂等：上一次的图清掉，不留孤儿文件
        shutil.rmtree(images)
    images.mkdir()
    # 库里有几处 print 到 stdout；stdout 只留给结果 JSON，所以解析期间全部转到 stderr。
    # 图片路径要写成相对 out 的 `images/…`，所以在 out 下跑（image_path 是相对 cwd 的）
    with contextlib.redirect_stdout(sys.stderr), _chdir(out):
        parsed = document_layout.parse_document(
            doc, filename=source.path.name, image_path=IMAGES_DIRNAME, write_images=True,
            image_format="png", use_ocr=False,  # 扫描件不管：OCR 引擎是另一套系统依赖
        )
        # 先攒 structured 再出 markdown：to_markdown 会就地改 list-item 框的 textlines
        #（实测参考文献每条尾部重复一遍），顺序反了 structured.json 里的引用就是脏的
        structured = build_structured(parsed, source, doc.page_count, pymupdf4llm.__version__)
        markdown = parsed.to_markdown(write_images=True, header=False, footer=False)
    (out / PAPER_NAME).write_text(markdown, encoding="utf-8")
    (out / STRUCTURED_NAME).write_text(
        json.dumps(structured, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    summary = {
        "out": str(out), "pages": doc.page_count,
        "sections": len(structured["sections"]), "tables": len(structured["tables"]),
        "figures": len(structured["figures"]), "formulas": len(structured["formulas"]),
        "references": len(structured["references"]),
        "files": [PAPER_NAME, STRUCTURED_NAME, f"{IMAGES_DIRNAME}/"]
                 + ([SOURCE_NAME] if source.url else []),
    }
    print(json.dumps(summary, ensure_ascii=False))
    return EXIT_OK


def _resolve_out(raw_input: str, raw_out: str | None) -> Path | int:
    if raw_out:
        return Path(raw_out).resolve()
    if _is_url(raw_input):
        print("输入是链接时要给 --out：链接旁边没有「同名目录」可放", file=sys.stderr)
        return EXIT_MISSING
    path = Path(raw_input)
    return (path.parent / path.stem).resolve()


def _fetch(raw_input: str, out: Path) -> Source | int:
    """本地路径原样用（存在与否 main 已核对）；链接就下载到 out/source.pdf，先验 %PDF 头再落盘。"""
    if not _is_url(raw_input):
        return Source(Path(raw_input).resolve(), None)
    request = urllib.request.Request(raw_input, headers={"User-Agent": "ai4sci-pdf-skill/1"})
    try:
        with urllib.request.urlopen(request, timeout=DOWNLOAD_TIMEOUT_S) as resp:
            data = resp.read(DOWNLOAD_MAX_BYTES + 1)
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        print(f"下载失败：{raw_input}：{exc}", file=sys.stderr)
        return EXIT_DOWNLOAD
    if len(data) > DOWNLOAD_MAX_BYTES:
        print(f"下载的文件超过 {DOWNLOAD_MAX_BYTES // 2**20} MB，不像一篇论文：{raw_input}",
              file=sys.stderr)
        return EXIT_DOWNLOAD
    if not data.startswith(b"%PDF"):
        head = data[:200].decode("utf-8", errors="replace").strip().replace("\n", " ")
        print(f"链接返回的不是 PDF（开头是 {head[:80]!r}）：{raw_input}", file=sys.stderr)
        return EXIT_DOWNLOAD
    path = out / SOURCE_NAME
    path.write_bytes(data)
    print(f"已下载 {len(data)} 字节到 {path}", file=sys.stderr)
    return Source(path, raw_input)


def _is_url(text: str) -> bool:
    return text.startswith(("http://", "https://"))


@contextlib.contextmanager
def _chdir(path: Path):
    previous = Path.cwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(previous)


# ── structured.json ──────────────────────────────────────────────────────────
def build_structured(parsed, source: Source, page_count: int, backend_version: str) -> dict:
    """从版面分析结果攒出给机器读的那份：分节、表、图、公式、参考文献、元数据。

    每一项都带页码（1 起）。图注按同页最近的 caption 框配；参考文献取「References」节之后的条目。
    """
    sections: list[dict] = []
    tables: list[dict] = []
    figures: list[dict] = []
    formulas: list[dict] = []
    reference_texts: list[str] = []
    links: list[str] = []
    title = ""
    in_references = False
    first_page_text: list[str] = []
    for page in parsed.pages:
        number = page.page_number
        captions = _assign_captions(page.boxes)
        for index, box in enumerate(page.boxes):
            kind = box.boxclass
            text = _text(box)
            if number == 1 and text:
                first_page_text.append(text)
            if kind == "title" and not title:
                title = text
            elif kind == "section-header":
                sections.append({"level": int(box.header_level or 1), "title": text,
                                 "page": number})
                in_references = text.strip().rstrip(".:").lower() in _REFERENCES_HEADINGS
            elif kind == "table" and box.table:
                cells = box.table.get("extract") or []
                tables.append({
                    "page": number, "caption": captions.get(index),
                    "header": [_cell(c) for c in cells[0]] if cells else [],
                    "rows": [[_cell(c) for c in row] for row in cells[1:]],
                    "markdown": (box.table.get("markdown") or "").strip(),
                })
            elif kind == "picture":
                figures.append({"page": number, "file": _image_name(box),
                                "caption": captions.get(index)})
            elif kind == "formula":
                formulas.append({"page": number, "file": _image_name(box)})
            elif in_references and kind in ("list-item", "text") and text:
                reference_texts.extend(_split_references(text))
        for link in page.links or []:
            uri = link.get("uri")
            if uri and uri not in links:
                links.append(uri)

    metadata = parsed.metadata or {}
    head = "\n".join(first_page_text)
    doi = _DOI_RE.search(head)
    arxiv = _ARXIV_RE.search(head) or (_ARXIV_RE.search(source.url) if source.url else None)
    return {
        "source": {
            "file": source.path.name, "sha256": _sha256(source.path), "pages": page_count,
            "url": source.url,
        },
        "backend": {"name": "pymupdf4llm", "version": backend_version, "mode": "layout",
                    "formulas": "image"},
        "metadata": {
            "title": title or (metadata.get("title") or "").strip(),
            "authors_line": _authors_line(parsed),
            "year": _year(metadata, head),
            "doi": doi.group(1).rstrip(".,;") if doi else None,
            "arxiv": arxiv.group(1) if arxiv else None,
            "pdf_metadata": {k: v for k, v in metadata.items() if v},
        },
        "sections": sections,
        "tables": tables,
        "figures": figures,
        "formulas": formulas,
        "references": reference_texts,
        "links": links,
    }


def _text(box) -> str:
    lines = box.textlines or []
    return " ".join(" ".join(span.get("text", "") for span in line.get("spans", []))
                    for line in lines).strip()


def _cell(cell) -> str:
    return " ".join(str(cell or "").split())


def _image_name(box) -> str | None:
    """写盘后 `box.image` 是相对 out 的路径字符串（`images/x.png`）；没写盘就是 None。"""
    return box.image if isinstance(box.image, str) else None


def _assign_captions(boxes) -> dict[int, str]:
    """同页的图注配给表与图，返回 {对象在 boxes 里的下标: 图注文字}。

    先按种类分开（「Table …」只配表、「Figure …」只配图），同一种类里对象与图注数目相等就按从上到下
    的次序一一对应；数目不等才退到「离得最近的没配过的」。只按最近距离配会错：两张表各配一条图注、
    图注都在表下方时，下面那张表离上面那条图注更近（PINNs 第 9 页）。没有 caption 框的对象没有图注，
    不拿正文冒充。
    """
    assigned: dict[int, str] = {}
    for boxclass in ("table", "picture"):
        objects = sorted((i for i, b in enumerate(boxes) if b.boxclass == boxclass),
                         key=lambda i: boxes[i].y0)
        captions = sorted((i for i, b in enumerate(boxes)
                           if b.boxclass == "caption" and _text(b)
                           and _caption_fits(boxclass, _text(b))),
                          key=lambda i: boxes[i].y0)
        if not objects or not captions:
            continue
        if len(objects) == len(captions):
            for oi, ci in zip(objects, captions, strict=True):
                assigned[oi] = _text(boxes[ci])
            continue
        pairs = sorted((min(abs(boxes[ci].y0 - boxes[oi].y1), abs(boxes[oi].y0 - boxes[ci].y1)),
                        oi, ci) for oi in objects for ci in captions)
        used: set[int] = set()
        for _, oi, ci in pairs:
            if oi in assigned or ci in used:
                continue
            assigned[oi] = _text(boxes[ci])
            used.add(ci)
    return assigned


def _caption_fits(boxclass: str, caption: str) -> bool:
    head = caption.lstrip().lower()
    if head.startswith(("table", "tab.", "表")):
        return boxclass == "table"
    if head.startswith(("figure", "fig.", "fig ", "图")):
        return boxclass == "picture"
    return True


def _split_references(text: str) -> list[str]:
    """一个框里可能挤着几条 `[n] …`；按编号切开，切不开就整段算一条。"""
    parts = [p.strip() for p in _REF_SPLIT_RE.split(text) if p.strip()]
    return parts or [text.strip()]


def _authors_line(parsed) -> str:
    """标题框之后第一段文字，通常是作者行；不拆成人名清单（拆错比不拆更糟）。"""
    page = parsed.pages[0] if parsed.pages else None
    if page is None:
        return ""
    seen_title = False
    for box in page.boxes:
        if box.boxclass == "title":
            seen_title = True
        elif seen_title and box.boxclass == "text":
            return _text(box)
    return ""


def _year(metadata: dict, head: str) -> int | None:
    """先信 PDF 自己记的日期（D:YYYYMMDD…），再在首页文字里找一个年份。"""
    for key in ("creationDate", "modDate"):
        raw = metadata.get(key) or ""
        match = re.search(r"D:(\d{4})", raw)
        if match:
            return int(match.group(1))
    match = _YEAR_RE.search(head)
    return int(match.group(1)) if match else None


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


if __name__ == "__main__":
    raise SystemExit(main())
