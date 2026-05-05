# src/ingestion/

Document ingestion: parsing, chunking, embedding, and indexing into Qdrant.

## Purpose

Turn raw documents (PDF, DOCX, CSV, etc.) into searchable vector chunks. Two paths exist:

1. **Legacy path** (`chunker.py`, `indexer.py`, `gdrive_flow.py`) — standalone scripts, being phased out.
2. **Current path** (`unified/`) — CocoIndex-based incremental pipeline with deterministic file identity and replace semantics.

## Entrypoints

| Entrypoint | Role |
|------------|------|
| `src.ingestion.service` | High-level service for directory and Google Drive ingestion (legacy wrapper) |
| `src.ingestion.unified.cli` | Unified pipeline CLI: `run`, `watch`, `backfill`, `status` |
| `src.ingestion.unified.flow` `build_flow()` / `run_once()` / `run_watch()` | CocoIndex flow assembly and execution |
| `src.ingestion.unified.qdrant_writer` `QdrantHybridWriter` | Writes hybrid vectors (dense + sparse + ColBERT) to Qdrant |

## Key Files

| File | Purpose |
|------|---------|
| [`chunker.py`](./chunker.py) | Document chunking strategies (fixed, semantic, sliding window) |
| [`document_parser.py`](./document_parser.py) | Docling-based document parsing |
| [`service.py`](./service.py) | Legacy ingestion service wrapper |
| [`unified/config.py`](./unified/config.py) | Unified pipeline configuration |
| [`unified/flow.py`](./unified/flow.py) | CocoIndex flow definition |
| [`unified/manifest.py`](./unified/manifest.py) | Content-hash-based stable file identity |
| [`unified/qdrant_writer.py`](./unified/qdrant_writer.py) | Qdrant upsert/delete with payload contract |
| [`unified/state_manager.py`](./unified/state_manager.py) | Ingestion state and resume tracking |
| [`unified/targets/qdrant_hybrid_target.py`](./unified/targets/qdrant_hybrid_target.py) | Custom CocoIndex target connector |

## Boundaries

- **Ingestion determinism and resumability** are critical. File identity uses content hashes (`manifest.py`); renames/moves do not create duplicates.
- **Do not change collection schema**, manifest hashing, or payload contract without updating downstream retrieval assumptions.
- `QdrantHybridWriter` enforces replace semantics: a file re-ingestion deletes old chunks before inserting new ones.

## Related Runtime Services

- **Qdrant** — target vector database
- **PostgreSQL** — CocoIndex flow state database
- **BGE-M3** — dense + sparse embeddings (or Voyage when configured)
- **Docling** — document parsing (HTTP or native backend)

## Focused Checks

```bash
# Unified pipeline dry-run
python -m src.ingestion.unified.cli run --dry-run

# Status check
python -m src.ingestion.unified.cli status

# Tests
pytest src/ingestion/unified/
make check
```

## See Also

- [`./unified/README.md`](./unified/README.md) — Detailed unified pipeline docs
- [`../retrieval/`](../retrieval/) — Search engines that consume ingested data
- [`../../docs/engineering/test-writing-guide.md`](../../docs/engineering/test-writing-guide.md) — Test conventions
