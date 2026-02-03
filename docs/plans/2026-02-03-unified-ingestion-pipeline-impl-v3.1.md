# Unified Ingestion Pipeline Implementation Plan (v3.1 - Full with Infrastructure)

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Complete unified ingestion pipeline with infrastructure: rclone systemd timer → Postgres state → Docling → Voyage+BM42 → Qdrant + monitoring/alerting.

**Architecture:**
```
Google Drive
     ↓ (systemd timer, 5min)
rclone sync → ~/drive-sync
     ↓ (60s poll)
UnifiedIngestionPipeline
     ├─ Postgres State (cocoindex.ingestion_state)
     ├─ DoclingClient (dev-docling:5001)
     ├─ VoyageService (telegram_bot/services/voyage.py)
     ├─ BM42 (FastEmbed local)
     └─ Qdrant (gdrive_documents_*)
     ↓
Monitoring (Loki + Alertmanager → Telegram)
```

**Tech Stack:** Python 3.12, asyncpg, Qdrant, Voyage AI, FastEmbed BM42, Docling, Redis, systemd

**Key Decisions:**
- ✅ **Reuse existing services** (VoyageService, CacheService, DoclingClient)
- ✅ **Use existing Postgres schema** (02-cocoindex.sql)
- ✅ **Fix payload contract** (page_content + metadata)
- ✅ **Replace cron with systemd timer** (better monitoring)
- ✅ **Add ingestion alerts** (Loki rules)
- ❌ **CocoIndex** - не используем (текущий подход проще и работает)

---

## Phase 1: Fix Payload Contract (Code)

### Task 1: Update GDriveIndexer Payload Format

**Files:**
- Modify: `src/ingestion/gdrive_indexer.py`
- Create: `tests/unit/ingestion/test_gdrive_indexer_payload.py`

**Step 1: Write failing test**

```python
# tests/unit/ingestion/test_gdrive_indexer_payload.py
"""Tests for gdrive indexer payload contract."""

import pytest
from unittest.mock import MagicMock


class TestGDriveIndexerPayload:
    """Test payload format for bot compatibility."""

    def test_payload_has_page_content_and_metadata(self):
        """Payload must have page_content and metadata dict."""
        from src.ingestion.gdrive_indexer import GDriveIndexer

        indexer = GDriveIndexer.__new__(GDriveIndexer)

        chunk = MagicMock()
        chunk.text = "Test content"
        chunk.chunk_id = 0
        chunk.document_name = "test.pdf"
        chunk.section = "Introduction"
        chunk.page_range = (1, 2)
        chunk.extra_metadata = {"headings": ["Title", "Intro"]}

        file_metadata = {
            "file_id": "abc123",
            "source_path": "docs/test.pdf",
            "mime_type": "application/pdf",
            "modified_time": "2026-02-03T12:00:00Z",
            "content_hash": "hash123",
        }

        payload = indexer._build_payload(chunk, file_metadata)

        # Required for retrieval
        assert "page_content" in payload
        assert payload["page_content"] == "Test content"

        # Required for small-to-big and citations
        assert "metadata" in payload
        assert isinstance(payload["metadata"], dict)
        assert payload["metadata"]["source"] == "docs/test.pdf"
        assert payload["metadata"]["file_id"] == "abc123"
        assert payload["metadata"]["headings"] == ["Title", "Intro"]

        # Keep flat file_id for delete operations
        assert payload["file_id"] == "abc123"
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/ingestion/test_gdrive_indexer_payload.py -v 2>&1 | head -20`

Expected: FAIL (no _build_payload method)

**Step 3: Implement _build_payload**

Add to `src/ingestion/gdrive_indexer.py` (around line 130):

```python
def _build_payload(self, chunk: Chunk, file_metadata: dict[str, Any]) -> dict[str, Any]:
    """Build Qdrant payload with bot-compatible format.

    Payload contract:
    - page_content: str - chunk text for retrieval
    - metadata: dict - for citations and small-to-big
    - file_id: str - flat, for delete operations

    Required by:
    - telegram_bot/services/qdrant.py (retrieval)
    - telegram_bot/services/small_to_big.py (parent lookup)
    """
    metadata = {
        # Identity
        "file_id": file_metadata.get("file_id"),
        "file_name": chunk.document_name,
        "source": file_metadata.get("source_path", ""),

        # Chunk position
        "chunk_id": chunk.chunk_id,
        "chunk_location": f"chunk_{chunk.chunk_id}",

        # Document structure
        "section": chunk.section,
        "page_range": list(chunk.page_range) if chunk.page_range else None,

        # File info
        "mime_type": file_metadata.get("mime_type"),
        "modified_time": file_metadata.get("modified_time"),
        "content_hash": file_metadata.get("content_hash"),
    }

    # Merge extra_metadata (headings, etc)
    if chunk.extra_metadata:
        for key, value in chunk.extra_metadata.items():
            if key not in metadata:
                metadata[key] = value

    return {
        "page_content": chunk.text,
        "metadata": metadata,
        "file_id": file_metadata.get("file_id"),  # Flat for delete
    }
```

**Step 4: Update index_file_chunks to use _build_payload**

Find where points are created and replace payload building:

```python
# In index_file_chunks, replace direct payload dict with:
payload = self._build_payload(chunk, file_metadata)
```

**Step 5: Run tests**

Run: `uv run pytest tests/unit/ingestion/test_gdrive_indexer_payload.py -v`

Expected: PASS

**Step 6: Commit**

```bash
git add src/ingestion/gdrive_indexer.py tests/unit/ingestion/test_gdrive_indexer_payload.py
git commit -m "fix(ingestion): update gdrive_indexer payload for bot compatibility

- Add page_content field (required by retrieval)
- Add nested metadata dict (required by small-to-big, citations)
- Keep flat file_id for delete operations"
```

---

## Phase 2: Postgres State Persistence (Code)

### Task 2: Create UnifiedStateManager

**Files:**
- Create: `src/ingestion/unified/__init__.py`
- Create: `src/ingestion/unified/state_manager.py`
- Reference: `docker/postgres/init/02-cocoindex.sql`

**Step 1: Verify existing schema**

Run: `docker exec dev-postgres psql -U postgres -d cocoindex -c "\\dt" 2>&1 | grep ingestion`

Expected: `ingestion_state` and `ingestion_dead_letter` tables

If tables don't exist:
Run: `docker exec dev-postgres psql -U postgres -f /docker-entrypoint-initdb.d/02-cocoindex.sql`

**Step 2: Create state_manager.py**

```python
# src/ingestion/unified/state_manager.py
"""State manager using existing cocoindex.ingestion_state table."""

from dataclasses import dataclass
from datetime import datetime
from typing import Any

import asyncpg


@dataclass
class FileState:
    """Maps to cocoindex.ingestion_state table."""
    file_id: str
    drive_id: str | None = None
    folder_id: str | None = None
    file_name: str | None = None
    mime_type: str | None = None
    modified_time: datetime | None = None
    content_hash: str | None = None
    parser_version: str | None = None
    chunker_version: str | None = None
    embedding_model: str = "voyage-4-large"
    chunk_count: int = 0
    indexed_at: datetime | None = None
    status: str = "pending"
    error_message: str | None = None
    retry_count: int = 0

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> "FileState":
        return cls(**{k: v for k, v in row.items() if k in cls.__dataclass_fields__})


class UnifiedStateManager:
    """Manages ingestion state using existing Postgres tables."""

    def __init__(
        self,
        pool: asyncpg.Pool | None = None,
        database_url: str | None = None,
    ):
        self._pool = pool
        self._database_url = database_url
        self._owns_pool = pool is None
        self._table = "cocoindex.ingestion_state"
        self._dlq_table = "cocoindex.ingestion_dead_letter"

    async def _get_pool(self) -> asyncpg.Pool:
        if self._pool is None:
            if self._database_url is None:
                raise ValueError("Either pool or database_url required")
            self._pool = await asyncpg.create_pool(self._database_url)
        return self._pool

    async def close(self) -> None:
        if self._owns_pool and self._pool:
            await self._pool.close()
            self._pool = None

    async def get_state(self, file_id: str) -> FileState | None:
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                f"SELECT * FROM {self._table} WHERE file_id = $1", file_id
            )
            return FileState.from_row(dict(row)) if row else None

    async def upsert_state(self, state: FileState) -> None:
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                f"""
                INSERT INTO {self._table} (
                    file_id, drive_id, folder_id, file_name, mime_type,
                    modified_time, content_hash, parser_version, chunker_version,
                    embedding_model, chunk_count, status, error_message, retry_count
                ) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14)
                ON CONFLICT (file_id) DO UPDATE SET
                    file_name = EXCLUDED.file_name,
                    mime_type = EXCLUDED.mime_type,
                    content_hash = EXCLUDED.content_hash,
                    parser_version = EXCLUDED.parser_version,
                    chunker_version = EXCLUDED.chunker_version,
                    status = EXCLUDED.status,
                    error_message = EXCLUDED.error_message,
                    retry_count = EXCLUDED.retry_count
                """,
                state.file_id, state.drive_id, state.folder_id, state.file_name,
                state.mime_type, state.modified_time, state.content_hash,
                state.parser_version, state.chunker_version, state.embedding_model,
                state.chunk_count, state.status, state.error_message, state.retry_count,
            )

    async def mark_indexed(self, file_id: str, chunk_count: int) -> None:
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                f"""
                UPDATE {self._table}
                SET status = 'indexed', chunk_count = $2, indexed_at = NOW(), error_message = NULL
                WHERE file_id = $1
                """,
                file_id, chunk_count,
            )

    async def mark_error(self, file_id: str, error: str) -> None:
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                f"""
                UPDATE {self._table}
                SET status = 'error', error_message = $2, retry_count = retry_count + 1
                WHERE file_id = $1
                """,
                file_id, error,
            )

    async def mark_deleted(self, file_id: str) -> None:
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                f"UPDATE {self._table} SET status = 'deleted' WHERE file_id = $1",
                file_id,
            )

    async def get_all_indexed_file_ids(self) -> set[str]:
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                f"SELECT file_id FROM {self._table} WHERE status = 'indexed'"
            )
            return {row["file_id"] for row in rows}

    async def get_pending_files(self, limit: int = 100) -> list[FileState]:
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                f"""
                SELECT * FROM {self._table}
                WHERE status IN ('pending', 'error') AND retry_count < 3
                ORDER BY modified_time ASC NULLS LAST LIMIT $1
                """,
                limit,
            )
            return [FileState.from_row(dict(row)) for row in rows]

    async def add_to_dlq(self, file_id: str, error_type: str, error_message: str, payload: dict | None = None) -> int:
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                f"""
                INSERT INTO {self._dlq_table} (file_id, error_type, error_message, payload)
                VALUES ($1, $2, $3, $4) RETURNING id
                """,
                file_id, error_type, error_message, payload,
            )
            return row["id"]

    async def get_stats(self) -> dict[str, int]:
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                f"SELECT status, COUNT(*) as count FROM {self._table} GROUP BY status"
            )
            return {row["status"]: row["count"] for row in rows}
```

**Step 3: Create __init__.py**

```python
# src/ingestion/unified/__init__.py
"""Unified ingestion pipeline components."""

from src.ingestion.unified.state_manager import UnifiedStateManager, FileState

__all__ = ["UnifiedStateManager", "FileState"]
```

**Step 4: Verify import**

Run: `uv run python -c "from src.ingestion.unified import UnifiedStateManager; print('OK')"`

Expected: `OK`

**Step 5: Commit**

```bash
git add src/ingestion/unified/
git commit -m "feat(ingestion): add UnifiedStateManager using existing Postgres schema"
```

---

## Phase 3: Unified Pipeline Orchestrator (Code)

### Task 3: Create UnifiedIngestionPipeline

**Files:**
- Create: `src/ingestion/unified/pipeline.py`

**Step 1: Create pipeline.py**

```python
# src/ingestion/unified/pipeline.py
"""Unified ingestion pipeline reusing existing services.

Components:
- VoyageService (telegram_bot/services/voyage.py)
- DoclingClient (src/ingestion/docling_client.py)
- GDriveIndexer (src/ingestion/gdrive_indexer.py)
- UnifiedStateManager (Postgres state)
"""

import hashlib
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from src.ingestion.unified.state_manager import UnifiedStateManager, FileState

logger = logging.getLogger(__name__)

SUPPORTED_EXTENSIONS = {".pdf", ".docx", ".xlsx", ".pptx", ".md", ".txt", ".html", ".csv"}


def compute_file_id(sync_dir: Path, file_path: Path) -> str:
    """SHA256(relative_path)[:16] - same as gdrive_flow.py"""
    relative = file_path.relative_to(sync_dir)
    return hashlib.sha256(str(relative).encode()).hexdigest()[:16]


def compute_content_hash(file_path: Path) -> str:
    """SHA256(content)[:16] for change detection."""
    hasher = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            hasher.update(chunk)
    return hasher.hexdigest()[:16]


@dataclass
class ProcessingStats:
    files_seen: int = 0
    files_processed: int = 0
    files_skipped: int = 0
    files_failed: int = 0
    files_deleted: int = 0
    chunks_indexed: int = 0


class UnifiedIngestionPipeline:
    """Orchestrates unified ingestion with Postgres state tracking."""

    def __init__(
        self,
        state_manager: UnifiedStateManager,
        indexer: Any,  # GDriveIndexer
        sync_dir: Path | str,
        docling_client: Any | None = None,
        collection_name: str = "gdrive_documents_binary",
        parser_version: str = "docling-2.1",
        chunker_version: str = "hybrid-1.0",
    ):
        self.state_manager = state_manager
        self.indexer = indexer
        self.sync_dir = Path(sync_dir)
        self.docling_client = docling_client
        self.collection_name = collection_name
        self.parser_version = parser_version
        self.chunker_version = chunker_version

    def _is_supported(self, path: Path) -> bool:
        if path.name.startswith(".") or path.name.startswith("~$"):
            return False
        return path.suffix.lower() in SUPPORTED_EXTENSIONS

    def _scan_files(self) -> dict[str, Path]:
        files = {}
        for path in self.sync_dir.rglob("*"):
            if path.is_file() and self._is_supported(path):
                file_id = compute_file_id(self.sync_dir, path)
                files[file_id] = path
        return files

    async def detect_changes(self) -> list[tuple[str, Path, str]]:
        """Returns [(file_id, path, change_type), ...]"""
        changes = []
        current_files = self._scan_files()
        current_ids = set(current_files.keys())
        indexed_ids = await self.state_manager.get_all_indexed_file_ids()

        # New and modified
        for file_id, path in current_files.items():
            if file_id not in indexed_ids:
                changes.append((file_id, path, "new"))
            else:
                state = await self.state_manager.get_state(file_id)
                if state and state.content_hash:
                    current_hash = compute_content_hash(path)
                    if current_hash != state.content_hash:
                        changes.append((file_id, path, "modified"))

        # Deleted
        for file_id in indexed_ids - current_ids:
            changes.append((file_id, Path(""), "deleted"))

        return changes

    async def _parse_and_chunk(self, file_path: Path) -> list:
        if self.docling_client:
            chunks = await self.docling_client.chunk_file(file_path)
            return self.docling_client.to_ingestion_chunks(
                chunks, source=str(file_path.relative_to(self.sync_dir)), source_type="gdrive"
            )
        else:
            # Fallback
            from src.ingestion.chunker import DocumentChunker, ChunkingStrategy
            text = file_path.read_text(encoding="utf-8", errors="ignore")
            chunker = DocumentChunker(strategy=ChunkingStrategy.FIXED_SIZE)
            return chunker.chunk_text(text, file_path.name)

    async def process_file(self, file_id: str, file_path: Path) -> bool:
        relative_path = str(file_path.relative_to(self.sync_dir))

        try:
            state = FileState(
                file_id=file_id,
                file_name=file_path.name,
                mime_type=self._get_mime_type(file_path),
                content_hash=compute_content_hash(file_path),
                parser_version=self.parser_version,
                chunker_version=self.chunker_version,
                status="processing",
            )
            await self.state_manager.upsert_state(state)

            chunks = await self._parse_and_chunk(file_path)
            if not chunks:
                await self.state_manager.mark_indexed(file_id, 0)
                return True

            file_metadata = {
                "file_id": file_id,
                "source_path": relative_path,
                "mime_type": state.mime_type,
                "content_hash": state.content_hash,
            }

            stats = await self.indexer.index_file_chunks(
                chunks=chunks,
                file_id=file_id,
                collection_name=self.collection_name,
                file_metadata=file_metadata,
            )

            await self.state_manager.mark_indexed(file_id, stats.indexed)
            logger.info(f"Indexed {file_path.name}: {stats.indexed} chunks")
            return True

        except Exception as e:
            logger.error(f"Error processing {file_path}: {e}")
            await self.state_manager.mark_error(file_id, str(e))

            # Check if should go to DLQ
            state = await self.state_manager.get_state(file_id)
            if state and state.retry_count >= 3:
                await self.state_manager.add_to_dlq(file_id, type(e).__name__, str(e))
            return False

    async def process_deletion(self, file_id: str) -> bool:
        try:
            await self.indexer.delete_file_points(file_id, self.collection_name)
            await self.state_manager.mark_deleted(file_id)
            logger.info(f"Deleted file_id={file_id}")
            return True
        except Exception as e:
            logger.error(f"Error deleting {file_id}: {e}")
            return False

    async def run_once(self) -> ProcessingStats:
        stats = ProcessingStats()
        changes = await self.detect_changes()
        stats.files_seen = len(changes)

        for file_id, path, change_type in changes:
            if change_type == "deleted":
                if await self.process_deletion(file_id):
                    stats.files_deleted += 1
                else:
                    stats.files_failed += 1
            else:
                if await self.process_file(file_id, path):
                    stats.files_processed += 1
                else:
                    stats.files_failed += 1

        return stats

    def _get_mime_type(self, path: Path) -> str:
        return {
            ".pdf": "application/pdf",
            ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            ".md": "text/markdown",
            ".txt": "text/plain",
            ".html": "text/html",
            ".csv": "text/csv",
        }.get(path.suffix.lower(), "application/octet-stream")
```

**Step 2: Commit**

```bash
git add src/ingestion/unified/pipeline.py
git commit -m "feat(ingestion): add UnifiedIngestionPipeline orchestrator"
```

---

## Phase 4: rclone Systemd Timer (Infrastructure)

### Task 4: Create Systemd Service and Timer

**Files:**
- Create: `docker/rclone/rclone-sync.service`
- Create: `docker/rclone/rclone-sync.timer`
- Modify: `Makefile` (add install targets)

**Step 1: Create systemd service**

```ini
# docker/rclone/rclone-sync.service
[Unit]
Description=Sync Google Drive via rclone
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
User=user
Environment="GDRIVE_SYNC_DIR=/home/user/drive-sync"
Environment="RCLONE_CONFIG=/home/user/projects/rag-fresh/docker/rclone/rclone.conf"
ExecStart=/home/user/projects/rag-fresh/docker/rclone/sync-drive.sh
StandardOutput=journal
StandardError=journal

# Prevent concurrent runs
ExecStartPre=/usr/bin/flock -n /tmp/rclone-sync.lock echo "Acquiring lock"

[Install]
WantedBy=multi-user.target
```

**Step 2: Create systemd timer**

```ini
# docker/rclone/rclone-sync.timer
[Unit]
Description=Run rclone sync every 5 minutes

[Timer]
OnBootSec=2min
OnUnitActiveSec=5min
AccuracySec=1min
RandomizedDelaySec=30

[Install]
WantedBy=timers.target
```

**Step 3: Add Makefile targets**

```makefile
# In Makefile, add to rclone section:

.PHONY: sync-drive-systemd-install sync-drive-systemd-status sync-drive-systemd-logs

sync-drive-systemd-install: ## Install rclone systemd timer (replaces cron)
	sudo cp docker/rclone/rclone-sync.service /etc/systemd/system/
	sudo cp docker/rclone/rclone-sync.timer /etc/systemd/system/
	sudo systemctl daemon-reload
	sudo systemctl enable rclone-sync.timer
	sudo systemctl start rclone-sync.timer
	@echo "Systemd timer installed. Check status with: make sync-drive-systemd-status"

sync-drive-systemd-status: ## Check rclone systemd timer status
	systemctl status rclone-sync.timer
	systemctl list-timers rclone-sync.timer

sync-drive-systemd-logs: ## Show rclone sync logs from journalctl
	journalctl -u rclone-sync.service -n 50 --no-pager
```

**Step 4: Verify files created**

Run: `ls -la docker/rclone/*.service docker/rclone/*.timer 2>/dev/null || echo "Files need to be created"`

**Step 5: Commit**

```bash
git add docker/rclone/rclone-sync.service docker/rclone/rclone-sync.timer
git commit -m "feat(infra): add rclone systemd timer (replaces cron)

- rclone-sync.service: oneshot service with lock
- rclone-sync.timer: 5min interval with jitter
- Logs to journalctl instead of files"
```

---

## Phase 5: Monitoring & Alerting (Infrastructure)

### Task 5: Add Ingestion Alert Rules

**Files:**
- Create: `docker/monitoring/rules/ingestion.yaml`

**Step 1: Create alert rules**

```yaml
# docker/monitoring/rules/ingestion.yaml
# Alert rules for unified ingestion pipeline

groups:
  - name: ingestion
    rules:
      # rclone sync alerts
      - alert: RcloneSyncNotRunning
        expr: |
          (time() - systemd_unit_last_active_timestamp_seconds{name="rclone-sync.service"}) > 900
        for: 5m
        labels:
          severity: warning
          service: rclone
        annotations:
          summary: "rclone sync hasn't run in 15 minutes"
          description: "Last run: {{ $value | humanizeDuration }} ago"

      - alert: RcloneSyncFailed
        expr: |
          systemd_unit_state{name="rclone-sync.service", state="failed"} == 1
        for: 1m
        labels:
          severity: critical
          service: rclone
        annotations:
          summary: "rclone sync service failed"
          description: "Check logs: journalctl -u rclone-sync.service"

      # Docling alerts
      - alert: DoclingHighErrorRate
        expr: |
          sum(rate(docling_conversion_errors_total[5m])) > 0.1
        for: 5m
        labels:
          severity: warning
          service: docling
        annotations:
          summary: "Docling conversion error rate high"
          description: "{{ $value | humanizePercentage }} errors in last 5 min"

      - alert: DoclingSlowConversion
        expr: |
          histogram_quantile(0.95, rate(docling_conversion_duration_seconds_bucket[5m])) > 120
        for: 10m
        labels:
          severity: warning
          service: docling
        annotations:
          summary: "Docling conversion taking >2min (p95)"
          description: "p95 latency: {{ $value | humanizeDuration }}"

      # Ingestion pipeline alerts
      - alert: IngestionPipelineStalled
        expr: |
          increase(ingestion_files_processed_total[1h]) == 0
          and
          ingestion_pending_files > 0
        for: 30m
        labels:
          severity: warning
          service: ingestion
        annotations:
          summary: "Ingestion pipeline stalled with pending files"
          description: "{{ $value }} files pending, none processed in 1h"

      - alert: IngestionHighFailureRate
        expr: |
          rate(ingestion_files_failed_total[15m])
          / rate(ingestion_files_processed_total[15m]) > 0.1
        for: 15m
        labels:
          severity: warning
          service: ingestion
        annotations:
          summary: "Ingestion failure rate >10%"
          description: "{{ $value | humanizePercentage }} of files failing"

      - alert: IngestionDLQGrowing
        expr: |
          increase(ingestion_dlq_items_total[1h]) > 5
        for: 15m
        labels:
          severity: warning
          service: ingestion
        annotations:
          summary: "Dead letter queue growing"
          description: "{{ $value }} items added to DLQ in last hour"

      ***REMOVED*** API alerts
      - alert: VoyageRateLimited
        expr: |
          rate(voyage_requests_total{status="rate_limited"}[5m]) > 0.1
        for: 5m
        labels:
          severity: warning
          service: voyage
        annotations:
          summary: "Voyage API rate limited"
          description: "Consider reducing batch concurrency"

      ***REMOVED*** indexing alerts
      - alert: QdrantIndexErrors
        expr: |
          rate(qdrant_upsert_errors_total[5m]) > 0.05
        for: 5m
        labels:
          severity: warning
          service: qdrant
        annotations:
          summary: "Qdrant upsert errors detected"
          description: "{{ $value | humanizePercentage }} error rate"
```

**Step 2: Verify existing alert infrastructure**

Run: `ls docker/monitoring/rules/`

Expected: Shows existing rule files

**Step 3: Commit**

```bash
git add docker/monitoring/rules/ingestion.yaml
git commit -m "feat(monitoring): add ingestion pipeline alert rules

- rclone sync monitoring (not running, failed)
- Docling errors and latency
- Pipeline stall and failure rate
- DLQ growth
- Voyage rate limiting
- Qdrant index errors"
```

---

## Phase 6: CLI and Integration (Code)

### Task 6: Create CLI Entry Point

**Files:**
- Create: `src/ingestion/unified/cli.py`

**Step 1: Create CLI**

```python
# src/ingestion/unified/cli.py
"""CLI for unified ingestion pipeline."""

import argparse
import asyncio
import logging
import os
import sys
from pathlib import Path

from dotenv import load_dotenv


def setup_logging(verbose: bool = False):
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )


async def run_ingestion(args):
    import asyncpg

    from src.ingestion.unified.state_manager import UnifiedStateManager
    from src.ingestion.unified.pipeline import UnifiedIngestionPipeline
    from src.ingestion.gdrive_indexer import GDriveIndexer
    from src.ingestion.docling_client import DoclingClient, DoclingConfig

    sync_dir = Path(os.getenv("GDRIVE_SYNC_DIR", os.path.expanduser("~/drive-sync")))
    database_url = os.getenv("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/cocoindex")
    collection = os.getenv("GDRIVE_COLLECTION_NAME", "gdrive_documents_binary")

    if not sync_dir.exists():
        logging.error(f"Sync dir not found: {sync_dir}")
        return 1

    pool = await asyncpg.create_pool(database_url)

    try:
        state_manager = UnifiedStateManager(pool=pool)

        indexer = GDriveIndexer(
            qdrant_url=os.getenv("QDRANT_URL", "http://localhost:6333"),
            voyage_api_key=os.getenv("VOYAGE_API_KEY"),
        )

        docling_config = DoclingConfig(base_url=os.getenv("DOCLING_URL", "http://localhost:5001"))

        async with DoclingClient(docling_config) as docling:
            pipeline = UnifiedIngestionPipeline(
                state_manager=state_manager,
                indexer=indexer,
                sync_dir=sync_dir,
                docling_client=docling,
                collection_name=collection,
            )

            if args.watch:
                logging.info(f"Watching {sync_dir} (interval={args.interval}s)")
                while True:
                    stats = await pipeline.run_once()
                    if stats.files_processed or stats.files_deleted:
                        logging.info(
                            f"Processed: {stats.files_processed}, "
                            f"Failed: {stats.files_failed}, "
                            f"Deleted: {stats.files_deleted}"
                        )
                    await asyncio.sleep(args.interval)
            else:
                stats = await pipeline.run_once()
                logging.info(
                    f"Done: {stats.files_processed} processed, "
                    f"{stats.files_failed} failed, {stats.files_deleted} deleted"
                )
    finally:
        await pool.close()

    return 0


async def show_status(args):
    import asyncpg
    from src.ingestion.unified.state_manager import UnifiedStateManager

    database_url = os.getenv("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/cocoindex")

    pool = await asyncpg.create_pool(database_url)
    try:
        manager = UnifiedStateManager(pool=pool)
        stats = await manager.get_stats()

        print("\n=== Ingestion Status ===")
        total = sum(stats.values())
        for status, count in sorted(stats.items()):
            pct = count / total * 100 if total else 0
            print(f"  {status}: {count} ({pct:.1f}%)")
        print(f"  TOTAL: {total}")
    finally:
        await pool.close()


def main():
    load_dotenv()

    parser = argparse.ArgumentParser(description="Unified Ingestion Pipeline")
    subparsers = parser.add_subparsers(dest="command", required=True)

    run_p = subparsers.add_parser("run", help="Run ingestion")
    run_p.add_argument("--watch", action="store_true", help="Continuous mode")
    run_p.add_argument("--interval", type=int, default=60, help="Poll interval (s)")
    run_p.add_argument("-v", "--verbose", action="store_true")

    status_p = subparsers.add_parser("status", help="Show status")
    status_p.add_argument("-v", "--verbose", action="store_true")

    args = parser.parse_args()
    setup_logging(getattr(args, "verbose", False))

    if args.command == "run":
        return asyncio.run(run_ingestion(args))
    elif args.command == "status":
        return asyncio.run(show_status(args))


if __name__ == "__main__":
    sys.exit(main())
```

**Step 2: Commit**

```bash
git add src/ingestion/unified/cli.py
git commit -m "feat(ingestion): add unified pipeline CLI"
```

---

### Task 7: Update Makefile

**Files:**
- Modify: `Makefile`

**Step 1: Add unified targets**

Add to ingestion section:

```makefile
# Unified Ingestion Pipeline (v3.1)
.PHONY: ingest-unified ingest-unified-watch ingest-unified-status

ingest-unified: ## Run unified ingestion once
	set -a && source .env && set +a && uv run python -m src.ingestion.unified.cli run

ingest-unified-watch: ## Run unified ingestion continuously (60s poll)
	set -a && source .env && set +a && uv run python -m src.ingestion.unified.cli run --watch

ingest-unified-status: ## Show unified ingestion status from Postgres
	set -a && source .env && set +a && uv run python -m src.ingestion.unified.cli status
```

**Step 2: Verify**

Run: `make help | grep unified`

Expected: Shows unified targets

**Step 3: Commit**

```bash
git add Makefile
git commit -m "feat(ingestion): add Makefile targets for unified pipeline"
```

---

## Phase 7: Integration Test

### Task 8: End-to-End Test

**Files:**
- Create: `tests/integration/test_unified_e2e.py`

**Step 1: Create E2E test**

```python
# tests/integration/test_unified_e2e.py
"""E2E test for unified ingestion pipeline."""

import os
import pytest
from pathlib import Path

pytestmark = pytest.mark.skipif(
    not os.getenv("RUN_INTEGRATION_TESTS"),
    reason="Set RUN_INTEGRATION_TESTS=1"
)


@pytest.mark.asyncio
async def test_unified_pipeline_e2e(tmp_path):
    """File goes through pipeline with correct payload format."""
    import asyncpg
    from qdrant_client import QdrantClient

    from src.ingestion.unified.state_manager import UnifiedStateManager
    from src.ingestion.unified.pipeline import UnifiedIngestionPipeline, compute_file_id
    from src.ingestion.gdrive_indexer import GDriveIndexer

    # Create test file
    test_file = tmp_path / "test.md"
    test_file.write_text("# Test\n\nContent for unified pipeline test.")

    database_url = os.getenv("DATABASE_URL")
    qdrant_url = os.getenv("QDRANT_URL", "http://localhost:6333")
    collection = "test_unified_e2e"

    pool = await asyncpg.create_pool(database_url)

    try:
        state_manager = UnifiedStateManager(pool=pool)
        indexer = GDriveIndexer(
            qdrant_url=qdrant_url,
            voyage_api_key=os.getenv("VOYAGE_API_KEY"),
        )

        pipeline = UnifiedIngestionPipeline(
            state_manager=state_manager,
            indexer=indexer,
            sync_dir=tmp_path,
            collection_name=collection,
        )

        stats = await pipeline.run_once()
        assert stats.files_processed == 1

        # Verify payload format
        qdrant = QdrantClient(url=qdrant_url)
        file_id = compute_file_id(tmp_path, test_file)

        results, _ = qdrant.scroll(
            collection_name=collection,
            scroll_filter={"must": [{"key": "file_id", "match": {"value": file_id}}]},
            limit=10,
            with_payload=True,
        )

        assert len(results) > 0
        payload = results[0].payload

        # Check payload contract
        assert "page_content" in payload
        assert "metadata" in payload
        assert isinstance(payload["metadata"], dict)
        assert payload["metadata"]["file_id"] == file_id

        # Cleanup
        await indexer.delete_file_points(file_id, collection)

    finally:
        await pool.close()
```

**Step 2: Run test**

Run: `RUN_INTEGRATION_TESTS=1 uv run pytest tests/integration/test_unified_e2e.py -v`

Expected: PASS

**Step 3: Commit**

```bash
git add tests/integration/test_unified_e2e.py
git commit -m "test(ingestion): add E2E test for unified pipeline"
```

---

## Summary

### Files Created

| File | Purpose |
|------|---------|
| `src/ingestion/unified/__init__.py` | Module exports |
| `src/ingestion/unified/state_manager.py` | Postgres state tracking |
| `src/ingestion/unified/pipeline.py` | Pipeline orchestrator |
| `src/ingestion/unified/cli.py` | CLI entry point |
| `docker/rclone/rclone-sync.service` | Systemd service |
| `docker/rclone/rclone-sync.timer` | Systemd timer (5min) |
| `docker/monitoring/rules/ingestion.yaml` | Alert rules |
| `tests/unit/ingestion/test_gdrive_indexer_payload.py` | Payload test |
| `tests/integration/test_unified_e2e.py` | E2E test |

### Files Modified

| File | Change |
|------|--------|
| `src/ingestion/gdrive_indexer.py` | Fixed payload contract |
| `Makefile` | Added unified targets |

### Components Reused (NOT duplicated)

| Component | Source | Usage |
|-----------|--------|-------|
| VoyageService | `telegram_bot/services/voyage.py` | Embeddings in GDriveIndexer |
| CacheService | `telegram_bot/services/cache.py` | Available (optional) |
| DoclingClient | `src/ingestion/docling_client.py` | Parsing |
| GDriveIndexer | `src/ingestion/gdrive_indexer.py` | Qdrant indexing |
| Postgres schema | `docker/postgres/init/02-cocoindex.sql` | State tracking |

### Infrastructure Added

| Component | Type | Purpose |
|-----------|------|---------|
| rclone-sync.timer | systemd | Replace cron (better monitoring) |
| ingestion.yaml | Loki rules | Pipeline alerts |

### Verification Commands

```bash
# Install systemd timer
make sync-drive-systemd-install
make sync-drive-systemd-status

# Run tests
uv run pytest tests/unit/ingestion/test_gdrive_indexer_payload.py -v
uv run pytest tests/integration/test_unified_e2e.py -v

# Check status
make ingest-unified-status

# Run once
make ingest-unified

# Watch mode
make ingest-unified-watch
```
