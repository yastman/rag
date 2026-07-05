# src/ingestion/

Document ingestion: parsing, chunking, embedding, and indexing into Qdrant.

## Purpose

Turn raw documents (PDF, DOCX, CSV, etc.) into searchable vector chunks. Two paths exist:

1. **Current path** (`unified/`) — incremental pipeline with deterministic file identity (content-hash manifest) and replace semantics. CocoIndex was removed (#2834); the pipeline now drives Docling → BGE-M3 → Qdrant directly.
2. **Legacy local wrappers** (`chunker.py`, `indexer.py`, `service.py`) — standalone helpers retained for compatibility; deprecated GDrive-specific modules were retired in favor of `unified/`.

## Entrypoints

| Entrypoint | Role |
|------------|------|
| `src.ingestion.service` | High-level service for directory ingestion (legacy wrapper) |
| `src.ingestion.unified.cli` | Unified pipeline CLI: `run` (+`--watch`), `preflight`, `bootstrap`, `schema-check`, `coverage-check`, `backfill-colbert` |
| `src.ingestion.unified.flow` `run_once()` / `run_watch()` | Pipeline assembly and execution (reads `SYNC_DIR`) |
| `src.ingestion.unified.qdrant_writer` `QdrantHybridWriter` | Writes hybrid vectors (dense + sparse + ColBERT) to Qdrant |

## Key Files

| File | Purpose |
|------|---------|
| [`chunker.py`](./chunker.py) | Document chunking strategies (fixed, semantic, sliding window) |
| [`hybrid_chunker.py`](./hybrid_chunker.py) | Token-aware hybrid chunking helper |
| [`document_parser.py`](./document_parser.py) | Docling-based document parsing |
| [`docling_common.py`](./docling_common.py) | Shared Docling contract (DoclingChunk, SUPPORTED_FORMATS, to_ingestion_chunks) |
| [`docling_native.py`](./docling_native.py) | In-process Docling backend (NativeDoclingAdapter, HybridChunker) |
| [`unified/config.py`](./unified/config.py) | Unified pipeline configuration |
| [`unified/flow.py`](./unified/flow.py) | Pipeline definition (`run_once` / `run_watch`) |
| [`unified/manifest.py`](./unified/manifest.py) | Content-hash-based stable file identity |
| [`unified/qdrant_writer.py`](./unified/qdrant_writer.py) | Qdrant upsert/delete with payload contract |
| [`unified/colbert_backfill.py`](./unified/colbert_backfill.py) | Backfill ColBERT vectors for existing points |

## Boundaries

- **Ingestion determinism and resumability** are critical. File identity uses content hashes (`manifest.py`); renames/moves do not create duplicates.
- **Do not change collection schema**, manifest hashing, or payload contract without updating downstream retrieval assumptions.
- `QdrantHybridWriter` enforces replace semantics: a file re-ingestion deletes old chunks before inserting new ones.

## Related Runtime Services

- **Qdrant** — target vector database (also the source of truth for idempotency via the content-hash manifest)
- **BGE-M3** — dense + sparse + ColBERT embeddings
- **Docling** — document parsing (in-process `docling_native` backend via `docling-native` extra)

## Focused Checks

```bash
# Check dependencies are reachable (Qdrant, BGE-M3, Docling, sync dir)
python -m src.ingestion.unified.cli preflight

# Create the Qdrant collection if missing
python -m src.ingestion.unified.cli bootstrap

# Validate collection schema (dense / bm42 / colbert)
python -m src.ingestion.unified.cli schema-check

# Tests
pytest src/ingestion/unified/
make check
```

## See Also

- [`./unified/AGENTS.override.md`](./unified/AGENTS.override.md) — Ingestion-specific scope rules and validation
- [`./unified/README.md`](./unified/README.md) — Detailed unified pipeline docs
- [`../retrieval/`](../retrieval/) — Search engines that consume ingested data
- [`../../DOCKER.md`](../../DOCKER.md) — Docker orchestration and service dependencies
- [`../../docs/LOCAL-DEVELOPMENT.md`](../../docs/LOCAL-DEVELOPMENT.md) — Local setup and validation ladder
- [`../../docs/runbooks/README.md`](../../docs/runbooks/README.md) — Operational troubleshooting
- [`../../docs/INGESTION.md`](../../docs/INGESTION.md) — Unified ingestion guide and troubleshooting
- [`../../docs/engineering/test-writing-guide.md`](../../docs/engineering/test-writing-guide.md) — Test conventions
