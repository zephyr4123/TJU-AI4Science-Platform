# Migration and Release Notes

This skill targets MarkItDown 0.1.6. The timeline below summarizes changes that affect user code and operational guidance.

## Release Timeline

### 0.1.0 — March 22, 2025

Major architecture release:

- Optional dependency feature groups introduced
- Plugin architecture introduced
- Conversions moved to in-memory streams; temporary files removed
- EPUB support added
- CLI extension, MIME, and charset hints added
- `--keep-data-uris` added

Breaking changes:

- Install `[all]` for behavior comparable to earlier all-in-one installs.
- `convert_stream()` now requires a binary stream.
- `DocumentConverter` implementations now receive binary streams plus `StreamInfo`, not file paths.

### 0.1.1 — March 25, 2025

- `convert_url()` renamed to `convert_uri()`.
- `file:` and `data:` URI handling added.
- `convert_url()` retained as a compatibility alias.

### 0.1.2 — May 28, 2025

- DOCX math-equation rendering
- Dedicated CSV-to-Markdown conversion
- XML/OMML parsing switched to `defusedxml`
- Streamable HTTP MCP support
- YouTube transcript fixes
- Python requirement updated to 3.10+

### 0.1.3 — August 26, 2025

- Safer ExifTool handling, requiring version 12.24 or later
- MCP plugin enablement through `MARKITDOWN_ENABLE_PLUGINS`
- DOCX linked-image fixes
- Document Intelligence HTML type handling
- Custom LLM prompt forwarding fix
- Additional HTML/PPTX robustness

### 0.1.4 — December 1, 2025

Security maintenance release:

- Mammoth updated to address CVE-2025-11849
- `pdfminer.six` updated to address GHSA-wf5f-4jwr-ppcp

### 0.1.5 — February 20, 2026

- Better aligned and wide PDF tables
- Partially numbered PDF-list fix
- `text/markdown` added to the HTTP Accept header
- Windows ONNX Runtime pin removed

### 0.1.6 — May 26, 2026

- Official OCR layer/plugin for embedded images and scanned PDFs
- PDF page cleanup to fix linear memory growth
- Deeply nested HTML recursion fix
- Azure Content Understanding converter
- Expanded security guidance for broad I/O and MCP binding

## Upgrade Installation

Create a clean environment for the comparison:

```bash
uv venv --python 3.12 .venv-markitdown
source .venv-markitdown/bin/activate
uv pip install "markitdown[all]==0.1.6"
```

Do not test a migration in an environment that still contains unknown third-party plugins.

## Code Replacements

### Result content

Old/compatibility:

```python
content = result.text_content
```

Current:

```python
content = result.markdown
```

`text_content` still works in 0.1.6 but is explicitly documented in source as a soft-deprecated alias.

### Local conversion

Broad:

```python
result = converter.convert(user_value)
```

Narrow local path:

```python
result = converter.convert_local(validated_path)
```

Use `convert_stream()` for validated uploaded bytes and `convert_response()` after an application-controlled download.

### Streams

Old:

```python
from io import StringIO

result = converter.convert_stream(StringIO("text"))
```

Current:

```python
from io import BytesIO

from markitdown import StreamInfo

result = converter.convert_stream(
    BytesIO(b"text"),
    stream_info=StreamInfo(
        extension=".txt",
        mimetype="text/plain",
        charset="utf-8",
    ),
)
```

### URI API

Old:

```python
result = converter.convert_url(uri)
```

Current:

```python
result = converter.convert_uri(validated_uri)
```

Prefer caller-controlled fetching plus `convert_response()` for HTTP(S).

### Hints

Legacy:

```python
result = converter.convert_stream(stream, file_extension=".pdf")
```

Current:

```python
from markitdown import StreamInfo

result = converter.convert_stream(
    stream,
    stream_info=StreamInfo(
        extension=".pdf",
        mimetype="application/pdf",
        filename="upload.pdf",
    ),
)
```

The legacy `file_extension`/`url` parameters still exist but are marked for migration in source.

## Custom Converter Migration

Pre-0.1 converter:

```python
class OldConverter(DocumentConverter):
    def convert(self, file_path):
        ...
```

0.1.x converter:

```python
from typing import Any, BinaryIO

from markitdown import DocumentConverter, DocumentConverterResult, StreamInfo


class CurrentConverter(DocumentConverter):
    def accepts(
        self,
        file_stream: BinaryIO,
        stream_info: StreamInfo,
        **kwargs: Any,
    ) -> bool:
        ...

    def convert(
        self,
        file_stream: BinaryIO,
        stream_info: StreamInfo,
        **kwargs: Any,
    ) -> DocumentConverterResult:
        return DocumentConverterResult(markdown="...")
```

If `accepts()` peeks at bytes, restore the original stream position before returning.

## Plugin Packaging Migration

Outdated entry-point group:

```toml
[project.entry-points."markitdown.plugins"]
```

Current group:

```toml
[project.entry-points."markitdown.plugin"]
example = "example_markitdown_plugin"
```

The plugin module must export:

```python
__plugin_interface_version__ = 1


def register_converters(markitdown, **kwargs):
    ...
```

Use `pyproject.toml`; old `setup.py`-only examples are no longer the preferred packaging pattern.

## Installation Guidance Migration

Outdated:

```bash
uv pip install markitdown
uv pip install "markitdown[all]"
```

Repository-standard reproducible install:

```bash
uv pip install "markitdown[all]==0.1.6"
```

The base package no longer implies every format dependency. Select an extra or `[all]`.

## Security Migration

Replace:

- User-controlled `convert(value)` calls
- Broad URI access
- Automatic plugin enablement
- Undisclosed LLM/cloud fallback

With:

- Narrow conversion APIs
- Path and destination allowlists
- Explicit size/time/resource limits
- Reviewed, pinned, opt-in plugins
- User-approved external processing

## Regression Checklist

- [ ] Install 0.1.6 in a clean environment
- [ ] Replace `.text_content` with `.markdown`
- [ ] Replace text streams with binary streams
- [ ] Replace `convert_url()` with `convert_uri()` or controlled fetch
- [ ] Update custom converter signatures
- [ ] Update plugin entry-point group
- [ ] Pin format extras
- [ ] Test PDF tables and multi-column reading order
- [ ] Test DOCX math and linked images
- [ ] Test PPTX grouped shapes and notes
- [ ] Confirm plugins remain disabled by default
- [ ] Confirm no conversion unexpectedly calls network/cloud
- [ ] Compare semantic output on a representative corpus

## Sources

- Releases: https://github.com/microsoft/markitdown/releases
- 0.1.0 migration notes: https://github.com/microsoft/markitdown/releases/tag/v0.1.0
- 0.1.6 release: https://github.com/microsoft/markitdown/releases/tag/v0.1.6
