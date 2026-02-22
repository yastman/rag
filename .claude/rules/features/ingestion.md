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
Google Drive → rclone sync → ~/drive-sync/ (or /opt/rag-fresh/drive-sync on VPS)
     ↓ (CocoIndex FlowLiveUpdater)
sources.LocalFile → QdrantHybridTarget (custom connector)
     ├─ DoclingClient.chunk_file_sync() (profiles: speed/quality/scan/vlm)
     ├─ BGE-M3 dense 1024-dim (or VoyageService in dev)
     ├─ BGE-M3 sparse /encode/sparse (replaced FastEmbed BM42)
     ├─ Manifest-based file identity (content hash → stable UUID)
     ├─ QdrantHybridWriter.*_sync()
     └─ StateManager.*_sync() → Postgres
```

**CLI commands:** `python -m src.ingestion.unified.cli preflight|bootstrap|run|status|reprocess`

**Embedding providers:**
- **Dev:** VoyageService (API) → `gdrive_documents_scalar`
- **VPS:** BGE-M3 local (`USE_LOCAL_DENSE_EMBEDDINGS=true`) → `gdrive_documents_bge`

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
| `src/ingestion/unified/cli.py` | CLI: preflight, bootstrap, run, status, reprocess |
| `src/ingestion/unified/manifest.py` | Content-hash → stable UUID mapping |
| `src/ingestion/unified/config.py` | `UnifiedIngestionConfig` — env-driven settings |
| `src/ingestion/unified/metrics.py` | Ingestion metrics (counters, timing) |
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

| Collection | Embeddings | Environment |
|------------|------------|-------------|
| `gdrive_documents_scalar` | Voyage 1024-dim | Dev |
| `gdrive_documents_bge` | BGE-M3 1024-dim | VPS |
| `gdrive_documents_binary` | Voyage (binary quantized) | Dev (fast) |

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
| Voyage 429 | Use CacheLayerManager or reduce batch size |
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

## VPS Ingestion

```bash
# Start ingestion on VPS
ssh vps "cd /opt/rag-fresh && docker compose --compatibility -f docker-compose.vps.yml --profile ingest up -d ingestion"

# Check logs
ssh vps "docker logs vps-ingestion --tail 50"

# Check Qdrant points
ssh vps "docker compose -f /opt/rag-fresh/docker-compose.vps.yml exec -T bge-m3 python -c \"import urllib.request, json; print(json.load(urllib.request.urlopen('http://qdrant:6333/collections/gdrive_documents_bge'))['result']['points_count'])\""
```

**VPS Environment:**
```bash
USE_LOCAL_DENSE_EMBEDDINGS=true
BGE_M3_URL=http://bge-m3:8000
GDRIVE_SYNC_DIR=/opt/rag-fresh/drive-sync
GDRIVE_COLLECTION_NAME=gdrive_documents_bge
DOCLING_PROFILE=quality  # speed|quality|scan|vlm
```

**Deploy (immutable image, no bind-mounts):**
```bash
ssh vps "cd /opt/rag-fresh && \
  docker compose --compatibility -f docker-compose.vps.yml --profile ingest build ingestion && \
  docker stop vps-ingestion && docker rm vps-ingestion && \
  docker compose --compatibility -f docker-compose.vps.yml --profile ingest up -d ingestion"
```

## Legacy (deprecated)

Legacy files in `src/ingestion/` (gdrive_flow.py, voyage_indexer.py) are superseded by unified pipeline.
