---
paths: "src/ingestion/**"
---

***REMOVED*** Document Ingestion

Parsing, chunking, and indexing documents into Qdrant via CocoIndex unified pipeline.

***REMOVED******REMOVED*** Quick Commands

```bash
make ingest-unified           ***REMOVED*** Run once
make ingest-unified-watch     ***REMOVED*** Continuous (FlowLiveUpdater)
make ingest-unified-status    ***REMOVED*** Show stats from Postgres
make ingest-unified-reprocess ***REMOVED*** Retry failed files
```

***REMOVED******REMOVED*** Architecture (v3.2.1)

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

***REMOVED******REMOVED******REMOVED*** rclone Setup

```bash
***REMOVED*** Configure (one-time)
rclone config  ***REMOVED*** Create 'gdrive' remote

***REMOVED*** Manual sync
rclone sync gdrive:RAG-Documents ~/drive-sync/ --progress

***REMOVED*** Cron (every 5 min)
*/5 * * * * rclone sync gdrive:RAG-Documents ~/drive-sync/ -q
```

***REMOVED******REMOVED*** Key Files

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

***REMOVED******REMOVED*** Sync Execution Pattern

CocoIndex calls `mutate()` synchronously. All operations must be sync:

```python
***REMOVED*** Target connector uses *_sync() methods:
state_manager.should_process_sync(file_id, content_hash)
docling.chunk_file_sync(abs_path)
writer.upsert_chunks_sync(chunks, file_id, ...)
state_manager.mark_indexed_sync(file_id, chunk_count, content_hash)
```

**Constraint:** NO `asyncio.run()` in mutate() — causes event loop conflicts.

***REMOVED******REMOVED*** Payload Contract

```python
{
    "page_content": str,       ***REMOVED*** Chunk text
    "metadata": {
        "file_id": str,        ***REMOVED*** sha256(rel_path)[:16]
        "doc_id": str,         ***REMOVED*** = file_id (for small-to-big)
        "order": int,          ***REMOVED*** Chunk order
        "source": str,         ***REMOVED*** Relative path
    },
    "file_id": str,            ***REMOVED*** Flat for fast delete
}
```

***REMOVED******REMOVED*** Collections

| Collection | Embeddings | Environment |
|------------|------------|-------------|
| `gdrive_documents_scalar` | Voyage 1024-dim | Dev |
| `gdrive_documents_bge` | BGE-M3 1024-dim | VPS |
| `gdrive_documents_binary` | Voyage (binary quantized) | Dev (fast) |

***REMOVED******REMOVED*** Testing

```bash
pytest tests/unit/ingestion/test_target_sync_execution.py -v  ***REMOVED*** Sync pattern
pytest tests/unit/ingestion/test_state_manager_sync.py -v     ***REMOVED*** StateManager sync
pytest tests/unit/ingestion/test_payload_contract.py -v       ***REMOVED*** Payload structure
pytest tests/unit/ingestion/test_cocoindex_init.py -v         ***REMOVED*** Init settings
RUN_INTEGRATION_TESTS=1 pytest tests/integration/test_unified_ingestion_e2e.py -v
```

***REMOVED******REMOVED*** Troubleshooting

| Error | Fix |
|-------|-----|
| Docling returns 0 chunks | Don't set `tokenizer="word"`, use `None` |
| Voyage 429 | Use CacheLayerManager or reduce batch size |
| `Event loop is closed` | StateManager resets pool between sync calls |
| `asyncio.run()` nested | Use `*_sync()` methods in mutate() |
| Missing payload fields | Check `test_payload_contract.py` |
| Files in DLQ | `make ingest-unified-reprocess` |

***REMOVED******REMOVED*** E2E Verification

```bash
***REMOVED*** 1. Sync from Google Drive
rclone sync gdrive:RAG-Documents ~/drive-sync/ --progress

***REMOVED*** 2. Run ingestion
make ingest-unified

***REMOVED*** 3. Check status
make ingest-unified-status  ***REMOVED*** Should show "indexed: N (100%)"

***REMOVED*** 4. Verify Qdrant
curl -s localhost:6333/collections/gdrive_documents_scalar | jq '.result.points_count'
```

***REMOVED******REMOVED*** VPS Ingestion

```bash
***REMOVED*** Start ingestion on VPS
ssh vps "cd /opt/rag-fresh && docker compose --compatibility -f docker-compose.vps.yml --profile ingest up -d ingestion"

***REMOVED*** Check logs
ssh vps "docker logs vps-ingestion --tail 50"

***REMOVED*** Check Qdrant points
ssh vps "docker compose -f /opt/rag-fresh/docker-compose.vps.yml exec -T bge-m3 python -c \"import urllib.request, json; print(json.load(urllib.request.urlopen('http://qdrant:6333/collections/gdrive_documents_bge'))['result']['points_count'])\""
```

**VPS Environment:**
```bash
USE_LOCAL_DENSE_EMBEDDINGS=true
BGE_M3_URL=http://bge-m3:8000
GDRIVE_SYNC_DIR=/opt/rag-fresh/drive-sync
GDRIVE_COLLECTION_NAME=gdrive_documents_bge
DOCLING_PROFILE=quality  ***REMOVED*** speed|quality|scan|vlm
```

**Deploy (immutable image, no bind-mounts):**
```bash
ssh vps "cd /opt/rag-fresh && \
  docker compose --compatibility -f docker-compose.vps.yml --profile ingest build ingestion && \
  docker stop vps-ingestion && docker rm vps-ingestion && \
  docker compose --compatibility -f docker-compose.vps.yml --profile ingest up -d ingestion"
```

***REMOVED******REMOVED*** Apartments Ingestion (incremental)

Separate pipeline for 297 apartment listings in `apartments` collection. Row-level change tracking via SHA-256 hash — only re-embeds changed rows.

***REMOVED******REMOVED******REMOVED*** Quick Commands

```bash
***REMOVED*** Full re-index
python -m src.ingestion.apartments.runner

***REMOVED*** Incremental (only changed rows)
python -m src.ingestion.apartments.runner --incremental

***REMOVED*** Dry run (show what would change)
python -m src.ingestion.apartments.runner --incremental --dry-run
```

***REMOVED******REMOVED******REMOVED*** Architecture

```
data/apartments.csv (297 rows)
  → source.read_apartments_csv() → (unique_key, change_key, ApartmentRecord)
  → runner.run_incremental() → diff vs .apartments_ingestion_state.json
  → flow.format_apartment_text() → hybrid text: [2BR|78m2|215kEUR] + NL body
  → BGEM3SyncClient.encode_dense/sparse/colbert()
  → flow.build_ingestion_batch() → Qdrant upsert (apartments collection)
```

***REMOVED******REMOVED******REMOVED*** Key Files

| File | Description |
|------|-------------|
| `src/ingestion/apartments/source.py` | CSV parser + `row_change_key()` for change detection |
| `src/ingestion/apartments/flow.py` | `format_apartment_text()`, `build_ingestion_batch()`, UUID5 point IDs |
| `src/ingestion/apartments/runner.py` | `IncrementalApartmentIngester` — CLI with --incremental/--dry-run |
| `scripts/apartments/ingest.py` | Legacy batch script (one-shot, no change tracking) |
| `scripts/apartments/setup_collection.py` | Collection creation + 11 payload indexes |

***REMOVED******REMOVED******REMOVED*** Testing

```bash
uv run pytest tests/unit/ingestion/test_apartment_source.py -v   ***REMOVED*** CSV parsing, change keys
uv run pytest tests/unit/ingestion/test_apartment_flow.py -v     ***REMOVED*** Hybrid text format
uv run pytest tests/unit/ingestion/test_apartment_runner.py -v   ***REMOVED*** Incremental logic
RUN_INTEGRATION=1 uv run pytest tests/integration/test_apartments_ingestion.py -v  ***REMOVED*** Live Qdrant
```

***REMOVED******REMOVED******REMOVED*** Collection

| Collection | Vectors | Points |
|------------|---------|--------|
| `apartments` | dense (1024) + bm42 (sparse) + colbert (multi-vec) | 297 |

***REMOVED******REMOVED******REMOVED*** Hybrid Text Format

`format_apartment_text()` delegates to `ApartmentRecord.to_hybrid_description()`:
- **Structured prefix** `[2BR|78.66m2|215kEUR]` — helps sparse/lexical retrieval
- **NL body** (Russian) — helps dense/semantic retrieval
- **Promotion marker** `Акция!` — if `is_promotion=True`

***REMOVED******REMOVED*** Legacy (deprecated)

Legacy files in `src/ingestion/` (gdrive_flow.py, voyage_indexer.py) are superseded by unified pipeline.
