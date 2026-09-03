# Ingestion

How documents get from a source file into the Qdrant store the RAG spine retrieves from.
The deterministic, idempotent, production path lives in `src/ingestion/unified/` — see
[`../src/ingestion/README.md`](../src/ingestion/README.md) and
[`../src/ingestion/unified/AGENTS.override.md`](../src/ingestion/unified/AGENTS.override.md).

## Pipeline

```
source file (.md) → MarkdownParser (stdlib, in-process) → chunk + embed (BGE-M3: dense + sparse + ColBERT) → Qdrant upsert
```

## Markdown-only authority (#3235)

**Production ingestion accepts exactly `.md`.** When in doubt, this section is the
authority.

- The supported production extension set is `{".md"}` — enforced by
  `UnifiedConfig.supported_extensions` and the parser suffix gate
  (`tests/contract/test_markdown_only_ingestion_contract.py`).
- Parsing is stdlib-only: strict UTF-8 read, deterministic heading/size splitting
  (`src/ingestion/markdown.py`). No converter SDK, no model downloads, no OCR.
- **Prohibited** — do not reintroduce: `docling`, `docling-core`, `docling-serve`,
  `DOCLING_URL`, `DOCLING_BACKEND`, `fastembed`, `transformers`, `torch`,
  `torchvision` in the root dependency graph, or any converter-sidecar service.
- The `docling-native` pyproject extra is removed; the ingestion image installs the
  lean base dependencies only.

## Guarantees

- **SHA256 file identity** — re-ingesting an unchanged file is a no-op.
- **Idempotent upsert** — a changed file replaces its prior chunks by source path.
- **Error handling** — failed documents are logged and skipped; `run_watch` retries on the next polling cycle (60 s). No DLQ, no exponential backoff.

**Known limitation:** deleting a source file does **not** remove its chunks from Qdrant;
they remain until manual cleanup.

## Operational boundary

The repository cannot prove the suffixes inside an external `GDRIVE_SYNC_DIR` or the
points already stored in a production Qdrant collection. Before deploying this change,
perform a read-only inventory; if non-Markdown sources or points exist, run a separate
operational migration (snapshot, explicit conversion/removal decisions, rebuild,
validation, rollback). Do not silently delete external data.

## Run it

```bash
make core-up          # BGE-M3 + Qdrant must be up (see ../docs/LOCAL-DEVELOPMENT.md)
```

Ingestion entry points and scripts live under `scripts/` (see
[`../scripts/README.md`](../scripts/README.md)) and `src/ingestion/`. Qdrant collection
setup/audit: `make qdrant-audit-indexes`.
