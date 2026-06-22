# Ingestion

The unified ingestion pipeline (`src/ingestion/unified/`) processes documents from a local directory into Qdrant using BGE-M3 embeddings. It is deterministic, idempotent, and production-ready.

## Key Properties

- **SHA256-based identity**: re-ingesting the same file content is a no-op (content hash → stable UUID → skip if unchanged).
- **Idempotent upsert**: old chunks for a file are deleted before new ones are written. Deleted source files are cleaned from Qdrant automatically.
- **Dead-letter queue (DLQ)**: failed documents are tracked in PostgreSQL with retry and backoff via the state manager.
- **Watch mode**: polls the source directory on a configurable interval (default 60s).
- Pipeline version: `v3.2.1`.

## Quick Start

```bash
# Start services (Qdrant + BGE-M3 + PostgreSQL + Docling)
make local-up-ingest

# Create the collection schema (once, or after collection reset)
make ingest-unified-bootstrap

# Run once
make ingest-unified

# Continuous watch
make ingest-unified-watch

# Status
make ingest-unified-status
```

## CLI Commands

All commands run via `python -m src.ingestion.unified.cli <command>`.

| Make target | CLI command | Description |
|---|---|---|
| `make ingest-unified-preflight` | `preflight` | Check config, source dir, service connectivity |
| `make ingest-unified-bootstrap` | `bootstrap --require-colbert` | Create/validate Qdrant collection schema |
| `make ingest-unified` | `run` | Single-pass ingestion |
| `make ingest-unified-watch` | `run --watch` | Continuous polling |
| `make ingest-unified-status` | `status` | Show collection stats and DLQ |
| `make ingest-unified-reprocess` | `reprocess --errors` | Retry all DLQ documents |
| `make ingest-unified-logs` | — | Tail ingestion container logs |

## Configuration

Configure via environment variables (see `.env.example`):

| Variable | Default | Description |
|---|---|---|
| `SYNC_DIR` / `GDRIVE_SYNC_DIR` | `~/drive-sync` | Source document directory |
| `MANIFEST_DIR` | same as `SYNC_DIR` | Directory for content-hash manifest |
| `INGESTION_DATABASE_URL` | — | PostgreSQL URL for state/DLQ tracking |
| `QDRANT_URL` | `http://localhost:6333` | Qdrant endpoint |
| `GDRIVE_COLLECTION_NAME` / `COLLECTION_NAME` | `gdrive_documents_bge` | Target Qdrant collection |
| `DOCLING_URL` | `http://localhost:5001` | Docling document parser endpoint |
| `DOCLING_BACKEND` | `docling_http` | `docling_http` or `docling_native` |
| `BGE_M3_URL` | `http://localhost:8000` | BGE-M3 embeddings service endpoint |
| `BGE_M3_TIMEOUT` | `300` | BGE-M3 request timeout (seconds) |
| `BGE_M3_CONCURRENCY` | `1` | Parallel embedding requests |

## Supported File Types

`.pdf`, `.docx`, `.doc`, `.xlsx`, `.pptx`, `.md`, `.txt`, `.html`, `.htm`, `.csv`

Docling handles PDF and Office formats. Markdown/text/HTML/CSV are parsed directly.

## Pipeline Architecture

```
Source dir (SYNC_DIR)
        │
        ▼
FilePollingChangeManager     detect added/modified/deleted files
        │                    by comparing SHA256 hash vs manifest
        ▼
UnifiedIngestionOrchestrator  orchestrate per-file mutations
        │
        ├── DoclingClient    parse document → text chunks
        │
        ├── BGE-M3 API       embed: dense (1024-dim) + sparse (BM42) + ColBERT
        │
        ├── QdrantHybridWriter  delete old chunks, upsert new points
        │
        └── UnifiedStateManager  record status in PostgreSQL DLQ table
```

## Payload Contract

Each Qdrant point written by ingestion has this payload structure:

```json
{
  "page_content": "<chunk text>",
  "metadata": {
    "doc_id":   "<file_id>",
    "order":    0,
    "source":   "<relative source path>",
    "file_id":  "<sha256-derived UUID>"
  },
  "file_id": "<sha256-derived UUID>"
}
```

`file_id` is stored flat at top level for fast delete-by-filter operations.

## Vector Names

| Name | Type | Dimensions | Purpose |
|---|---|---|---|
| `dense` | Dense | 1024 | Semantic similarity (BGE-M3) |
| `bm42` | Sparse | — | BM42 term-frequency (BGE-M3 sparse) |
| `colbert` | Multivector | 1024 × tokens | Late-interaction reranking |

The `bm42` name is fixed for backward compatibility with existing collections.

## State Manager / DLQ

The PostgreSQL state table tracks:

- `file_id` — content-hash-derived stable ID
- `source_path` — original file path
- `status` — `indexed` | `error` | `deleted`
- `content_hash` — prevents re-ingestion of unchanged files
- `embedding_model`, `pipeline_version`, `chunk_count` — provenance
- `error_message`, `retry_count` — DLQ fields

```bash
make ingest-unified-status      # show counts per status
make ingest-unified-reprocess   # requeue all error entries
```

## Compose Service

The `ingestion` Compose service uses profile `ingest` or `full`:

```bash
make docker-ingest-up     # start ingestion + docling + dependencies
make ingest-unified-logs  # docker compose logs ingestion -f --tail 100
```

The service mounts `GDRIVE_SYNC_DIR` read-only at `/data/drive-sync` and writes the manifest to the `ingestion-manifest` volume.
