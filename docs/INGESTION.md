# Ingestion

This project currently uses a unified CocoIndex-based ingestion pipeline as the primary path.

## Primary Runtime

- Package: `src/ingestion/unified/`
- CLI entrypoint: `python -m src.ingestion.unified.cli`
- Pipeline version in code: `v3.2.1`

## What The Pipeline Does

1. Reads files from `GDRIVE_SYNC_DIR` (LocalFile source).
2. Computes stable file identity via manifest/content hash.
3. Parses and chunks files through Docling.
4. Generates embeddings:
   - default: local BGE-M3 (`USE_LOCAL_DENSE_EMBEDDINGS=true`)
   - optional: Voyage dense + BGE-M3 sparse
5. Upserts/deletes points in Qdrant.
6. Tracks file state/retries/DLQ in PostgreSQL.

## Core Commands

```bash
# Validate dependencies, env, and source directory
make ingest-unified-preflight

# Create or validate the runtime collection schema
make ingest-unified-bootstrap

# One-shot run
make ingest-unified

# Continuous watch mode
make ingest-unified-watch

# State/DLQ status
make ingest-unified-status

# Reprocess files in error state
make ingest-unified-reprocess

# Container logs
make ingest-unified-logs
```

Direct CLI equivalents:

```bash
uv run python -m src.ingestion.unified.cli preflight
uv run python -m src.ingestion.unified.cli bootstrap
uv run python -m src.ingestion.unified.cli run --watch
uv run python -m src.ingestion.unified.cli status
uv run python -m src.ingestion.unified.cli reprocess --errors
```

## Langfuse Trace Contract

- CLI root spans:
  - `ingestion-cli-run`
  - `ingestion-cli-preflight`
- Runtime stage spans:
  - `ingestion-flow-run-once`
  - `ingestion-flow-watch`
  - `ingestion-qdrant-upsert-chunks`
  - `ingestion-qdrant-delete-file`

Validate coverage together with API/voice traces:

```bash
make validate-traces-fast
```

## Required Environment Variables

- `INGESTION_DATABASE_URL`
- `QDRANT_URL`
- `DOCLING_URL`
- `BGE_M3_URL`

Commonly used:
- `GDRIVE_SYNC_DIR`
- `GDRIVE_COLLECTION_NAME`
- `RCLONE_CONFIG_FILE`
- `RCLONE_REMOTE`
- `USE_LOCAL_DENSE_EMBEDDINGS`
- `BGE_M3_TIMEOUT`
- `BGE_M3_CONCURRENCY`
- `MANIFEST_DIR`

## Docker Service

`docker-compose.dev.yml` includes `ingestion` service under profile `ingest`.

```bash
make docker-ingest-up
make ingest-unified-logs
```

The service mounts `GDRIVE_SYNC_DIR` into `/data/drive-sync` with fail-fast bind-mount semantics.
If the host path is missing, `docker compose` now fails instead of silently creating an empty directory.

## Legacy Commands

`make ingest-gdrive` is deprecated. Use unified ingestion commands above for active development.

## Troubleshooting

- `preflight` fails on Qdrant: confirm collection exists or run `bootstrap`.
- `preflight` fails on sync dir: confirm `GDRIVE_SYNC_DIR` exists, is a directory, and contains supported files.
- `status` shows only errors: run `reprocess --errors`, then inspect Docling/BGE-M3 logs.
- No files processed: verify `GDRIVE_SYNC_DIR` mount/path and allowed file extensions.
- Collection exists but has `0 points`: verify the Google Drive sync host path is populated before debugging Qdrant.
