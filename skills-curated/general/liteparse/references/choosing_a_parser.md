# Choosing a Document Parser

Use this guide to pick the right tool in the scientific-agent-skills repo.

```mermaid
flowchart TD
  start[User has a document task]
  start --> q1{Need PDF merge split forms or encryption utilities?}
  q1 -->|yes| pdfSkill[pdf skill]
  q1 -->|no| q2{Need Markdown audio video or EPUB?}
  q2 -->|yes| markitdown[markitdown skill]
  q2 -->|no| q3{Need bounding boxes fast local parse or page PNGs for agents?}
  q3 -->|yes| liteparse[liteparse skill]
  q3 -->|no| liteparse
```

## Comparison table

| Criterion | LiteParse | MarkItDown | pdf skill |
|-----------|-----------|------------|-----------|
| **Primary output** | Layout text + JSON with bboxes | Markdown | PDF bytes / extracted text |
| **Runs locally** | Yes | Yes | Yes |
| **Bounding boxes** | Yes | No | Limited |
| **OCR** | Tesseract + optional HTTP OCR | Yes (images/PDF) | Via external tools |
| **Page screenshots** | Yes (PNG) | No | Image extract only |
| **Office → text** | Via LibreOffice convert | Native converters | N/A |
| **Audio / video / EPUB** | No | Yes | No |
| **PDF merge / split / forms** | No | No | Yes |
| **Best for** | RAG grounding, agent vision, batch PDF corpus | LLM-friendly Markdown pipelines | PDF manipulation |

## Decision rules

### Choose **LiteParse** when

- You need **coordinates** for citations, highlighting, or layout-aware chunking.
- You want **fast local** parsing with no cloud service.
- You are building **multimodal** workflows (parse JSON + page screenshots).
- You are batch-processing **folders of PDFs** for a literature review pipeline.
- Scanned PDFs need **OCR** with optional custom HTTP OCR backends.

### Choose **MarkItDown** when

- The downstream step expects **Markdown** (RAG, summarization, notebook ingestion).
- Inputs include **HTML, EPUB, audio, YouTube**.
- You do not need per-span bounding boxes.

### Choose the **pdf** skill when

- The task is **PDF file operations**: merge, split, rotate, watermark, fill forms, encrypt/decrypt.
- You only need simple text extraction without spatial layout or OCR orchestration.

## Combining tools

Common pipelines:

1. **LiteParse → chunk + embed** — JSON/text for vector store; bboxes for UI highlights.
2. **LiteParse screenshots + vision model** — figures and tables; text JSON for search.
3. **LiteParse text → MarkItDown-style post-processing** — only if you must have Markdown; otherwise use LiteParse text directly.
4. **pdf skill merge** → **LiteParse parse** — assemble supplementary PDFs, then extract.

Avoid running LiteParse and MarkItDown on the same file unless you have distinct consumers (coordinates vs Markdown).
