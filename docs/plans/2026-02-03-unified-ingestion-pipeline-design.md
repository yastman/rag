# Design: Unified Ingestion Pipeline (rclone + CocoIndex + Qdrant)

**Date:** 2026-02-03
**Status:** Draft
**Author:** Claude
**Based on:** Production ТЗ for RAG chatbot (недвижимость)

---

## 1. Overview

### 1.1 Goal

Build a production ingestion pipeline that automatically syncs documents from Google Drive, extracts text/structure, chunks, computes dense+sparse embeddings, and indexes to Qdrant for hybrid search with source citations.

### 1.2 Success Criteria

- User uploads/updates/deletes document in Drive → changes reflected in search within 10 minutes (SLO 95%)
- Hybrid search: dense (Voyage 1024) + sparse (BM42)
- Idempotent updates: no duplicates on re-processing
- Deletions correctly remove all chunks from Qdrant

### 1.3 Non-Goals (out of scope)

- UI/admin for source management
- Per-chunk ACL/ABAC
- Full RAGAS evaluation harness

---

## 2. Architecture

### 2.1 Data Flow

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              GOOGLE DRIVE                                   │
│                         (Shared Folder: RAG/)                               │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼ systemd timer (every 5 min)
┌─────────────────────────────────────────────────────────────────────────────┐
│  RCLONE SYNC                                                                │
│  rclone sync gdrive:RAG /data/drive-sync --drive-export-formats docx,xlsx   │
│  Log: /var/log/rclone-sync.log                                              │
│  Metric: last_sync_success_ts, sync_duration, files_changed                 │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼ watch/poll (60s) + refresh (6h)
┌─────────────────────────────────────────────────────────────────────────────┐
│  COCOINDEX ORCHESTRATOR                                                     │
│  Source: LocalFile("/data/drive-sync", watch_interval=60s)                  │
│  State: Postgres (cocoindex.ingestion_state)                                │
│  Detects: NEW / MODIFIED / DELETED files via content_hash                   │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
            ┌───────────────────────┼───────────────────────┐
            ▼                       ▼                       ▼
       [NEW FILE]            [MODIFIED FILE]          [DELETED FILE]
            │                       │                       │
            │                       ▼                       ▼
            │              DELETE chunks WHERE      DELETE chunks WHERE
            │              file_id = X              file_id = X
            │                       │               Update state → DELETED
            │                       ▼
            └───────────────────────┤
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  DOCLING-SERVE (dev-docling:5001)                                           │
│  POST /v1/chunk/hybrid/file                                                 │
│  Output: chunks[] with contextualized_text, headings, chunk_location        │
│  Timeout: 120s, retries on 5xx                                              │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  EMBEDDINGS (batched, rate-limited)                                         │
│  ├─ Voyage voyage-4-large (1024-dim dense), batch=100, 300 RPM              │
│  └─ FastEmbed BM42 (sparse vectors, IDF modifier)                           │
│  Input: contextualized_text                                                 │
│  Retries: exponential backoff on 429/5xx                                    │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  QDRANT UPSERT (dev-qdrant:6333)                                            │
│  Collection: gdrive_documents                                               │
│  Vectors: dense (1024, cosine) + bm42 (sparse, IDF)                         │
│  Point ID: UUIDv5(file_id + chunk_location)                                 │
│  Payload: file_id, source_path, headings, text, content_hash, updated_at    │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  STATE UPDATE (Postgres)                                                    │
│  Success: UPDATE ingestion_state SET status='indexed', chunk_count=N        │
│  Failure: INSERT INTO dead_letter_queue (file_id, error, retry_count)       │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 2.2 Components

| Component | Role | Container/Service |
|-----------|------|-------------------|
| rclone | Drive → local sync | systemd timer on host |
| CocoIndex | Orchestration, state tracking | Python process |
| Postgres | Ingestion state, DLQ | dev-postgres:5432 |
| docling-serve | Parsing, chunking | dev-docling:5001 |
| Voyage AI | Dense embeddings | External API |
| FastEmbed | Sparse BM42 | In-process |
| Qdrant | Vector storage, hybrid search | dev-qdrant:6333 |

---

## 3. Postgres Schema

### 3.1 Database Setup

```sql
-- File: docker/postgres/init/03-ingestion.sql

-- Ingestion state tracking
CREATE TABLE ingestion_state (
    id SERIAL PRIMARY KEY,
    file_id VARCHAR(64) UNIQUE NOT NULL,      -- SHA256(relative_path)[:16]
    source_path VARCHAR(1000) NOT NULL,        -- Relative path from sync dir
    file_name VARCHAR(500),
    mime_type VARCHAR(100),
    file_size BIGINT,
    content_hash VARCHAR(64),                  -- SHA256 of file content

    -- Processing info
    status VARCHAR(20) DEFAULT 'pending',      -- pending, processing, indexed, error, deleted
    chunk_count INTEGER DEFAULT 0,

    -- Versioning
    parser_version VARCHAR(20),                -- e.g., "docling-2.1"
    embedding_version VARCHAR(20),             -- e.g., "voyage-4-large"
    pipeline_version VARCHAR(20),              -- e.g., "v1.0"

    -- Timestamps
    file_modified_at TIMESTAMPTZ,
    indexed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),

    -- Error tracking
    error_message TEXT,
    retry_count INTEGER DEFAULT 0,
    last_error_at TIMESTAMPTZ
);

CREATE INDEX idx_ingestion_file_id ON ingestion_state(file_id);
CREATE INDEX idx_ingestion_status ON ingestion_state(status);
CREATE INDEX idx_ingestion_source_path ON ingestion_state(source_path);
CREATE INDEX idx_ingestion_content_hash ON ingestion_state(content_hash);

-- Dead letter queue for failed items
CREATE TABLE dead_letter_queue (
    id SERIAL PRIMARY KEY,
    file_id VARCHAR(64) NOT NULL,
    source_path VARCHAR(1000),
    error_type VARCHAR(100),                   -- docling_timeout, voyage_429, qdrant_error
    error_message TEXT,
    stack_trace TEXT,
    payload JSONB,                             -- Original request data
    retry_count INTEGER DEFAULT 0,
    max_retries INTEGER DEFAULT 3,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    last_retry_at TIMESTAMPTZ,
    resolved_at TIMESTAMPTZ,
    resolved_by VARCHAR(100)                   -- manual, auto_retry, skip
);

CREATE INDEX idx_dlq_file_id ON dead_letter_queue(file_id);
CREATE INDEX idx_dlq_error_type ON dead_letter_queue(error_type);
CREATE INDEX idx_dlq_resolved ON dead_letter_queue(resolved_at) WHERE resolved_at IS NULL;

-- Sync status tracking (for rclone)
CREATE TABLE sync_status (
    id SERIAL PRIMARY KEY,
    sync_type VARCHAR(50) DEFAULT 'rclone',
    started_at TIMESTAMPTZ NOT NULL,
    completed_at TIMESTAMPTZ,
    status VARCHAR(20),                        -- running, success, failed
    files_added INTEGER DEFAULT 0,
    files_modified INTEGER DEFAULT 0,
    files_deleted INTEGER DEFAULT 0,
    bytes_transferred BIGINT DEFAULT 0,
    duration_seconds FLOAT,
    error_message TEXT
);

CREATE INDEX idx_sync_status_completed ON sync_status(completed_at DESC);
```

### 3.2 State Transitions

```
                    ┌─────────┐
                    │ pending │ ◄── New file detected
                    └────┬────┘
                         │
                         ▼
                  ┌────────────┐
        ┌────────►│ processing │
        │         └──────┬─────┘
        │                │
        │    ┌───────────┴───────────┐
        │    ▼                       ▼
   ┌────────────┐             ┌───────────┐
   │  indexed   │             │   error   │──► DLQ (after 3 retries)
   └────────────┘             └───────────┘
        │                           │
        │ file deleted              │ file modified
        ▼                           ▼
   ┌─────────┐                 ┌─────────┐
   │ deleted │                 │ pending │ (re-process)
   └─────────┘                 └─────────┘
```

---

## 4. File Identification

### 4.1 file_id Strategy

**Decision:** Use `SHA256(relative_path)[:16]` for MVP.

```python
def compute_file_id(sync_dir: Path, file_path: Path) -> str:
    """Compute stable file_id from relative path."""
    relative = file_path.relative_to(sync_dir)
    return hashlib.sha256(str(relative).encode()).hexdigest()[:16]
```

**Trade-offs:**
- Rename/move in Drive = DELETE old + ADD new (acceptable for MVP)
- Simple, no external manifest needed
- Future: Add Drive file_id via `.gdrive_manifest.json` for stability

### 4.2 point_id (Qdrant)

**Decision:** `UUIDv5(file_id + chunk_location)`

```python
def compute_point_id(file_id: str, chunk_location: str) -> str:
    """Compute deterministic point ID for idempotency."""
    namespace = uuid.UUID("6ba7b810-9dad-11d1-80b4-00c04fd430c8")  # URL namespace
    return str(uuid.uuid5(namespace, f"{file_id}:{chunk_location}"))
```

**chunk_location format:** `page:{page_num}:offset:{char_offset}` or docling's native `doc_items` reference.

---

## 5. Qdrant Collection Schema

### 5.1 Collection Setup

```python
# scripts/setup_gdrive_collection.py

from qdrant_client import QdrantClient
from qdrant_client.models import (
    VectorParams, SparseVectorParams, Distance,
    PayloadSchemaType, SparseIndexParams, Modifier,
)

COLLECTION_NAME = "gdrive_documents"

def setup_collection(client: QdrantClient):
    """Create collection with hybrid vectors."""

    client.create_collection(
        collection_name=COLLECTION_NAME,
        vectors_config={
            "dense": VectorParams(
                size=1024,
                distance=Distance.COSINE,
            ),
        },
        sparse_vectors_config={
            "bm42": SparseVectorParams(
                index=SparseIndexParams(on_disk=False),
                modifier=Modifier.IDF,
            ),
        },
    )

    # Payload indexes for filtering and deletion
    payload_indexes = [
        ("file_id", PayloadSchemaType.KEYWORD),
        ("source_path", PayloadSchemaType.KEYWORD),
        ("mime_type", PayloadSchemaType.KEYWORD),
        ("updated_at", PayloadSchemaType.DATETIME),
    ]

    for field_name, field_type in payload_indexes:
        client.create_payload_index(
            collection_name=COLLECTION_NAME,
            field_name=field_name,
            field_schema=field_type,
        )
```

### 5.2 Payload Schema

```python
@dataclass
class ChunkPayload:
    # Identity
    file_id: str                    # SHA256(relative_path)[:16]
    point_id: str                   # UUIDv5(file_id + chunk_location)

    # Source info
    source_path: str                # Relative path from sync dir
    file_name: str                  # Original filename
    mime_type: str                  # application/pdf, etc.

    # Chunk info
    chunk_index: int                # Order within document
    chunk_count: int                # Total chunks in document
    chunk_location: str             # page:1:offset:0

    # Content
    text: str                       # contextualized_text for RAG
    headings: list[str]             # Breadcrumb headers
    content_hash: str               # SHA256(text)[:16] for diff

    # Metadata
    page_number: int | None
    docling_meta: dict              # Raw docling metadata

    # Versioning
    pipeline_version: str           # "v1.0"
    embedding_version: str          # "voyage-4-large"
    updated_at: str                 # ISO timestamp
```

---

## 6. Module Structure

### 6.1 New/Modified Files

```
src/ingestion/
├── __init__.py
├── orchestrator.py          # NEW: Main CocoIndex orchestrator
├── state_manager.py         # NEW: Postgres state CRUD
├── dead_letter.py           # NEW: DLQ operations
├── file_processor.py        # NEW: Single file processing pipeline
├── docling_client.py        # EXISTS: Keep as-is
├── gdrive_indexer.py        # MODIFY: Use new state manager
├── chunker.py               # EXISTS: Keep as-is
└── voyage_indexer.py        # EXISTS: Keep as-is

docker/
├── postgres/
│   └── init/
│       ├── 01-init.sql      # EXISTS
│       └── 03-ingestion.sql # NEW: State tables
├── rclone/
│   ├── rclone.conf          # EXISTS
│   ├── sync-drive.sh        # EXISTS
│   └── rclone-sync.service  # NEW: systemd unit
│   └── rclone-sync.timer    # NEW: systemd timer

scripts/
├── setup_gdrive_collection.py  # NEW: Collection + indexes
├── reprocess_dlq.py            # NEW: Manual DLQ retry
└── ingestion_status.py         # NEW: Status dashboard CLI
```

### 6.2 Core Classes

```python
# src/ingestion/orchestrator.py

class IngestionOrchestrator:
    """Main orchestrator for the ingestion pipeline."""

    def __init__(
        self,
        sync_dir: Path,
        postgres_url: str,
        qdrant_url: str,
        docling_url: str,
        voyage_api_key: str,
        watch_interval: int = 60,
        refresh_interval: int = 21600,  # 6 hours
    ):
        self.sync_dir = sync_dir
        self.state_manager = StateManager(postgres_url)
        self.file_processor = FileProcessor(
            docling_url=docling_url,
            qdrant_url=qdrant_url,
            voyage_api_key=voyage_api_key,
        )
        self.dead_letter = DeadLetterQueue(postgres_url)

    async def run_once(self) -> IngestionStats:
        """Single pass: detect changes, process, update state."""

    async def run_continuous(self, watch_interval: int = 60):
        """Continuous mode with polling."""

    async def detect_changes(self) -> FileChanges:
        """Compare filesystem to state DB."""

    async def process_file(self, file_path: Path, change_type: ChangeType):
        """Process single file with retries and DLQ."""
```

```python
# src/ingestion/state_manager.py

class StateManager:
    """Postgres state operations."""

    async def get_state(self, file_id: str) -> FileState | None:
        """Get current state for file."""

    async def update_state(self, state: FileState) -> None:
        """Update file state."""

    async def mark_indexed(self, file_id: str, chunk_count: int) -> None:
        """Mark file as successfully indexed."""

    async def mark_deleted(self, file_id: str) -> None:
        """Mark file as deleted."""

    async def mark_error(self, file_id: str, error: str) -> None:
        """Mark file as errored, increment retry count."""

    async def get_pending_files(self) -> list[FileState]:
        """Get files pending processing."""

    async def detect_missing_files(self, current_files: set[str]) -> list[str]:
        """Find file_ids in DB but not in filesystem (deleted)."""
```

---

## 7. rclone Automation

### 7.1 systemd Timer

```ini
# docker/rclone/rclone-sync.timer
[Unit]
Description=Run rclone sync every 5 minutes

[Timer]
OnBootSec=1min
OnUnitActiveSec=5min
AccuracySec=1min

[Install]
WantedBy=timers.target
```

```ini
# docker/rclone/rclone-sync.service
[Unit]
Description=Sync Google Drive to local folder
After=network-online.target

[Service]
Type=oneshot
User=user
ExecStart=/opt/scripts/sync-drive.sh
StandardOutput=append:/var/log/rclone-sync.log
StandardError=append:/var/log/rclone-sync.log

[Install]
WantedBy=multi-user.target
```

### 7.2 Sync Script

```bash
#!/bin/bash
# docker/rclone/sync-drive.sh

set -euo pipefail

SYNC_DIR="${GDRIVE_SYNC_DIR:-/data/drive-sync}"
LOG_FILE="/var/log/rclone-sync.log"
METRICS_FILE="/tmp/rclone_metrics.prom"

echo "[$(date -Iseconds)] Starting sync..."

START_TIME=$(date +%s)

rclone sync gdrive:RAG "$SYNC_DIR" \
    --drive-export-formats docx,xlsx,pptx \
    --exclude ".*" \
    --exclude "~$*" \
    --stats-one-line \
    --stats-log-level NOTICE \
    2>&1 | tee -a "$LOG_FILE"

END_TIME=$(date +%s)
DURATION=$((END_TIME - START_TIME))

# Write Prometheus metrics
cat > "$METRICS_FILE" << EOF
# HELP rclone_last_sync_timestamp Last successful sync timestamp
# TYPE rclone_last_sync_timestamp gauge
rclone_last_sync_timestamp $END_TIME
# HELP rclone_sync_duration_seconds Sync duration in seconds
# TYPE rclone_sync_duration_seconds gauge
rclone_sync_duration_seconds $DURATION
EOF

echo "[$(date -Iseconds)] Sync completed in ${DURATION}s"
```

---

## 8. Error Handling & Retries

### 8.1 Retry Strategy

| Error Type | Retry | Backoff | Max Retries |
|------------|-------|---------|-------------|
| Docling timeout | Yes | Exponential (2^n * 5s) | 3 |
| Docling 5xx | Yes | Exponential | 3 |
| Voyage 429 | Yes | Respect Retry-After header | 5 |
| Voyage 5xx | Yes | Exponential | 3 |
| Qdrant 5xx | Yes | Exponential | 3 |
| 4xx (not 429) | No | — | 0 → DLQ |
| Parse error | No | — | 0 → DLQ |

### 8.2 DLQ Processing

```python
# scripts/reprocess_dlq.py

async def reprocess_dlq(
    limit: int = 10,
    error_type: str | None = None,
    dry_run: bool = False,
):
    """Manually retry items from dead letter queue."""

    items = await dlq.get_unresolved(limit=limit, error_type=error_type)

    for item in items:
        if dry_run:
            print(f"Would retry: {item.file_id} ({item.error_type})")
            continue

        try:
            await processor.process_file(item.source_path)
            await dlq.mark_resolved(item.id, resolved_by="manual_retry")
        except Exception as e:
            await dlq.increment_retry(item.id, str(e))
```

---

## 9. Observability

### 9.1 Metrics (Prometheus format)

```python
# Ingestion metrics
ingestion_files_seen_total
ingestion_files_processed_total{status="success|error"}
ingestion_chunks_generated_total
ingestion_processing_duration_seconds

# Docling metrics
docling_requests_total{status="success|error|timeout"}
docling_latency_seconds{quantile="0.5|0.95|0.99"}
docling_chunks_per_document

***REMOVED*** metrics
voyage_requests_total{status="success|error|rate_limited"}
voyage_tokens_total
voyage_latency_seconds{quantile="0.5|0.95|0.99"}

# BM42 metrics
bm42_documents_total
bm42_latency_seconds

***REMOVED*** metrics
qdrant_upsert_total{status="success|error"}
qdrant_delete_total{status="success|error"}
qdrant_latency_seconds{operation="upsert|delete"}

# End-to-end
ingestion_time_to_index_seconds{quantile="0.5|0.95"}
```

### 9.2 Alerts

```yaml
# docker/monitoring/rules/ingestion.yaml

groups:
  - name: ingestion
    rules:
      - alert: RcloneSyncFailed
        expr: time() - rclone_last_sync_timestamp > 900
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "rclone sync not running"

      - alert: IngestionBacklogHigh
        expr: ingestion_pending_files > 100
        for: 10m
        labels:
          severity: warning

      - alert: DoclingTimeoutsHigh
        expr: rate(docling_requests_total{status="timeout"}[5m]) > 0.1
        for: 5m
        labels:
          severity: warning

      - alert: VoyageRateLimited
        expr: rate(voyage_requests_total{status="rate_limited"}[5m]) > 0.2
        for: 5m
        labels:
          severity: warning

      - alert: DLQGrowing
        expr: increase(dlq_items_total[1h]) > 10
        for: 15m
        labels:
          severity: warning
```

---

## 10. Makefile Targets

```makefile
# Ingestion Pipeline
.PHONY: ingest-setup ingest-run ingest-watch ingest-status ingest-dlq

ingest-setup: ## Setup Postgres schema + Qdrant collection
	docker exec dev-postgres psql -U postgres -f /docker-entrypoint-initdb.d/03-ingestion.sql
	uv run python scripts/setup_gdrive_collection.py

ingest-run: ## Run ingestion once
	uv run python -m src.ingestion.orchestrator --once

ingest-watch: ## Run continuous ingestion (60s poll)
	uv run python -m src.ingestion.orchestrator --watch

ingest-status: ## Show ingestion status
	uv run python scripts/ingestion_status.py

ingest-dlq: ## Show dead letter queue
	uv run python scripts/reprocess_dlq.py --dry-run

ingest-dlq-retry: ## Retry items from DLQ
	uv run python scripts/reprocess_dlq.py --limit 10

# rclone
.PHONY: sync-drive-install sync-drive-run sync-drive-status

sync-drive-install: ## Install rclone systemd timer
	sudo cp docker/rclone/rclone-sync.service /etc/systemd/system/
	sudo cp docker/rclone/rclone-sync.timer /etc/systemd/system/
	sudo systemctl daemon-reload
	sudo systemctl enable --now rclone-sync.timer

sync-drive-run: ## Run rclone sync manually
	/opt/scripts/sync-drive.sh

sync-drive-status: ## Check rclone timer status
	systemctl status rclone-sync.timer
	journalctl -u rclone-sync.service -n 20
```

---

## 11. Testing

### 11.1 Unit Tests

```python
# tests/unit/ingestion/test_orchestrator.py

class TestIngestionOrchestrator:
    async def test_detect_new_file(self):
        """New file in sync dir detected as NEW."""

    async def test_detect_modified_file(self):
        """Changed content_hash detected as MODIFIED."""

    async def test_detect_deleted_file(self):
        """File in DB but not filesystem detected as DELETED."""

    async def test_idempotent_processing(self):
        """Re-processing same file doesn't create duplicates."""


# tests/unit/ingestion/test_state_manager.py

class TestStateManager:
    async def test_state_transitions(self):
        """Test pending → processing → indexed flow."""

    async def test_error_retry_count(self):
        """Retry count increments on repeated errors."""
```

### 11.2 Integration Tests

```python
# tests/integration/test_ingestion_e2e.py

@pytest.mark.integration
class TestIngestionE2E:
    async def test_add_file_appears_in_qdrant(self):
        """Add file to sync dir → chunks in Qdrant."""

    async def test_modify_file_updates_chunks(self):
        """Modify file → old chunks deleted, new upserted."""

    async def test_delete_file_removes_chunks(self):
        """Delete file → all chunks removed from Qdrant."""

    async def test_docling_error_goes_to_dlq(self):
        """Docling failure → file in DLQ, not blocking pipeline."""
```

### 11.3 Acceptance Criteria

| Test | Expected |
|------|----------|
| Add file | Chunks in Qdrant within 10 min |
| Modify file | Old chunks deleted, new added |
| Delete file | All chunks removed |
| Rename file | DELETE + ADD (path-based file_id) |
| Docling error | File in DLQ, pipeline continues |
| Re-process | No duplicates (idempotent point_id) |
| 500K chunks | p95 search < 50ms |

---

## 12. Implementation Plan

### Phase 1: Foundation (Day 1-2)

1. [ ] Create `docker/postgres/init/03-ingestion.sql`
2. [ ] Create `scripts/setup_gdrive_collection.py`
3. [ ] Create `src/ingestion/state_manager.py`
4. [ ] Create `src/ingestion/dead_letter.py`
5. [ ] Unit tests for state manager

### Phase 2: Orchestrator (Day 3-4)

6. [ ] Create `src/ingestion/orchestrator.py`
7. [ ] Create `src/ingestion/file_processor.py`
8. [ ] Integrate with existing `docling_client.py`
9. [ ] Integrate with existing `gdrive_indexer.py`
10. [ ] Unit tests for orchestrator

### Phase 3: Automation (Day 5)

11. [ ] Create systemd units for rclone
12. [ ] Update Makefile targets
13. [ ] Integration tests

### Phase 4: Observability (Day 6)

14. [ ] Add Prometheus metrics
15. [ ] Create alert rules
16. [ ] Create `scripts/ingestion_status.py`
17. [ ] Update `docs/INGESTION.md`

### Phase 5: Testing & Docs (Day 7)

18. [ ] E2E tests with real files
19. [ ] Load test (500K chunks)
20. [ ] Runbook documentation
21. [ ] Final review and merge

---

## 13. Open Questions

1. **Bot collection:** Should `gdrive_documents` be separate or merge with `contextual_bulgaria_voyage`?
   - Option A: Separate, bot queries both
   - Option B: Single collection, all docs together

2. **drive_file_id manifest:** Implement now or defer?
   - MVP: path-based file_id (rename = delete+add)
   - Future: manifest for Drive ID stability

3. **Chunk-diff optimization:** Implement in MVP or defer?
   - MVP: DELETE all + UPSERT all
   - Future: Compare content_hash per chunk

---

## 14. References

- Original ТЗ: User-provided production spec
- Milestone J: `docs/plans/2026-02-02-milestone-j-ingestion-pipeline.md`
- GDrive docs: `docs/GDRIVE_INGESTION.md`
- CocoIndex: https://cocoindex.io/docs
