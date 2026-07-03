# src/ingestion/unified/

Stateless unified ingestion pipeline.

## Purpose

Idempotent document ingestion with stable file identity and hybrid vector
writes to Qdrant. Runs as a single pass (or a polling watch loop) with **no
external state database** — idempotency lives in Qdrant via a per-point
`metadata.content_hash`.

## How it works

`run_once` scans `sync_dir` → for each supported file: compute `content_hash`
and a stable `file_id` (manifest) → if Qdrant already holds a point for that
`(file_id, content_hash)` the file is **skipped** → otherwise parse via Docling,
embed via BGE-M3, and upsert into Qdrant. Upsert uses deterministic point ids
(atomic replace) so a *changed* file is re-ingested correctly and stale chunks
are swept.

## Entrypoints

| Entrypoint | Role |
|------------|------|
| [`cli.py`](./cli.py) `main()` | CLI: `run`, `run --watch`, `preflight`, `bootstrap`, `schema-check`, `coverage-check`, `backfill-colbert` |
| [`flow.py`](./flow.py) `run_once()` | Single-pass, stateless, idempotent ingestion |
| [`flow.py`](./flow.py) `run_watch()` | Continuous polling loop over `run_once` |
| [`qdrant_writer.py`](./qdrant_writer.py) `QdrantHybridWriter.upsert_chunks_sync()` | Atomic-replace upsert of a file's chunks |

## Key Files

| File | Purpose |
|------|---------|
| [`config.py`](./config.py) | `UnifiedConfig` — paths, Qdrant, Docling, BGE-M3 settings |
| [`flow.py`](./flow.py) | Stateless scan → parse → embed → Qdrant upsert with content-hash dedup |
| [`manifest.py`](./manifest.py) | `FileManifest` — content-hash → stable UUID mapping (rename/move safe) |
| [`qdrant_writer.py`](./qdrant_writer.py) | Batch hybrid upserts and per-file delete/replace |
| [`colbert_backfill.py`](./colbert_backfill.py) | Backfill ColBERT multivectors for existing chunks |

## Boundaries

- **Deterministic identity**: `manifest.py` uses `content_hash` as the primary key. Renamed or moved files reuse the same `file_id` and do not create duplicates.
- **Idempotency**: a file whose `(file_id, content_hash)` already exists in Qdrant is skipped; there is no separate state store.
- **Replace semantics**: re-ingesting a changed file deletes the prior version's points by `source_path` and upserts new chunks (deterministic ids), so no stale chunks survive a content change.
- **Deleted source files (known limitation)**: removing a file from `sync_dir` does **not** delete its chunks from Qdrant. There is no scan for vanished sources; orphaned points remain until manual cleanup. Use `QdrantHybridWriter.delete_file_sync`/`delete_by_source_path_sync` out-of-band to remove them.
- **Payload contract**: `qdrant_writer.py` writes a consistent payload schema expected by retrieval. Changing fields here requires a coordinated change in `telegram_bot/services/qdrant.py` and `src/retrieval/`.
- **Do not change hashing or collection semantics** without a migration plan; downstream retrieval and history depend on stable point identities.

## Related Runtime Services

- **Qdrant** — vector database target (also the source of truth for idempotency)
- **BGE-M3** — local dense + sparse + ColBERT embeddings
- **Docling** — document parsing (in-process via `docling_native` backend; `DOCLING_BACKEND` only accepts `docling_native`)

## Focused Checks

```bash
# Create the Qdrant collection if missing
python -m src.ingestion.unified.cli bootstrap

# Check dependencies are reachable
python -m src.ingestion.unified.cli preflight

# Run once
python -m src.ingestion.unified.cli run

# Watch mode (polling loop)
python -m src.ingestion.unified.cli run --watch

# Tests
make test-ingest-extra
make check
```

## See Also

- [`../README.md`](../README.md) — Ingestion overview
- [`../../../docs/engineering/test-writing-guide.md`](../../../docs/engineering/test-writing-guide.md) — Test conventions
