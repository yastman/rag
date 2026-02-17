# Document Ingestion Pipeline

Production-ready pipeline for ingesting documents from local directories and Google Drive into Qdrant.

## Overview

The ingestion pipeline uses CocoIndex for document processing with:
- **CocoIndex IngestionPipeline** — Document loading, chunking, embedding
- **Voyage AI** — High-quality embeddings (voyage-4-large, 1024-dim)
- **Qdrant** — Vector storage with hybrid search (dense + BM42 sparse)
- **Postgres** — Ingestion state tracking (optional)

## Architecture

```
Local Directory / Google Drive
            │
            ▼
┌───────────────────────────────────────────┐
│  CocoIndex Flow                            │
│  - LocalFile source                        │
│  - SplitRecursively (512 tokens, 50 overlap)│
│  - VoyageEmbedFunction (voyage-4-large)    │
└───────────────────────────────────────────┘
            │
            ▼
┌───────────────────────────────────────────┐
│  Qdrant Target                             │
│  - Dense vectors: voyage-4-large (1024-dim)│
│  - Cosine similarity                       │
│  - Incremental updates                     │
└───────────────────────────────────────────┘
```

## Quick Start

```bash
# 1. Setup Qdrant collection with payload indexes
make ingest-setup

# 2. Ingest from local directory
make ingest-dir DIR=path/to/documents

# 3. Or ingest from Google Drive
export GOOGLE_SERVICE_ACCOUNT_KEY=path/to/credentials.json
make ingest-gdrive FOLDER_ID=your_folder_id

# 4. Check status
make ingest-status
```

## Supported Formats

| Format | Source | Notes |
|--------|--------|-------|
| PDF | LocalFile | Auto-detected |
| DOCX | LocalFile | Auto-detected |
| MD | LocalFile | Auto-detected |
| TXT | LocalFile | Auto-detected |
| HTML | LocalFile | Auto-detected |
| Google Docs | Not yet supported | Use DoclingClient instead |
| Google Sheets | Not yet supported | Use DoclingClient instead |

## Configuration

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `QDRANT_URL` | `http://localhost:6333` | Qdrant server URL |
| `QDRANT_API_KEY` | - | Qdrant API key (optional) |
| `VOYAGE_API_KEY` | - | Voyage AI API key (required) |
| `QDRANT_COLLECTION` | `contextual_bulgaria_voyage` | Target collection |
| `GOOGLE_SERVICE_ACCOUNT_KEY` | - | Path to GDrive service account JSON |

### Chunking Parameters

| Parameter | Value | Description |
|-----------|-------|-------------|
| `chunk_size` | 512 | Tokens per chunk |
| `chunk_overlap` | 50 | Overlap between chunks |

## Makefile Targets

```bash
make ingest-setup    # Setup Qdrant collection with indexes
make ingest-dir      # Ingest from directory (DIR=path)
make ingest-gdrive   # Ingest from Google Drive (FOLDER_ID=xxx)
make ingest-status   # Show collection statistics
make ingest-test     # Run ingestion unit tests
```

## Python API

### Basic Usage

```python
from telegram_bot.services.ingestion_cocoindex import (
    CocoIndexIngestionService,
    ingest_from_directory,
    ingest_from_gdrive,
    get_ingestion_status,
)

# Convenience functions
stats = await ingest_from_directory("/path/to/docs")
stats = await ingest_from_gdrive("folder_id")
status = await get_ingestion_status()
```

### Service Class

```python
service = CocoIndexIngestionService(
    qdrant_url="http://localhost:6333",
    voyage_api_key="your-api-key",
    collection_name="my_collection",
)

# Ingest directory
stats = await service.ingest_directory(Path("/path/to/docs"))

# Ingest Google Drive
stats = await service.ingest_gdrive("folder_id")

# Get stats
collection_stats = await service.get_collection_stats()

# Cleanup
await service.close()
```

### Ingestion Stats

```python
@dataclass
class CocoIndexIngestionStats:
    total_documents: int = 0
    total_nodes: int = 0
    indexed_nodes: int = 0
    skipped_nodes: int = 0
    duration_seconds: float = 0.0
    errors: list[str] = []
```

## Postgres State Tracking (Optional)

For advanced state management, use the `cocoindex` database:

```bash
# Database auto-created on Postgres startup
# Tables: ingestion_state, ingestion_dead_letter
```

Schema in `docker/postgres/init/02-cocoindex.sql`.

## Testing

```bash
# Unit tests (no Docker required)
make ingest-test

# Integration tests (requires Docker services)
RUN_INTEGRATION_TESTS=1 pytest tests/integration/test_ingestion_e2e.py -v
```

## Troubleshooting

| Issue | Solution |
|-------|----------|
| Voyage 429 rate limit | Reduce batch size, add delays |
| Qdrant connection refused | `docker compose up -d qdrant` |
| GDrive auth error | Check `GOOGLE_SERVICE_ACCOUNT_KEY` path |
| No documents found | Check directory path, file extensions |

## See Also

- [PIPELINE_OVERVIEW.md](PIPELINE_OVERVIEW.md) — Full RAG pipeline
- [QDRANT_STACK.md](QDRANT_STACK.md) — Vector database details
- [agent-rules/workflow.md](agent-rules/workflow.md) — Codex workflow
- [agent-rules/testing-and-validation.md](agent-rules/testing-and-validation.md) — Validation gates
