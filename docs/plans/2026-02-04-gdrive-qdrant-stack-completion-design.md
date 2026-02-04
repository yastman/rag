# GDrive → Qdrant Stack Completion Design

> **Status:** Design document
> **Date:** 2026-02-04
> **Goal:** Complete the unified ingestion stack to production-ready state

## Executive Summary

The unified ingestion pipeline (v3.2.1) is ~85% complete. The architecture is sound, most code exists, but several integration gaps prevent end-to-end operation.

**Current State:**
- Code: 90% implemented
- Docker: 100% configured
- Tests: 2 failing (async/sync mismatch)
- Infrastructure: rclone scripts exist, systemd not installed
- Data: 0 files ingested (pipeline never ran successfully)

**Blocking Issues:**
1. Target connector uses `asyncio.run()` with async handlers (tests fail)
2. rclone not configured for actual GDrive folder
3. systemd timer not installed

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         CURRENT STATE                                    │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  Google Drive                                                            │
│       │                                                                  │
│       ▼ (manual rclone sync)                                            │
│  ~/drive-sync/  ◄─── 3 files exist (Test/, Procesed/, 1 xlsx)          │
│       │                                                                  │
│       ▼ (NOT RUNNING - tests fail)                                      │
│  CocoIndex Flow                                                          │
│       │                                                                  │
│       ▼                                                                  │
│  QdrantHybridTarget ◄─── asyncio.run() + async handlers (BUG)          │
│       │                                                                  │
│       ├─► DoclingClient (chunking) ✅                                   │
│       ├─► VoyageService (dense) ✅ has sync method                      │
│       ├─► FastEmbed BM42 (sparse) ✅                                    │
│       └─► Qdrant + Postgres ✅                                          │
│                                                                          │
│  ingestion_state: 0 rows                                                 │
│  Qdrant gdrive_documents_scalar: 0 points                               │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## Gap Analysis

### 1. Code Issues

| Component | File | Issue | Fix Required |
|-----------|------|-------|--------------|
| Target `_handle_delete` | `qdrant_hybrid_target.py:218` | `async def` | Make sync, use `delete_file_sync()` |
| Target `_handle_upsert` | `qdrant_hybrid_target.py:228` | `async def` | Make sync, use sync methods |
| Target `mutate()` | `qdrant_hybrid_target.py:215` | `asyncio.run()` | Remove, handlers are sync |
| DoclingClient | `docling_client.py` | async only | Add sync wrapper or use httpx sync |
| StateManager | `state_manager.py` | async only | Add sync methods with `asyncpg` sync |

**Root Cause:** Plan v3.2.1 specified sync execution (P0.5), but implementation kept async pattern.

**Evidence:**
```python
# Test expects sync (will fail):
assert not asyncio.iscoroutinefunction(QdrantHybridTargetConnector._handle_delete)

# Current code (async):
async def _handle_delete(cls, spec, file_id) -> None:
    await writer.delete_file(...)  # calls async method
```

### 2. Infrastructure Gaps

| Component | Status | Location | Action |
|-----------|--------|----------|--------|
| rclone binary | ✅ Installed | `/usr/bin/rclone` v1.60.1 | None |
| rclone remote | ✅ Configured | `gdrive:` remote exists | None |
| rclone.conf (docker) | ⚠️ Template | `docker/rclone/rclone.conf` | Set `root_folder_id` |
| sync-drive.sh | ✅ Complete | `docker/rclone/sync-drive.sh` | Install to `/opt/scripts/` |
| crontab | ✅ Complete | `docker/rclone/crontab` | Install to `/etc/cron.d/` |
| systemd timer | ❌ Missing | N/A | Create or use cron |
| ~/drive-sync | ✅ Exists | 3 test files | Sync real data |

### 3. Test Failures

```
FAILED tests/unit/ingestion/test_target_sync_execution.py::test_handle_methods_are_sync
FAILED tests/unit/ingestion/test_target_sync_execution.py::test_mutate_does_not_call_asyncio_run
```

Both will pass once handlers become sync.

### 4. Docker Service

| Aspect | Status | Notes |
|--------|--------|-------|
| Dockerfile.ingestion | ✅ | Multi-stage, non-root user |
| docker-compose service | ✅ | Profile: `ingest`, `full` |
| Environment vars | ✅ | All configured |
| Volume mounts | ✅ | `~/drive-sync:/data/drive-sync:ro` |
| Health check | ✅ | `pgrep -f cli` |
| Container running | ❌ | Not started |

---

## Design Decisions

### D1: Sync vs Async in Target Connector

**Decision:** Make `mutate()` and handlers fully synchronous.

**Rationale:**
- CocoIndex calls `mutate()` from sync context
- `asyncio.run()` inside `mutate()` creates event loop conflicts
- All dependencies have sync alternatives:
  - `QdrantHybridWriter.delete_file_sync()` ✅
  - `QdrantHybridWriter.upsert_chunks_sync()` ✅
  - `VoyageService.embed_documents_sync()` ✅
  - Qdrant client is natively sync ✅

**Exception:** StateManager and DoclingClient are async-only. Options:
1. Add `*_sync` methods (preferred)
2. Use `asyncio.run()` per-call (acceptable for low-frequency ops)
3. Replace asyncpg with psycopg2 (invasive)

**Chosen:** Option 1 for StateManager (add sync methods), Option 2 for DoclingClient (wrap in `asyncio.run()` since it's I/O bound and called once per file).

### D2: rclone Scheduling

**Decision:** Use cron (not systemd timer).

**Rationale:**
- crontab file already exists and is tested
- WSL2 environment may not have full systemd
- cron is simpler for 5-minute intervals
- Can upgrade to systemd later if needed

### D3: Error Handling

**Decision:** Keep current DLQ pattern but ensure sync execution.

**Current flow:**
1. File fails → `mark_error()` + increment retry_count
2. After 3 retries → `add_to_dlq()`
3. DLQ entries reviewable via `make ingest-unified-status`

This is correct, just needs sync implementation.

---

## Implementation Plan

### Phase 1: Fix Sync Execution (P0 - Blocking)

**Goal:** Make tests pass, enable pipeline execution.

#### Task 1.1: Add StateManager Sync Methods

Add to `src/ingestion/unified/state_manager.py`:

```python
def get_state_sync(self, file_id: str) -> FileState | None:
    """Sync version using psycopg2 or asyncio.run()."""
    return asyncio.get_event_loop().run_until_complete(self.get_state(file_id))

def mark_processing_sync(self, file_id: str) -> None:
    asyncio.get_event_loop().run_until_complete(self.mark_processing(file_id))

def mark_indexed_sync(self, file_id: str, chunk_count: int, content_hash: str) -> None:
    asyncio.get_event_loop().run_until_complete(
        self.mark_indexed(file_id, chunk_count, content_hash)
    )

def mark_error_sync(self, file_id: str, error: str) -> None:
    asyncio.get_event_loop().run_until_complete(self.mark_error(file_id, error))

def mark_deleted_sync(self, file_id: str) -> None:
    asyncio.get_event_loop().run_until_complete(self.mark_deleted(file_id))

def should_process_sync(self, file_id: str, content_hash: str) -> bool:
    return asyncio.get_event_loop().run_until_complete(
        self.should_process(file_id, content_hash)
    )

def add_to_dlq_sync(self, file_id: str, error_type: str, error_message: str, payload: dict | None = None) -> int:
    return asyncio.get_event_loop().run_until_complete(
        self.add_to_dlq(file_id, error_type, error_message, payload)
    )
```

**Alternative (cleaner):** Use `psycopg2` for sync methods instead of wrapping async.

#### Task 1.2: Add DoclingClient Sync Wrapper

Add to `src/ingestion/docling_client.py`:

```python
def chunk_file_sync(self, file_path: Path) -> list[DoclingChunk]:
    """Sync version for use in CocoIndex target."""
    loop = asyncio.new_event_loop()
    try:
        asyncio.set_event_loop(loop)
        if not self._client:
            loop.run_until_complete(self.connect())
        return loop.run_until_complete(self.chunk_file(file_path))
    finally:
        loop.close()
```

#### Task 1.3: Refactor Target Connector

Replace `qdrant_hybrid_target.py` handlers:

```python
@staticmethod
def mutate(
    *all_mutations: tuple[QdrantHybridTargetSpec, dict[str, QdrantHybridTargetValues | None]],
) -> None:
    """Apply data mutations to Qdrant (fully synchronous)."""
    for spec, mutations in all_mutations:
        for file_id, mutation in mutations.items():
            try:
                if mutation is None:
                    QdrantHybridTargetConnector._handle_delete_sync(spec, file_id)
                else:
                    QdrantHybridTargetConnector._handle_upsert_sync(spec, file_id, mutation)
            except Exception as e:
                logger.error(f"Mutation failed for {file_id}: {e}", exc_info=True)

@classmethod
def _handle_delete_sync(cls, spec: QdrantHybridTargetSpec, file_id: str) -> None:
    """Handle file deletion (sync)."""
    writer = cls._get_writer(spec)
    state_manager = cls._get_state_manager(spec)

    writer.delete_file_sync(file_id, spec.collection_name)
    state_manager.mark_deleted_sync(file_id)
    logger.info(f"Deleted: file_id={file_id}")

@classmethod
def _handle_upsert_sync(
    cls,
    spec: QdrantHybridTargetSpec,
    file_id: str,
    mutation: QdrantHybridTargetValues,
) -> None:
    """Handle file insert/update (sync)."""
    writer = cls._get_writer(spec)
    docling = cls._get_docling(spec)
    state_manager = cls._get_state_manager(spec)

    abs_path = Path(mutation.abs_path)
    source_path = mutation.source_path
    content_hash = compute_content_hash(abs_path)

    if not state_manager.should_process_sync(file_id, content_hash):
        logger.debug(f"Skipping unchanged: {source_path}")
        return

    state_manager.mark_processing_sync(file_id)

    try:
        # Use sync docling method
        docling_chunks = docling.chunk_file_sync(abs_path)
        if not docling_chunks:
            state_manager.mark_indexed_sync(file_id, 0, content_hash)
            logger.warning(f"No chunks from: {source_path}")
            return

        chunks = docling.to_ingestion_chunks(
            docling_chunks,
            source=source_path,
            source_type=abs_path.suffix.lstrip("."),
        )

        file_metadata = {
            "file_name": mutation.file_name,
            "mime_type": mutation.mime_type,
            "file_size": mutation.file_size,
            "content_hash": content_hash,
            "modified_time": datetime.now(UTC).isoformat(),
        }

        # Use sync writer method
        stats = writer.upsert_chunks_sync(
            chunks=chunks,
            file_id=file_id,
            source_path=source_path,
            file_metadata=file_metadata,
            collection_name=spec.collection_name,
        )

        if stats.errors:
            raise Exception("; ".join(stats.errors))

        state_manager.mark_indexed_sync(file_id, stats.points_upserted, content_hash)
        logger.info(f"Indexed: {source_path} ({stats.points_upserted} chunks)")

    except Exception as e:
        logger.error(f"Upsert failed for {source_path}: {e}")
        state_manager.mark_error_sync(file_id, str(e))

        state = state_manager.get_state_sync(file_id)
        if state and state.retry_count >= spec.max_retries:
            state_manager.add_to_dlq_sync(
                file_id=file_id,
                error_type=type(e).__name__,
                error_message=str(e),
                payload={"source_path": source_path},
            )
            logger.warning(f"Moved to DLQ: {source_path}")
        raise
```

#### Task 1.4: Verify Tests Pass

```bash
uv run pytest tests/unit/ingestion/test_target_sync_execution.py -v
uv run pytest tests/unit/ingestion/test_payload_contract.py -v
uv run pytest tests/unit/ingestion/test_cocoindex_init.py -v
```

**Expected:** All 9 tests pass.

---

### Phase 2: Infrastructure Setup (P1)

**Goal:** Enable automated rclone sync.

#### Task 2.1: Configure rclone Remote

```bash
# Option A: Use existing user rclone config
rclone listremotes  # Should show gdrive:

# Option B: Set specific folder
rclone lsd gdrive:  # List root folders
# Note the folder ID for RAG documents
```

#### Task 2.2: Install Sync Script

```bash
sudo mkdir -p /opt/scripts
sudo cp docker/rclone/sync-drive.sh /opt/scripts/
sudo chmod +x /opt/scripts/sync-drive.sh

# Test manually
GDRIVE_SYNC_DIR=~/drive-sync /opt/scripts/sync-drive.sh
```

#### Task 2.3: Install Crontab

```bash
sudo cp docker/rclone/crontab /etc/cron.d/rclone-sync
sudo chmod 644 /etc/cron.d/rclone-sync

# Verify
sudo crontab -l -u root | grep rclone
```

#### Task 2.4: Verify Sync

```bash
# Wait 5 minutes or trigger manually
ls -la ~/drive-sync/

# Check logs
tail -f ~/.local/log/rclone-sync.log
```

---

### Phase 3: End-to-End Validation (P2)

**Goal:** Verify complete pipeline works.

#### Task 3.1: Run Ingestion Once

```bash
# Ensure services are up
make docker-core-up

# Run ingestion manually (not watch mode)
make ingest-unified

# Check status
make ingest-unified-status
```

**Expected output:**
```
=== Ingestion Status ===
  indexed: N (100.0%)
  TOTAL: N

  DLQ: 0 items
  Collection: gdrive_documents_scalar
  Sync dir: /home/user/drive-sync
```

#### Task 3.2: Verify Qdrant Data

```bash
# Check collection
curl -s localhost:6333/collections/gdrive_documents_scalar | jq '.result.points_count'

# Sample point payload
curl -s localhost:6333/collections/gdrive_documents_scalar/points/scroll \
  -H 'Content-Type: application/json' \
  -d '{"limit": 1, "with_payload": true}' | jq '.result.points[0].payload'
```

**Expected:** Points with `page_content`, `metadata.file_id`, `metadata.doc_id`, `metadata.order`, `metadata.source`.

#### Task 3.3: Run Watch Mode

```bash
# Start watch mode
make ingest-unified-watch

# In another terminal, add a test file
echo "# Test Document" > ~/drive-sync/test-watch.md

# Watch logs for processing
# Should see: "Indexed: test-watch.md (1 chunks)"

# Cleanup
rm ~/drive-sync/test-watch.md
# Should see: "Deleted: file_id=..."
```

#### Task 3.4: Docker Integration

```bash
# Start ingestion container
docker compose -f docker-compose.dev.yml --profile ingest up -d

# Check logs
docker logs dev-ingestion -f

# Verify health
docker ps --filter name=dev-ingestion --format "{{.Status}}"
```

---

### Phase 4: Production Hardening (P3 - Optional)

#### Task 4.1: Add Metrics Integration

Ensure metrics are logged:

```python
# In _handle_upsert_sync:
from src.ingestion.unified.metrics import IngestionMetrics, timed_operation, log_ingestion_result

metrics = IngestionMetrics(file_id=file_id, source_path=source_path)

with timed_operation(metrics, "docling"):
    docling_chunks = docling.chunk_file_sync(abs_path)

with timed_operation(metrics, "voyage"):
    # voyage happens inside upsert_chunks_sync
    pass

with timed_operation(metrics, "qdrant"):
    stats = writer.upsert_chunks_sync(...)

metrics.chunks_created = stats.points_upserted
metrics.status = "success"
log_ingestion_result(metrics)
```

#### Task 4.2: Loki Alert Rules

Verify rules are loaded:

```bash
curl -s localhost:3100/loki/api/v1/rules | jq '.data.groups[].name'
# Should include: "ingestion"
```

---

## Verification Checklist

### Phase 1 Complete
- [ ] `pytest tests/unit/ingestion/test_target_sync_execution.py` — 3 passed
- [ ] `pytest tests/unit/ingestion/test_payload_contract.py` — 4 passed
- [ ] `pytest tests/unit/ingestion/test_cocoindex_init.py` — 3 passed

### Phase 2 Complete
- [ ] `/opt/scripts/sync-drive.sh` exists and executable
- [ ] `/etc/cron.d/rclone-sync` exists
- [ ] `~/drive-sync/` has files from GDrive

### Phase 3 Complete
- [ ] `make ingest-unified-status` shows indexed > 0
- [ ] Qdrant collection has points with correct payload
- [ ] Watch mode detects file changes
- [ ] `docker logs dev-ingestion` shows successful processing

### Production Ready
- [ ] All unit tests pass
- [ ] E2E test passes: `RUN_INTEGRATION_TESTS=1 pytest tests/integration/test_unified_ingestion_e2e.py`
- [ ] Docker service runs without errors for 1 hour
- [ ] Alerts configured in Loki

---

## Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| asyncpg pool issues | Medium | High | Use psycopg2 for sync methods |
| Docling timeout | Low | Medium | 300s timeout, retry logic |
| Voyage rate limit | Low | Medium | Batch size 128, backoff |
| rclone token expiry | Medium | High | Document refresh process |
| Large file OOM | Low | High | Memory limit 1G in Docker |

---

## Summary

**Work Required:**
1. **Phase 1 (P0):** ~2-3 hours — Fix async/sync, make tests pass
2. **Phase 2 (P1):** ~30 min — Install rclone cron
3. **Phase 3 (P2):** ~1 hour — Validate end-to-end
4. **Phase 4 (P3):** ~1 hour — Production hardening

**Total:** ~5-6 hours to production-ready state.

**Files to Modify:**
- `src/ingestion/unified/state_manager.py` — add `*_sync` methods
- `src/ingestion/docling_client.py` — add `chunk_file_sync()`
- `src/ingestion/unified/targets/qdrant_hybrid_target.py` — refactor to sync

**Files to Create:**
- None (all infrastructure files exist)

**Files to Install:**
- `/opt/scripts/sync-drive.sh`
- `/etc/cron.d/rclone-sync`
