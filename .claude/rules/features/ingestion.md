---
paths: "src/ingestion/**"
---

# Document Ingestion

Parsing, chunking, and indexing documents into Qdrant.

## Purpose

Convert PDF/DOCX/CSV/Google Drive documents into searchable vector embeddings in Qdrant.

## Architecture (CocoIndex Pipeline)

```
Google Drive / Local Files
        │
        ▼ (CocoIndex: 60s polling)
┌───────────────────────────────────────────┐
│ IngestionService (src/ingestion/service.py) │
│ State: Postgres (cocoindex database)        │
└───────────────────────────────────────────┘
        │
        ▼
docling-serve (PDF, DOCX, etc.) → TokenChunker (512 tokens)
        │
        ▼
Voyage API (batched, 100 chunks/request)
        │
        ▼ Replace semantics
Qdrant (DELETE by file_id → UPSERT new chunks)
```

## Quick Commands

```bash
# Unified Pipeline v3.2.1 (recommended)
make ingest-unified           # Run once
make ingest-unified-watch     # Continuous (FlowLiveUpdater)
make ingest-unified-status    # Show stats from Postgres
make ingest-unified-reprocess # Retry failed files

# Legacy commands
make ingest-gdrive-run        # Old GDrive flow
```

## Unified Pipeline v3.2.1 (Feb 2026)

**Architecture:**
```
rclone sync → GDRIVE_SYNC_DIR
     ↓ (CocoIndex poll)
sources.LocalFile → QdrantHybridTarget (custom)
     ├─ DoclingClient (chunking)
     ├─ VoyageService (dense 1024)
     ├─ FastEmbed BM42 (sparse)
     ├─ Qdrant (delete + upsert)
     └─ Postgres (state + DLQ)
```

**Key Files:**

| File | Description |
|------|-------------|
| `src/ingestion/unified/config.py` | UnifiedConfig dataclass |
| `src/ingestion/unified/state_manager.py` | Postgres state + DLQ |
| `src/ingestion/unified/qdrant_writer.py` | Payload contract writer |
| `src/ingestion/unified/targets/qdrant_hybrid_target.py` | CocoIndex custom target |
| `src/ingestion/unified/flow.py` | CocoIndex flow definition |
| `src/ingestion/unified/cli.py` | CLI: run, status, reprocess |

**Payload Contract (required):**
```python
{
    "page_content": str,       # Chunk text
    "metadata": {
        "file_id": str,        # sha256(rel_path)[:16]
        "doc_id": str,         # = file_id (for small-to-big)
        "order": int,          # Chunk order
        "source": str,         # Relative path
    },
    "file_id": str,            # Flat for fast delete
}
```

**Docker Service:**
```bash
docker compose -f docker-compose.dev.yml up -d ingestion
docker logs dev-ingestion -f
```

## Legacy Files

| File | Description |
|------|-------------|
| `src/ingestion/docling_client.py` | Docling API client (httpx async) |
| `src/ingestion/gdrive_flow.py` | Google Drive ingestion flow |
| `src/ingestion/voyage_indexer.py` | Legacy VoyageIndexer |
| `telegram_bot/services/ingestion_cocoindex.py` | CLI wrapper |

## Legacy Architecture

```
Document → Parser (PyMuPDF/Docling) → Chunker (semantic/fixed)
        → VoyageIndexer (dense + BM42 sparse) → Qdrant upsert
```

## Key Files

| File | Line | Description |
|------|------|-------------|
| `src/ingestion/document_parser.py` | 45 | ParserCache |
| `src/ingestion/document_parser.py` | 80+ | UniversalDocumentParser |
| `src/ingestion/chunker.py` | 34 | DocumentChunker |
| `src/ingestion/chunker.py` | 230 | chunk_csv_by_rows() |
| `src/ingestion/voyage_indexer.py` | 47 | VoyageIndexer |

## Parser Selection

| Format | Parser | Speed |
|--------|--------|-------|
| PDF | PyMuPDF | 377x faster than Docling |
| DOCX | Docling | Universal converter |
| CSV | chunk_csv_by_rows() | Row-per-chunk |

## Chunking Strategies

| Strategy | Use Case | Description |
|----------|----------|-------------|
| SEMANTIC | Legal docs | Respects sections, chapters |
| FIXED_SIZE | General | 1024 chars with 256 overlap |
| SLIDING_WINDOW | Dense coverage | Overlapping windows |

## Configuration

| Parameter | Default | Description |
|-----------|---------|-------------|
| `chunk_size` | 1024 | Target chars per chunk |
| `overlap` | 256 | Overlap between chunks |
| `VOYAGE_BATCH_SIZE` | 128 | Texts per API request |

## Common Patterns

### Parse document

```python
from src.ingestion.document_parser import UniversalDocumentParser

parser = UniversalDocumentParser(use_cache=True)
doc = parser.parse_file("document.pdf")
print(doc.content)
```

### Chunk text

```python
from src.ingestion.chunker import DocumentChunker, ChunkingStrategy

chunker = DocumentChunker(
    chunk_size=1024,
    overlap=256,
    strategy=ChunkingStrategy.SEMANTIC,
)

chunks = chunker.chunk_text(
    text=doc.content,
    document_name="legal_code.pdf",
    article_number="doc_001",
)
```

### Chunk CSV (row-per-chunk)

```python
from src.ingestion.chunker import chunk_csv_by_rows

chunks = chunk_csv_by_rows(
    csv_path=Path("properties.csv"),
    document_name="bulgaria_properties",
)
# Each row becomes one chunk with structured metadata
```

### Index to Qdrant

```python
from src.ingestion.voyage_indexer import VoyageIndexer

indexer = VoyageIndexer(
    qdrant_url="http://localhost:6333",
    voyage_api_key=api_key,
    voyage_model="voyage-4-large",
)

stats = await indexer.index_chunks(
    chunks=chunks,
    collection_name="contextual_bulgaria_voyage",
)
print(f"Indexed {stats.indexed_chunks} chunks")
```

## CSV Metadata Extraction

Automatic field mapping:

| CSV Column | Metadata Field | Type |
|------------|----------------|------|
| Название | title | string |
| Город | city | string |
| Цена (€) | price | int |
| Комнат | rooms | int |
| Площадь (м²) | area | float |
| Этаж | floor | int |
| До моря (м) | distance_to_sea | int |

## Parser Cache

MD5-based caching to skip re-parsing:

```python
parser = UniversalDocumentParser(use_cache=True)
# First call: parses and caches
# Second call: returns from .cache/parser/
```

## Qdrant Collection Setup

VoyageIndexer creates collection with:
- Dense vectors: 1024-dim, cosine distance
- Sparse vectors: BM42
- Scalar Int8 quantization (4x compression)

## Dependencies

- Container: `dev-docling` (5001), 4GB RAM
- Voyage API for embeddings
- Qdrant for storage

## Google Drive Ingestion

```bash
# Setup rclone (one time)
rclone config  # Create "gdrive" remote with OAuth

# Sync files
rclone sync gdrive:RAG ~/drive-sync

# Run ingestion
make ingest-gdrive-run
# or: uv run python -m src.ingestion.gdrive_flow --once --sync-dir ~/drive-sync
```

### GDrive Flow Architecture

```
~/drive-sync (rclone) → GDriveFlow → DoclingClient → Voyage → Qdrant
                              ↓
                     .manifest.json (tracks processed files)
```

### GDrive Collections

| Collection | Quantization |
|------------|--------------|
| `gdrive_documents_scalar` | INT8 (default) |
| `gdrive_documents_binary` | Binary (fast) |

## Testing

```bash
# Unified pipeline tests
pytest tests/unit/ingestion/test_payload_contract.py -v
RUN_INTEGRATION_TESTS=1 pytest tests/integration/test_unified_ingestion_e2e.py -v

# Legacy tests
pytest tests/unit/test_chunker.py -v
pytest tests/unit/test_document_parser.py -v
pytest tests/unit/ingestion/test_docling_client.py -v
```

## Troubleshooting

| Error | Fix |
|-------|-----|
| Docling returns 0 chunks | Don't set `tokenizer="word"`, use `None` |
| Voyage 429 | Use CacheService or reduce batch size |
| rclone empty token | `rclone config reconnect gdrive:` |
| Ingestion stalled | Check `make ingest-unified-status` |
| Files in DLQ | `make ingest-unified-reprocess` |
| Missing payload fields | Check `test_payload_contract.py` |

## Development Guide

### Adding new document format

1. Add parser method to `UniversalDocumentParser`
2. Update `parse_file()` extension detection
3. Add tests with sample document

### Adding new chunking strategy

1. Add to `ChunkingStrategy` enum
2. Implement `_chunk_new_strategy()` method
3. Add case to `chunk_text()`
