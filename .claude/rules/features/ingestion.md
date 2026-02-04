---
paths: "src/ingestion/**"
---

# Document Ingestion

Parsing, chunking, and indexing documents into Qdrant via CocoIndex unified pipeline.

## Quick Commands

```bash
make ingest-unified           # Run once
make ingest-unified-watch     # Continuous (FlowLiveUpdater)
make ingest-unified-status    # Show stats from Postgres
make ingest-unified-reprocess # Retry failed files
```

## Architecture (v3.2.1)

```
Google Drive → rclone sync → ~/drive-sync/
     ↓ (CocoIndex FlowLiveUpdater)
sources.LocalFile → QdrantHybridTarget (custom connector)
     ├─ DoclingClient.chunk_file_sync()
     ├─ VoyageService (dense 1024-dim)
     ├─ FastEmbed BM42 (sparse)
     ├─ QdrantHybridWriter.*_sync()
     └─ StateManager.*_sync() → Postgres
```

### rclone Setup

```bash
# Configure (one-time)
rclone config  # Create 'gdrive' remote

# Manual sync
rclone sync gdrive:RAG-Documents ~/drive-sync/ --progress

# Cron (every 5 min)
*/5 * * * * rclone sync gdrive:RAG-Documents ~/drive-sync/ -q
```

## Key Files

| File | Description |
|------|-------------|
| `src/ingestion/unified/flow.py` | CocoIndex flow definition |
| `src/ingestion/unified/targets/qdrant_hybrid_target.py` | Custom target (pure sync) |
| `src/ingestion/unified/qdrant_writer.py` | Qdrant writer with sync methods |
| `src/ingestion/unified/state_manager.py` | Postgres state + DLQ + sync methods |
| `src/ingestion/unified/cli.py` | CLI: run, status, reprocess |
| `src/ingestion/docling_client.py` | Docling API client + chunk_file_sync() |

## Sync Execution Pattern

CocoIndex calls `mutate()` synchronously. All operations must be sync:

```python
# Target connector uses *_sync() methods:
state_manager.should_process_sync(file_id, content_hash)
docling.chunk_file_sync(abs_path)
writer.upsert_chunks_sync(chunks, file_id, ...)
state_manager.mark_indexed_sync(file_id, chunk_count, content_hash)
```

**Constraint:** NO `asyncio.run()` in mutate() — causes event loop conflicts.

## Payload Contract

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

## Collections

| Collection | Quantization |
|------------|--------------|
| `gdrive_documents_scalar` | INT8 (default) |
| `gdrive_documents_binary` | Binary (fast) |

## Testing

```bash
pytest tests/unit/ingestion/test_target_sync_execution.py -v  # Sync pattern
pytest tests/unit/ingestion/test_state_manager_sync.py -v     # StateManager sync
pytest tests/unit/ingestion/test_payload_contract.py -v       # Payload structure
pytest tests/unit/ingestion/test_cocoindex_init.py -v         # Init settings
RUN_INTEGRATION_TESTS=1 pytest tests/integration/test_unified_ingestion_e2e.py -v
```

## Troubleshooting

| Error | Fix |
|-------|-----|
| Docling returns 0 chunks | Don't set `tokenizer="word"`, use `None` |
| Voyage 429 | Use CacheService or reduce batch size |
| `Event loop is closed` | StateManager resets pool between sync calls |
| `asyncio.run()` nested | Use `*_sync()` methods in mutate() |
| Missing payload fields | Check `test_payload_contract.py` |
| Files in DLQ | `make ingest-unified-reprocess` |

## E2E Verification

```bash
# 1. Sync from Google Drive
rclone sync gdrive:RAG-Documents ~/drive-sync/ --progress

# 2. Run ingestion
make ingest-unified

# 3. Check status
make ingest-unified-status  # Should show "indexed: N (100%)"

# 4. Verify Qdrant
curl -s localhost:6333/collections/gdrive_documents_scalar | jq '.result.points_count'
```

## Legacy (deprecated)

Legacy files in `src/ingestion/` (gdrive_flow.py, voyage_indexer.py) are superseded by unified pipeline.
