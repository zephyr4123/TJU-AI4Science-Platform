# Plugin System

## Plugin Discovery

Plugins are Python distributions registered under the `markitdown.plugin` entry-point group.

List discovered plugins without enabling them:

```bash
markitdown --list-plugins
```

Enable plugins for one CLI conversion:

```bash
markitdown --use-plugins input.rtf -o output.md
```

Enable in Python:

```python
from markitdown import MarkItDown

converter = MarkItDown(enable_plugins=True)
result = converter.convert_local("input.rtf")
print(result.markdown)
```

## Plugin Trust Checklist

Before installing a plugin:

- Confirm the exact package name; defend against typosquatting.
- Verify the publisher and source repository.
- Review `pyproject.toml`, entry points, dependencies, and install hooks.
- Inspect converters for filesystem, subprocess, environment, and network access.
- Pin an exact version and retain a lockfile/hash in production.
- Test in an isolated environment with non-sensitive documents.
- Re-run review after every update.

Do not install arbitrary packages merely because they use the `#markitdown-plugin` tag.

## Plugin Interface Version 1

### Converter

```python
from typing import Any, BinaryIO

from markitdown import (
    DocumentConverter,
    DocumentConverterResult,
    StreamInfo,
)


class ExampleConverter(DocumentConverter):
    def accepts(
        self,
        file_stream: BinaryIO,
        stream_info: StreamInfo,
        **kwargs: Any,
    ) -> bool:
        return (stream_info.extension or "").lower() == ".example"

    def convert(
        self,
        file_stream: BinaryIO,
        stream_info: StreamInfo,
        **kwargs: Any,
    ) -> DocumentConverterResult:
        payload = file_stream.read()
        return DocumentConverterResult(
            markdown=payload.decode("utf-8", errors="replace")
        )
```

`accepts()` must restore the stream position if it reads any bytes.

### Module registration

```python
from markitdown import MarkItDown

__plugin_interface_version__ = 1


def register_converters(markitdown: MarkItDown, **kwargs) -> None:
    markitdown.register_converter(ExampleConverter())
```

### `pyproject.toml`

```toml
[project.entry-points."markitdown.plugin"]
example = "example_markitdown_plugin"
```

MarkItDown calls `register_converters()` when a plugin-enabled instance is constructed and forwards the constructor keywords.

## Converter Priority

Lower values run first:

- Specific built-in formats: `0.0`
- Generic text/HTML/ZIP converters: `10.0`

Registering a converter before built-ins can change the parser selected for existing formats. Treat priority as part of the plugin's security and compatibility review.

## Sources

- Sample plugin at v0.1.6: https://github.com/microsoft/markitdown/tree/v0.1.6/packages/markitdown-sample-plugin
