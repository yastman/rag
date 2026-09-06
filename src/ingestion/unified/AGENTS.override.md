# Unified ingestion

Applies to src/ingestion/unified/**; extends [root AGENTS](../../../AGENTS.md).

- Preserve deterministic identity, manifest semantics, and idempotent writes.
- flow.py and qdrant_writer.py must agree on sync-safe write behavior.
- Do not silently alter collection names, file hashing, or identity semantics.
- Preserve defaults when adding configuration.
- Removing a source from sync_dir does not delete its Qdrant chunks. No vanished-source scan
  exists; cleanup uses explicit delete_file_sync/delete_by_source_path_sync operations.
- Supported formats and ingestion behavior are owned by [INGESTION.md](../../../docs/INGESTION.md).

## Checks

Run `make check` and `make test-ingestion`.
For behavior changes, run `uv run --no-sync python -m src.ingestion.unified.cli preflight`.
For flow changes, use one controlled development ingestion:
`uv run --no-sync python -m src.ingestion.unified.cli run`.
Confirm the target directory/collection first; a documentation edit does not require a live write.

Use [local setup](../../../docs/LOCAL-DEVELOPMENT.md) and [CLI](cli.py) for supported commands.
