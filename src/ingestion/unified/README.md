# src/ingestion/unified/

CocoIndex-based unified ingestion pipeline.

## Purpose

Incremental, resumable document ingestion with stable file identity and hybrid vector writes to Qdrant. Replaces the legacy `gdrive_flow.py` and standalone indexer scripts.

## Entrypoints

| Entrypoint | Role |
|------------|------|
| [`cli.py`](./cli.py) `main()` | CLI: `run`, `run --watch`, `backfill-colbert`, `status`, `preflight` |
| [`flow.py`](./flow.py) `build_flow()` | Assemble the CocoIndex flow for a given config |
| [`flow.py`](./flow.py) `run_once()` | Single-pass ingestion |
| [`flow.py`](./flow.py) `run_watch()` | Continuous watch mode via `FlowLiveUpdater` |
| [`qdrant_writer.py`](./qdrant_writer.py) `QdrantHybridWriter.write_file()` | Write a single file's chunks to Qdrant |

## Key Files

| File | Purpose |
|------|---------|
| [`config.py`](./config.py) | `UnifiedConfig` — paths, Qdrant, Docling, BGE-M3/Voyage settings |
| [`flow.py`](./flow.py) | CocoIndex flow: LocalFile source → transforms → QdrantHybridTarget |
| [`manifest.py`](./manifest.py) | `GDriveManifest` — content-hash → stable UUID mapping (rename/move safe) |
| [`qdrant_writer.py`](./qdrant_writer.py) | Batch hybrid upserts and per-file delete/replace |
| [`state_manager.py`](./state_manager.py) | File state tracking for resume and idempotency |
| [`colbert_backfill.py`](./colbert_backfill.py) | Backfill ColBERT multivectors for existing chunks |
| [`targets/qdrant_hybrid_target.py`](./targets/qdrant_hybrid_target.py) | Custom CocoIndex target connector |

## Boundaries

- **Deterministic identity**: `manifest.py` uses `content_hash` as the primary key. Renamed or moved files reuse the same `file_id` and do not create duplicates.
- **Replace semantics**: re-ingesting a file deletes its old chunks (by `file_id`) before inserting new ones.
- **Payload contract**: `qdrant_writer.py` writes a consistent payload schema expected by retrieval. Changing fields here requires a coordinated change in `telegram_bot/services/qdrant.py` and `src/retrieval/`.
- **Do not change hashing or collection semantics** without a migration plan; downstream retrieval and history depend on stable point identities.

## Related Runtime Services

- **Qdrant** — vector database target
- **PostgreSQL** — CocoIndex flow state (`INGESTION_DATABASE_URL`)
- **BGE-M3** — local dense + sparse embeddings (default)
- **Voyage** — cloud dense embeddings (optional, `USE_LOCAL_DENSE_EMBEDDINGS=false`)
- **Docling** — document parsing (`DOCLING_BACKEND`: `docling_http` or `docling_native`)

## Focused Checks

```bash
# Run once (dry-run)
python -m src.ingestion.unified.cli run --dry-run

# Watch mode
python -m src.ingestion.unified.cli run --watch

# Backfill ColBERT vectors
python -m src.ingestion.unified.cli backfill-colbert

# Tests
pytest src/ingestion/unified/
make check
```

## See Also

- [`../README.md`](../README.md) — Ingestion overview
- [`../../../docs/engineering/test-writing-guide.md`](../../../docs/engineering/test-writing-guide.md) — Test conventions
