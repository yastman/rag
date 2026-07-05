# Docling Architecture Authority

> Canonical decisions for Docling in this project. When in doubt, this document is the
> authority. card_62cd34acf8c3 / phase_bd57610de114.

## Architecture Decision

**Docling is an in-process Python SDK — NOT a service.**

- No HTTP calls. No sidecar. No network dependency for document parsing.
- Docling runs in the same Python process as the ingestion pipeline.
- The compose profile `ingest` is a **runtime profile** (controls which services start),
  not a pyproject extra.

## Prohibited Patterns

The following are **PROHIBITED** — do not add, do not reference:

| Pattern | Status |
|---|---|
| `docling-serve` | REMOVED — was never the correct integration |
| `DOCLING_URL` | REMOVED — no HTTP endpoint exists |
| Any HTTP/REST call to a Docling sidecar | PROHIBITED |

If you see references to `docling-serve` or `DOCLING_URL` in code or docs, treat them as
migration artifacts and remove them.

## Bot vs Ingestion Split

| Component | Docling? |
|---|---|
| `telegram_bot/` (bot image) | ❌ Does NOT import or install Docling |
| `src/ingestion/` (ingestion runtime) | ✅ Only place Docling lives |

The bot image is kept lean. Docling — and its heavy ML dependencies (`transformers`,
`pymupdf`, `fastembed`) — are installed only in the ingestion runtime.

## Extras Structure

The single pyproject extra that brings in Docling is:

```
docling-native
```

Not `ingest`, not `ingestion` — **`docling-native`**.

Dependencies bundled in `docling-native`:
- `docling-core[chunking]`
- `transformers`
- `pymupdf`
- `fastembed`

## Configuration Defaults

| Setting | Default | Notes |
|---|---|---|
| OCR | `do_ocr=False` | Opt-in only — enable explicitly when OCR is needed |
| Chunker | `HybridChunker` with `BAAI/bge-m3` | Always use this; do not swap the tokenizer |
| Page metadata | `page_range` mandatory for PDFs | Required field — do not omit |
