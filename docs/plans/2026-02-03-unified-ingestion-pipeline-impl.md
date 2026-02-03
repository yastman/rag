# Unified Ingestion Pipeline Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build production ingestion pipeline: rclone sync → CocoIndex orchestrator → Postgres state → docling → Voyage+BM42 → Qdrant

**Architecture:** rclone syncs Drive to `/data/drive-sync` (systemd timer, 5min). Orchestrator polls filesystem (60s), tracks state in Postgres, processes changes through docling chunking, embeds with Voyage+BM42, upserts to Qdrant with idempotent point IDs. Failed files go to DLQ.

**Tech Stack:** Python 3.12, asyncpg, Qdrant, Voyage AI, FastEmbed BM42, docling-serve, systemd

---

## Phase 1: Postgres Schema

### Task 1: Create Ingestion State Tables

**Files:**
- Create: `docker/postgres/init/03-ingestion.sql`

**Step 1: Create the SQL schema file**

```sql
-- docker/postgres/init/03-ingestion.sql
-- Ingestion state tracking for GDrive pipeline

-- Main state table
CREATE TABLE IF NOT EXISTS ingestion_state (
    id SERIAL PRIMARY KEY,
    file_id VARCHAR(64) UNIQUE NOT NULL,
    source_path VARCHAR(1000) NOT NULL,
    file_name VARCHAR(500),
    mime_type VARCHAR(100),
    file_size BIGINT,
    content_hash VARCHAR(64),
    status VARCHAR(20) DEFAULT 'pending',
    chunk_count INTEGER DEFAULT 0,
    parser_version VARCHAR(20),
    embedding_version VARCHAR(20),
    pipeline_version VARCHAR(20) DEFAULT 'v1.0',
    file_modified_at TIMESTAMPTZ,
    indexed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    error_message TEXT,
    retry_count INTEGER DEFAULT 0,
    last_error_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_ingestion_file_id ON ingestion_state(file_id);
CREATE INDEX IF NOT EXISTS idx_ingestion_status ON ingestion_state(status);
CREATE INDEX IF NOT EXISTS idx_ingestion_source_path ON ingestion_state(source_path);

-- Dead letter queue
CREATE TABLE IF NOT EXISTS dead_letter_queue (
    id SERIAL PRIMARY KEY,
    file_id VARCHAR(64) NOT NULL,
    source_path VARCHAR(1000),
    error_type VARCHAR(100),
    error_message TEXT,
    stack_trace TEXT,
    payload JSONB,
    retry_count INTEGER DEFAULT 0,
    max_retries INTEGER DEFAULT 3,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    last_retry_at TIMESTAMPTZ,
    resolved_at TIMESTAMPTZ,
    resolved_by VARCHAR(100)
);

CREATE INDEX IF NOT EXISTS idx_dlq_file_id ON dead_letter_queue(file_id);
CREATE INDEX IF NOT EXISTS idx_dlq_unresolved ON dead_letter_queue(resolved_at) WHERE resolved_at IS NULL;

-- Sync status
CREATE TABLE IF NOT EXISTS sync_status (
    id SERIAL PRIMARY KEY,
    sync_type VARCHAR(50) DEFAULT 'rclone',
    started_at TIMESTAMPTZ NOT NULL,
    completed_at TIMESTAMPTZ,
    status VARCHAR(20),
    files_added INTEGER DEFAULT 0,
    files_modified INTEGER DEFAULT 0,
    files_deleted INTEGER DEFAULT 0,
    duration_seconds FLOAT,
    error_message TEXT
);

CREATE INDEX IF NOT EXISTS idx_sync_completed ON sync_status(completed_at DESC);
```

**Step 2: Apply schema to running Postgres**

Run: `docker exec dev-postgres psql -U postgres -f /docker-entrypoint-initdb.d/03-ingestion.sql 2>&1`

Expected: Tables created (or "already exists" if re-run)

**Step 3: Verify tables exist**

Run: `docker exec dev-postgres psql -U postgres -c "SELECT table_name FROM information_schema.tables WHERE table_name LIKE 'ingestion%' OR table_name LIKE 'dead_%' OR table_name LIKE 'sync_%';"`

Expected:
```
    table_name
-------------------
 ingestion_state
 dead_letter_queue
 sync_status
```

**Step 4: Commit**

```bash
git add docker/postgres/init/03-ingestion.sql
git commit -m "feat(ingestion): add Postgres schema for state tracking and DLQ"
```

---

### Task 2: Create StateManager Class

**Files:**
- Create: `src/ingestion/state_manager.py`
- Create: `tests/unit/ingestion/test_state_manager.py`

**Step 1: Write failing test for StateManager**

```python
# tests/unit/ingestion/test_state_manager.py
"""Tests for ingestion state manager."""

import pytest
from datetime import datetime, UTC
from unittest.mock import AsyncMock, MagicMock, patch


class TestStateManager:
    """Test StateManager operations."""

    @pytest.fixture
    def mock_pool(self):
        """Create mock asyncpg pool."""
        pool = AsyncMock()
        pool.acquire = AsyncMock()
        return pool

    @pytest.mark.asyncio
    async def test_get_state_returns_none_for_unknown_file(self, mock_pool):
        """get_state returns None for non-existent file_id."""
        from src.ingestion.state_manager import StateManager

        mock_conn = AsyncMock()
        mock_conn.fetchrow = AsyncMock(return_value=None)
        mock_pool.acquire.return_value.__aenter__.return_value = mock_conn

        manager = StateManager(pool=mock_pool)
        result = await manager.get_state("unknown_file_id")

        assert result is None
        mock_conn.fetchrow.assert_called_once()

    @pytest.mark.asyncio
    async def test_upsert_state_creates_new_record(self, mock_pool):
        """upsert_state creates new record for new file."""
        from src.ingestion.state_manager import StateManager, FileState

        mock_conn = AsyncMock()
        mock_conn.execute = AsyncMock()
        mock_pool.acquire.return_value.__aenter__.return_value = mock_conn

        manager = StateManager(pool=mock_pool)
        state = FileState(
            file_id="abc123",
            source_path="Test/doc.pdf",
            file_name="doc.pdf",
            content_hash="hash123",
            status="pending",
        )
        await manager.upsert_state(state)

        mock_conn.execute.assert_called_once()
        call_args = mock_conn.execute.call_args[0][0]
        assert "INSERT INTO ingestion_state" in call_args

    @pytest.mark.asyncio
    async def test_mark_indexed_updates_status(self, mock_pool):
        """mark_indexed updates status and chunk_count."""
        from src.ingestion.state_manager import StateManager

        mock_conn = AsyncMock()
        mock_conn.execute = AsyncMock()
        mock_pool.acquire.return_value.__aenter__.return_value = mock_conn

        manager = StateManager(pool=mock_pool)
        await manager.mark_indexed("abc123", chunk_count=15)

        mock_conn.execute.assert_called_once()
        call_args = mock_conn.execute.call_args[0]
        assert "status = 'indexed'" in call_args[0]

    @pytest.mark.asyncio
    async def test_mark_deleted_updates_status(self, mock_pool):
        """mark_deleted sets status to deleted."""
        from src.ingestion.state_manager import StateManager

        mock_conn = AsyncMock()
        mock_conn.execute = AsyncMock()
        mock_pool.acquire.return_value.__aenter__.return_value = mock_conn

        manager = StateManager(pool=mock_pool)
        await manager.mark_deleted("abc123")

        mock_conn.execute.assert_called_once()
        call_args = mock_conn.execute.call_args[0]
        assert "status = 'deleted'" in call_args[0]

    @pytest.mark.asyncio
    async def test_get_all_active_file_ids(self, mock_pool):
        """get_all_active_file_ids returns non-deleted files."""
        from src.ingestion.state_manager import StateManager

        mock_conn = AsyncMock()
        mock_conn.fetch = AsyncMock(return_value=[
            {"file_id": "abc123"},
            {"file_id": "def456"},
        ])
        mock_pool.acquire.return_value.__aenter__.return_value = mock_conn

        manager = StateManager(pool=mock_pool)
        result = await manager.get_all_active_file_ids()

        assert result == {"abc123", "def456"}
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/ingestion/test_state_manager.py -v 2>&1 | head -30`

Expected: FAIL with "ModuleNotFoundError" or "ImportError"

**Step 3: Implement StateManager**

```python
# src/ingestion/state_manager.py
"""Postgres state manager for ingestion pipeline."""

from dataclasses import dataclass, field
from datetime import datetime, UTC
from typing import Any

import asyncpg


@dataclass
class FileState:
    """State of a file in the ingestion pipeline."""

    file_id: str
    source_path: str
    file_name: str | None = None
    mime_type: str | None = None
    file_size: int | None = None
    content_hash: str | None = None
    status: str = "pending"
    chunk_count: int = 0
    parser_version: str | None = None
    embedding_version: str | None = None
    pipeline_version: str = "v1.0"
    file_modified_at: datetime | None = None
    indexed_at: datetime | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    error_message: str | None = None
    retry_count: int = 0
    last_error_at: datetime | None = None

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> "FileState":
        """Create FileState from database row."""
        return cls(**{k: v for k, v in row.items() if k in cls.__dataclass_fields__})


class StateManager:
    """Manages ingestion state in Postgres."""

    def __init__(self, pool: asyncpg.Pool | None = None, database_url: str | None = None):
        """Initialize with connection pool or URL."""
        self._pool = pool
        self._database_url = database_url
        self._owns_pool = pool is None

    async def _get_pool(self) -> asyncpg.Pool:
        """Get or create connection pool."""
        if self._pool is None:
            if self._database_url is None:
                raise ValueError("Either pool or database_url must be provided")
            self._pool = await asyncpg.create_pool(self._database_url)
        return self._pool

    async def close(self) -> None:
        """Close pool if we own it."""
        if self._owns_pool and self._pool is not None:
            await self._pool.close()
            self._pool = None

    async def get_state(self, file_id: str) -> FileState | None:
        """Get current state for a file."""
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM ingestion_state WHERE file_id = $1",
                file_id,
            )
            if row is None:
                return None
            return FileState.from_row(dict(row))

    async def upsert_state(self, state: FileState) -> None:
        """Insert or update file state."""
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO ingestion_state (
                    file_id, source_path, file_name, mime_type, file_size,
                    content_hash, status, chunk_count, parser_version,
                    embedding_version, pipeline_version, file_modified_at,
                    updated_at
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, NOW())
                ON CONFLICT (file_id) DO UPDATE SET
                    source_path = EXCLUDED.source_path,
                    file_name = EXCLUDED.file_name,
                    mime_type = EXCLUDED.mime_type,
                    file_size = EXCLUDED.file_size,
                    content_hash = EXCLUDED.content_hash,
                    status = EXCLUDED.status,
                    chunk_count = EXCLUDED.chunk_count,
                    parser_version = EXCLUDED.parser_version,
                    embedding_version = EXCLUDED.embedding_version,
                    pipeline_version = EXCLUDED.pipeline_version,
                    file_modified_at = EXCLUDED.file_modified_at,
                    updated_at = NOW()
                """,
                state.file_id,
                state.source_path,
                state.file_name,
                state.mime_type,
                state.file_size,
                state.content_hash,
                state.status,
                state.chunk_count,
                state.parser_version,
                state.embedding_version,
                state.pipeline_version,
                state.file_modified_at,
            )

    async def mark_indexed(self, file_id: str, chunk_count: int) -> None:
        """Mark file as successfully indexed."""
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE ingestion_state
                SET status = 'indexed',
                    chunk_count = $2,
                    indexed_at = NOW(),
                    updated_at = NOW(),
                    error_message = NULL
                WHERE file_id = $1
                """,
                file_id,
                chunk_count,
            )

    async def mark_deleted(self, file_id: str) -> None:
        """Mark file as deleted."""
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE ingestion_state
                SET status = 'deleted',
                    updated_at = NOW()
                WHERE file_id = $1
                """,
                file_id,
            )

    async def mark_error(self, file_id: str, error: str) -> None:
        """Mark file as errored, increment retry count."""
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE ingestion_state
                SET status = 'error',
                    error_message = $2,
                    retry_count = retry_count + 1,
                    last_error_at = NOW(),
                    updated_at = NOW()
                WHERE file_id = $1
                """,
                file_id,
                error,
            )

    async def mark_processing(self, file_id: str) -> None:
        """Mark file as currently processing."""
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE ingestion_state
                SET status = 'processing',
                    updated_at = NOW()
                WHERE file_id = $1
                """,
                file_id,
            )

    async def get_all_active_file_ids(self) -> set[str]:
        """Get all file_ids that are not deleted."""
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT file_id FROM ingestion_state WHERE status != 'deleted'"
            )
            return {row["file_id"] for row in rows}

    async def get_pending_files(self, limit: int = 100) -> list[FileState]:
        """Get files pending processing."""
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT * FROM ingestion_state
                WHERE status IN ('pending', 'error')
                AND retry_count < 3
                ORDER BY created_at ASC
                LIMIT $1
                """,
                limit,
            )
            return [FileState.from_row(dict(row)) for row in rows]

    async def get_stats(self) -> dict[str, int]:
        """Get ingestion statistics."""
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT status, COUNT(*) as count
                FROM ingestion_state
                GROUP BY status
                """
            )
            return {row["status"]: row["count"] for row in rows}
```

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/ingestion/test_state_manager.py -v`

Expected: All 5 tests PASS

**Step 5: Commit**

```bash
git add src/ingestion/state_manager.py tests/unit/ingestion/test_state_manager.py
git commit -m "feat(ingestion): add StateManager for Postgres state tracking"
```

---

### Task 3: Create DeadLetterQueue Class

**Files:**
- Create: `src/ingestion/dead_letter.py`
- Create: `tests/unit/ingestion/test_dead_letter.py`

**Step 1: Write failing test**

```python
# tests/unit/ingestion/test_dead_letter.py
"""Tests for dead letter queue."""

import pytest
from unittest.mock import AsyncMock


class TestDeadLetterQueue:
    """Test DLQ operations."""

    @pytest.fixture
    def mock_pool(self):
        """Create mock asyncpg pool."""
        pool = AsyncMock()
        pool.acquire = AsyncMock()
        return pool

    @pytest.mark.asyncio
    async def test_add_to_dlq(self, mock_pool):
        """add() inserts record into DLQ."""
        from src.ingestion.dead_letter import DeadLetterQueue

        mock_conn = AsyncMock()
        mock_conn.execute = AsyncMock()
        mock_pool.acquire.return_value.__aenter__.return_value = mock_conn

        dlq = DeadLetterQueue(pool=mock_pool)
        await dlq.add(
            file_id="abc123",
            source_path="Test/doc.pdf",
            error_type="docling_timeout",
            error_message="Timeout after 120s",
        )

        mock_conn.execute.assert_called_once()
        call_sql = mock_conn.execute.call_args[0][0]
        assert "INSERT INTO dead_letter_queue" in call_sql

    @pytest.mark.asyncio
    async def test_get_unresolved(self, mock_pool):
        """get_unresolved returns items without resolved_at."""
        from src.ingestion.dead_letter import DeadLetterQueue, DLQItem

        mock_conn = AsyncMock()
        mock_conn.fetch = AsyncMock(return_value=[
            {
                "id": 1,
                "file_id": "abc123",
                "source_path": "Test/doc.pdf",
                "error_type": "docling_timeout",
                "error_message": "Timeout",
                "retry_count": 1,
                "max_retries": 3,
                "created_at": None,
                "last_retry_at": None,
                "resolved_at": None,
                "resolved_by": None,
            }
        ])
        mock_pool.acquire.return_value.__aenter__.return_value = mock_conn

        dlq = DeadLetterQueue(pool=mock_pool)
        items = await dlq.get_unresolved(limit=10)

        assert len(items) == 1
        assert items[0].file_id == "abc123"

    @pytest.mark.asyncio
    async def test_mark_resolved(self, mock_pool):
        """mark_resolved updates resolved_at and resolved_by."""
        from src.ingestion.dead_letter import DeadLetterQueue

        mock_conn = AsyncMock()
        mock_conn.execute = AsyncMock()
        mock_pool.acquire.return_value.__aenter__.return_value = mock_conn

        dlq = DeadLetterQueue(pool=mock_pool)
        await dlq.mark_resolved(item_id=1, resolved_by="manual_retry")

        mock_conn.execute.assert_called_once()
        call_sql = mock_conn.execute.call_args[0][0]
        assert "resolved_at = NOW()" in call_sql
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/ingestion/test_dead_letter.py -v 2>&1 | head -20`

Expected: FAIL with ImportError

**Step 3: Implement DeadLetterQueue**

```python
# src/ingestion/dead_letter.py
"""Dead letter queue for failed ingestion items."""

from dataclasses import dataclass
from datetime import datetime
from typing import Any

import asyncpg


@dataclass
class DLQItem:
    """Item in the dead letter queue."""

    id: int
    file_id: str
    source_path: str | None
    error_type: str | None
    error_message: str | None
    retry_count: int
    max_retries: int
    created_at: datetime | None
    last_retry_at: datetime | None
    resolved_at: datetime | None
    resolved_by: str | None

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> "DLQItem":
        """Create from database row."""
        return cls(**{k: v for k, v in row.items() if k in cls.__dataclass_fields__})


class DeadLetterQueue:
    """Manages dead letter queue in Postgres."""

    def __init__(self, pool: asyncpg.Pool | None = None, database_url: str | None = None):
        """Initialize with connection pool or URL."""
        self._pool = pool
        self._database_url = database_url
        self._owns_pool = pool is None

    async def _get_pool(self) -> asyncpg.Pool:
        """Get or create connection pool."""
        if self._pool is None:
            if self._database_url is None:
                raise ValueError("Either pool or database_url must be provided")
            self._pool = await asyncpg.create_pool(self._database_url)
        return self._pool

    async def close(self) -> None:
        """Close pool if we own it."""
        if self._owns_pool and self._pool is not None:
            await self._pool.close()
            self._pool = None

    async def add(
        self,
        file_id: str,
        source_path: str | None = None,
        error_type: str | None = None,
        error_message: str | None = None,
        stack_trace: str | None = None,
        payload: dict | None = None,
    ) -> int:
        """Add item to DLQ. Returns the item ID."""
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO dead_letter_queue (
                    file_id, source_path, error_type, error_message,
                    stack_trace, payload
                ) VALUES ($1, $2, $3, $4, $5, $6)
                RETURNING id
                """,
                file_id,
                source_path,
                error_type,
                error_message,
                stack_trace,
                payload,
            )
            return row["id"]

    async def get_unresolved(
        self,
        limit: int = 100,
        error_type: str | None = None,
    ) -> list[DLQItem]:
        """Get unresolved items from DLQ."""
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            if error_type:
                rows = await conn.fetch(
                    """
                    SELECT * FROM dead_letter_queue
                    WHERE resolved_at IS NULL
                    AND error_type = $1
                    AND retry_count < max_retries
                    ORDER BY created_at ASC
                    LIMIT $2
                    """,
                    error_type,
                    limit,
                )
            else:
                rows = await conn.fetch(
                    """
                    SELECT * FROM dead_letter_queue
                    WHERE resolved_at IS NULL
                    AND retry_count < max_retries
                    ORDER BY created_at ASC
                    LIMIT $1
                    """,
                    limit,
                )
            return [DLQItem.from_row(dict(row)) for row in rows]

    async def mark_resolved(self, item_id: int, resolved_by: str = "auto") -> None:
        """Mark item as resolved."""
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE dead_letter_queue
                SET resolved_at = NOW(),
                    resolved_by = $2
                WHERE id = $1
                """,
                item_id,
                resolved_by,
            )

    async def increment_retry(self, item_id: int, error_message: str | None = None) -> None:
        """Increment retry count for item."""
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE dead_letter_queue
                SET retry_count = retry_count + 1,
                    last_retry_at = NOW(),
                    error_message = COALESCE($2, error_message)
                WHERE id = $1
                """,
                item_id,
                error_message,
            )

    async def get_stats(self) -> dict[str, int]:
        """Get DLQ statistics."""
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT
                    COUNT(*) FILTER (WHERE resolved_at IS NULL) as unresolved,
                    COUNT(*) FILTER (WHERE resolved_at IS NOT NULL) as resolved,
                    COUNT(*) FILTER (WHERE retry_count >= max_retries AND resolved_at IS NULL) as exhausted
                FROM dead_letter_queue
                """
            )
            return dict(row)
```

**Step 4: Run tests**

Run: `uv run pytest tests/unit/ingestion/test_dead_letter.py -v`

Expected: All 3 tests PASS

**Step 5: Commit**

```bash
git add src/ingestion/dead_letter.py tests/unit/ingestion/test_dead_letter.py
git commit -m "feat(ingestion): add DeadLetterQueue for failed items"
```

---

## Phase 2: Orchestrator

### Task 4: Create Orchestrator Class

**Files:**
- Create: `src/ingestion/orchestrator.py`
- Create: `tests/unit/ingestion/test_orchestrator.py`

**Step 1: Write failing test**

```python
# tests/unit/ingestion/test_orchestrator.py
"""Tests for ingestion orchestrator."""

import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, UTC


class TestIngestionOrchestrator:
    """Test orchestrator operations."""

    @pytest.fixture
    def mock_state_manager(self):
        """Mock StateManager."""
        manager = AsyncMock()
        manager.get_all_active_file_ids = AsyncMock(return_value=set())
        manager.get_state = AsyncMock(return_value=None)
        manager.upsert_state = AsyncMock()
        manager.mark_indexed = AsyncMock()
        manager.mark_deleted = AsyncMock()
        manager.mark_error = AsyncMock()
        return manager

    @pytest.fixture
    def mock_file_processor(self):
        """Mock FileProcessor."""
        processor = AsyncMock()
        processor.process = AsyncMock(return_value={"chunk_count": 10, "status": "success"})
        return processor

    @pytest.fixture
    def mock_dlq(self):
        """Mock DeadLetterQueue."""
        dlq = AsyncMock()
        dlq.add = AsyncMock()
        return dlq

    @pytest.mark.asyncio
    async def test_detect_new_file(self, tmp_path, mock_state_manager):
        """New file in sync dir detected as NEW."""
        from src.ingestion.orchestrator import IngestionOrchestrator

        # Create test file
        test_file = tmp_path / "doc.pdf"
        test_file.write_bytes(b"PDF content")

        mock_state_manager.get_all_active_file_ids.return_value = set()

        orchestrator = IngestionOrchestrator(
            sync_dir=tmp_path,
            state_manager=mock_state_manager,
            file_processor=AsyncMock(),
            dlq=AsyncMock(),
        )

        changes = await orchestrator.detect_changes()

        assert len(changes.new_files) == 1
        assert changes.new_files[0].name == "doc.pdf"

    @pytest.mark.asyncio
    async def test_detect_deleted_file(self, tmp_path, mock_state_manager):
        """File in DB but not filesystem detected as DELETED."""
        from src.ingestion.orchestrator import IngestionOrchestrator

        # No files in filesystem
        mock_state_manager.get_all_active_file_ids.return_value = {"abc123"}

        orchestrator = IngestionOrchestrator(
            sync_dir=tmp_path,
            state_manager=mock_state_manager,
            file_processor=AsyncMock(),
            dlq=AsyncMock(),
        )

        changes = await orchestrator.detect_changes()

        assert "abc123" in changes.deleted_file_ids

    @pytest.mark.asyncio
    async def test_detect_modified_file(self, tmp_path, mock_state_manager):
        """Changed content_hash detected as MODIFIED."""
        from src.ingestion.orchestrator import IngestionOrchestrator, compute_file_id
        from src.ingestion.state_manager import FileState

        # Create test file
        test_file = tmp_path / "doc.pdf"
        test_file.write_bytes(b"NEW content")

        file_id = compute_file_id(tmp_path, test_file)
        mock_state_manager.get_all_active_file_ids.return_value = {file_id}
        mock_state_manager.get_state.return_value = FileState(
            file_id=file_id,
            source_path="doc.pdf",
            content_hash="old_hash",
            status="indexed",
        )

        orchestrator = IngestionOrchestrator(
            sync_dir=tmp_path,
            state_manager=mock_state_manager,
            file_processor=AsyncMock(),
            dlq=AsyncMock(),
        )

        changes = await orchestrator.detect_changes()

        assert len(changes.modified_files) == 1
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/ingestion/test_orchestrator.py -v 2>&1 | head -20`

Expected: FAIL with ImportError

**Step 3: Implement Orchestrator**

```python
# src/ingestion/orchestrator.py
"""Main orchestrator for ingestion pipeline."""

import asyncio
import hashlib
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from src.ingestion.state_manager import StateManager, FileState
from src.ingestion.dead_letter import DeadLetterQueue

logger = logging.getLogger(__name__)

SUPPORTED_EXTENSIONS = {".pdf", ".docx", ".xlsx", ".pptx", ".md", ".txt", ".html"}


def compute_file_id(sync_dir: Path, file_path: Path) -> str:
    """Compute stable file_id from relative path."""
    relative = file_path.relative_to(sync_dir)
    return hashlib.sha256(str(relative).encode()).hexdigest()[:16]


def compute_content_hash(file_path: Path) -> str:
    """Compute content hash for change detection."""
    hasher = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            hasher.update(chunk)
    return hasher.hexdigest()[:16]


@dataclass
class FileChanges:
    """Detected file changes."""

    new_files: list[Path] = field(default_factory=list)
    modified_files: list[Path] = field(default_factory=list)
    deleted_file_ids: set[str] = field(default_factory=set)


@dataclass
class IngestionStats:
    """Statistics from ingestion run."""

    files_seen: int = 0
    files_processed: int = 0
    files_failed: int = 0
    files_deleted: int = 0
    chunks_generated: int = 0


class IngestionOrchestrator:
    """Orchestrates the ingestion pipeline."""

    def __init__(
        self,
        sync_dir: Path | str,
        state_manager: StateManager,
        file_processor: "FileProcessor",
        dlq: DeadLetterQueue,
        supported_extensions: set[str] | None = None,
    ):
        """Initialize orchestrator."""
        self.sync_dir = Path(sync_dir)
        self.state_manager = state_manager
        self.file_processor = file_processor
        self.dlq = dlq
        self.supported_extensions = supported_extensions or SUPPORTED_EXTENSIONS

    def _is_supported_file(self, path: Path) -> bool:
        """Check if file type is supported."""
        if path.name.startswith(".") or path.name.startswith("~$"):
            return False
        return path.suffix.lower() in self.supported_extensions

    def _scan_files(self) -> dict[str, Path]:
        """Scan sync directory for supported files."""
        files = {}
        for path in self.sync_dir.rglob("*"):
            if path.is_file() and self._is_supported_file(path):
                file_id = compute_file_id(self.sync_dir, path)
                files[file_id] = path
        return files

    async def detect_changes(self) -> FileChanges:
        """Detect new, modified, and deleted files."""
        changes = FileChanges()

        # Get current files in filesystem
        current_files = self._scan_files()

        # Get known file_ids from database
        known_file_ids = await self.state_manager.get_all_active_file_ids()

        # Detect new and modified files
        for file_id, file_path in current_files.items():
            if file_id not in known_file_ids:
                changes.new_files.append(file_path)
            else:
                # Check if content changed
                state = await self.state_manager.get_state(file_id)
                if state and state.content_hash:
                    current_hash = compute_content_hash(file_path)
                    if current_hash != state.content_hash:
                        changes.modified_files.append(file_path)

        # Detect deleted files
        current_file_ids = set(current_files.keys())
        changes.deleted_file_ids = known_file_ids - current_file_ids

        return changes

    async def process_new_file(self, file_path: Path) -> bool:
        """Process a new file."""
        file_id = compute_file_id(self.sync_dir, file_path)
        relative_path = str(file_path.relative_to(self.sync_dir))

        # Create initial state
        state = FileState(
            file_id=file_id,
            source_path=relative_path,
            file_name=file_path.name,
            mime_type=self._get_mime_type(file_path),
            file_size=file_path.stat().st_size,
            content_hash=compute_content_hash(file_path),
            status="pending",
        )
        await self.state_manager.upsert_state(state)

        return await self._process_file(file_id, file_path)

    async def process_modified_file(self, file_path: Path) -> bool:
        """Process a modified file."""
        file_id = compute_file_id(self.sync_dir, file_path)

        # Delete old chunks first
        await self.file_processor.delete_chunks(file_id)

        # Update state with new hash
        state = await self.state_manager.get_state(file_id)
        if state:
            state.content_hash = compute_content_hash(file_path)
            state.status = "pending"
            await self.state_manager.upsert_state(state)

        return await self._process_file(file_id, file_path)

    async def process_deleted_file(self, file_id: str) -> bool:
        """Process a deleted file."""
        try:
            await self.file_processor.delete_chunks(file_id)
            await self.state_manager.mark_deleted(file_id)
            logger.info(f"Deleted chunks for file_id={file_id}")
            return True
        except Exception as e:
            logger.error(f"Error deleting file_id={file_id}: {e}")
            return False

    async def _process_file(self, file_id: str, file_path: Path) -> bool:
        """Process a single file through the pipeline."""
        try:
            await self.state_manager.mark_processing(file_id)

            result = await self.file_processor.process(file_path, file_id)

            if result["status"] == "success":
                await self.state_manager.mark_indexed(file_id, result["chunk_count"])
                logger.info(f"Indexed {file_path.name}: {result['chunk_count']} chunks")
                return True
            else:
                raise Exception(result.get("error", "Unknown error"))

        except Exception as e:
            logger.error(f"Error processing {file_path}: {e}")
            await self.state_manager.mark_error(file_id, str(e))

            # Check if should go to DLQ
            state = await self.state_manager.get_state(file_id)
            if state and state.retry_count >= 3:
                await self.dlq.add(
                    file_id=file_id,
                    source_path=str(file_path.relative_to(self.sync_dir)),
                    error_type=type(e).__name__,
                    error_message=str(e),
                )
                logger.warning(f"File {file_id} moved to DLQ after 3 retries")

            return False

    def _get_mime_type(self, path: Path) -> str:
        """Get MIME type from file extension."""
        ext = path.suffix.lower()
        mime_map = {
            ".pdf": "application/pdf",
            ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
            ".md": "text/markdown",
            ".txt": "text/plain",
            ".html": "text/html",
        }
        return mime_map.get(ext, "application/octet-stream")

    async def run_once(self) -> IngestionStats:
        """Run single ingestion pass."""
        stats = IngestionStats()

        changes = await self.detect_changes()

        stats.files_seen = len(changes.new_files) + len(changes.modified_files)

        # Process new files
        for file_path in changes.new_files:
            if await self.process_new_file(file_path):
                stats.files_processed += 1
            else:
                stats.files_failed += 1

        # Process modified files
        for file_path in changes.modified_files:
            if await self.process_modified_file(file_path):
                stats.files_processed += 1
            else:
                stats.files_failed += 1

        # Process deleted files
        for file_id in changes.deleted_file_ids:
            if await self.process_deleted_file(file_id):
                stats.files_deleted += 1

        return stats

    async def run_continuous(self, interval: int = 60) -> None:
        """Run continuous ingestion with polling."""
        logger.info(f"Starting continuous ingestion (interval={interval}s)")
        while True:
            try:
                stats = await self.run_once()
                if stats.files_processed or stats.files_deleted:
                    logger.info(
                        f"Processed: {stats.files_processed}, "
                        f"Failed: {stats.files_failed}, "
                        f"Deleted: {stats.files_deleted}"
                    )
            except Exception as e:
                logger.error(f"Error in ingestion loop: {e}")

            await asyncio.sleep(interval)
```

**Step 4: Run tests**

Run: `uv run pytest tests/unit/ingestion/test_orchestrator.py -v`

Expected: All 3 tests PASS

**Step 5: Commit**

```bash
git add src/ingestion/orchestrator.py tests/unit/ingestion/test_orchestrator.py
git commit -m "feat(ingestion): add IngestionOrchestrator with change detection"
```

---

### Task 5: Create FileProcessor Class

**Files:**
- Create: `src/ingestion/file_processor.py`
- Create: `tests/unit/ingestion/test_file_processor.py`

**Step 1: Write failing test**

```python
# tests/unit/ingestion/test_file_processor.py
"""Tests for file processor."""

import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch


class TestFileProcessor:
    """Test FileProcessor operations."""

    @pytest.fixture
    def mock_docling_client(self):
        """Mock DoclingClient."""
        client = AsyncMock()
        client.chunk_file = AsyncMock(return_value=[
            {
                "text": "Chunk 1 content",
                "contextualized_text": "Context: Chunk 1 content",
                "headings": ["Section 1"],
                "meta": {"page": 1, "offset": 0},
            },
            {
                "text": "Chunk 2 content",
                "contextualized_text": "Context: Chunk 2 content",
                "headings": ["Section 1", "Subsection"],
                "meta": {"page": 1, "offset": 100},
            },
        ])
        return client

    @pytest.fixture
    def mock_indexer(self):
        """Mock GDriveIndexer."""
        indexer = AsyncMock()
        indexer.index_chunks = AsyncMock(return_value={"indexed": 2, "replaced": 0})
        indexer.delete_by_file_id = AsyncMock()
        return indexer

    @pytest.mark.asyncio
    async def test_process_returns_chunk_count(
        self, tmp_path, mock_docling_client, mock_indexer
    ):
        """process() returns chunk count on success."""
        from src.ingestion.file_processor import FileProcessor

        test_file = tmp_path / "doc.pdf"
        test_file.write_bytes(b"PDF content")

        processor = FileProcessor(
            docling_client=mock_docling_client,
            indexer=mock_indexer,
            sync_dir=tmp_path,
        )

        result = await processor.process(test_file, "file123")

        assert result["status"] == "success"
        assert result["chunk_count"] == 2
        mock_indexer.index_chunks.assert_called_once()

    @pytest.mark.asyncio
    async def test_delete_chunks_calls_indexer(self, mock_indexer):
        """delete_chunks() calls indexer delete method."""
        from src.ingestion.file_processor import FileProcessor

        processor = FileProcessor(
            docling_client=AsyncMock(),
            indexer=mock_indexer,
            sync_dir=Path("/tmp"),
        )

        await processor.delete_chunks("file123")

        mock_indexer.delete_by_file_id.assert_called_once_with("file123")
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/ingestion/test_file_processor.py -v 2>&1 | head -20`

Expected: FAIL with ImportError

**Step 3: Implement FileProcessor**

```python
# src/ingestion/file_processor.py
"""File processor for ingestion pipeline."""

import hashlib
import logging
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from src.ingestion.docling_client import DoclingClient, DoclingConfig

logger = logging.getLogger(__name__)

# UUID namespace for point IDs
POINT_ID_NAMESPACE = uuid.UUID("6ba7b810-9dad-11d1-80b4-00c04fd430c8")


def compute_point_id(file_id: str, chunk_location: str) -> str:
    """Compute deterministic point ID for idempotency."""
    return str(uuid.uuid5(POINT_ID_NAMESPACE, f"{file_id}:{chunk_location}"))


def compute_chunk_location(meta: dict) -> str:
    """Compute stable chunk location from docling metadata."""
    page = meta.get("page", 0)
    offset = meta.get("offset", 0)
    return f"page:{page}:offset:{offset}"


@dataclass
class ProcessedChunk:
    """A processed chunk ready for indexing."""

    point_id: str
    file_id: str
    source_path: str
    file_name: str
    chunk_index: int
    chunk_count: int
    chunk_location: str
    text: str
    headings: list[str]
    content_hash: str
    page_number: int | None
    docling_meta: dict


class FileProcessor:
    """Processes files through docling and prepares for indexing."""

    def __init__(
        self,
        docling_client: Any,  # DoclingClient or mock
        indexer: Any,  # GDriveIndexer or mock
        sync_dir: Path,
        pipeline_version: str = "v1.0",
        embedding_version: str = "voyage-4-large",
    ):
        """Initialize processor."""
        self.docling_client = docling_client
        self.indexer = indexer
        self.sync_dir = Path(sync_dir)
        self.pipeline_version = pipeline_version
        self.embedding_version = embedding_version

    async def process(self, file_path: Path, file_id: str) -> dict[str, Any]:
        """Process a file and index chunks."""
        try:
            # Get chunks from docling
            raw_chunks = await self.docling_client.chunk_file(file_path)

            if not raw_chunks:
                return {
                    "status": "success",
                    "chunk_count": 0,
                    "message": "No chunks extracted",
                }

            # Transform to processed chunks
            relative_path = str(file_path.relative_to(self.sync_dir))
            processed_chunks = []

            for idx, raw_chunk in enumerate(raw_chunks):
                chunk_location = compute_chunk_location(raw_chunk.get("meta", {}))
                text = raw_chunk.get("contextualized_text") or raw_chunk.get("text", "")

                chunk = ProcessedChunk(
                    point_id=compute_point_id(file_id, chunk_location),
                    file_id=file_id,
                    source_path=relative_path,
                    file_name=file_path.name,
                    chunk_index=idx,
                    chunk_count=len(raw_chunks),
                    chunk_location=chunk_location,
                    text=text,
                    headings=raw_chunk.get("headings", []),
                    content_hash=hashlib.sha256(text.encode()).hexdigest()[:16],
                    page_number=raw_chunk.get("meta", {}).get("page"),
                    docling_meta=raw_chunk.get("meta", {}),
                )
                processed_chunks.append(chunk)

            # Index chunks
            result = await self.indexer.index_chunks(
                chunks=processed_chunks,
                file_id=file_id,
            )

            return {
                "status": "success",
                "chunk_count": len(processed_chunks),
                "indexed": result.get("indexed", 0),
                "replaced": result.get("replaced", 0),
            }

        except Exception as e:
            logger.error(f"Error processing {file_path}: {e}")
            return {
                "status": "error",
                "chunk_count": 0,
                "error": str(e),
            }

    async def delete_chunks(self, file_id: str) -> None:
        """Delete all chunks for a file."""
        await self.indexer.delete_by_file_id(file_id)
```

**Step 4: Run tests**

Run: `uv run pytest tests/unit/ingestion/test_file_processor.py -v`

Expected: All 2 tests PASS

**Step 5: Commit**

```bash
git add src/ingestion/file_processor.py tests/unit/ingestion/test_file_processor.py
git commit -m "feat(ingestion): add FileProcessor for docling + indexing"
```

---

### Task 6: Update __init__.py Exports

**Files:**
- Modify: `src/ingestion/__init__.py`

**Step 1: Update exports**

```python
# src/ingestion/__init__.py
"""Ingestion module for document processing pipeline."""

from src.ingestion.state_manager import StateManager, FileState
from src.ingestion.dead_letter import DeadLetterQueue, DLQItem
from src.ingestion.orchestrator import (
    IngestionOrchestrator,
    FileChanges,
    IngestionStats,
    compute_file_id,
    compute_content_hash,
)
from src.ingestion.file_processor import FileProcessor, ProcessedChunk

__all__ = [
    # State management
    "StateManager",
    "FileState",
    # Dead letter queue
    "DeadLetterQueue",
    "DLQItem",
    # Orchestrator
    "IngestionOrchestrator",
    "FileChanges",
    "IngestionStats",
    "compute_file_id",
    "compute_content_hash",
    # File processor
    "FileProcessor",
    "ProcessedChunk",
]
```

**Step 2: Verify imports work**

Run: `uv run python -c "from src.ingestion import StateManager, IngestionOrchestrator, FileProcessor; print('OK')"`

Expected: `OK`

**Step 3: Commit**

```bash
git add src/ingestion/__init__.py
git commit -m "feat(ingestion): export new orchestrator components"
```

---

## Phase 3: CLI & Makefile

### Task 7: Create CLI Entry Point

**Files:**
- Create: `src/ingestion/cli.py`

**Step 1: Create CLI**

```python
# src/ingestion/cli.py
"""CLI entry point for ingestion pipeline."""

import argparse
import asyncio
import logging
import os
import sys
from pathlib import Path

from dotenv import load_dotenv


def setup_logging(verbose: bool = False) -> None:
    """Configure logging."""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


async def run_ingestion(args: argparse.Namespace) -> int:
    """Run ingestion pipeline."""
    import asyncpg

    from src.ingestion.orchestrator import IngestionOrchestrator
    from src.ingestion.state_manager import StateManager
    from src.ingestion.dead_letter import DeadLetterQueue
    from src.ingestion.file_processor import FileProcessor
    from src.ingestion.docling_client import DoclingClient, DoclingConfig
    from src.ingestion.gdrive_indexer import GDriveIndexer

    # Get config from env
    sync_dir = Path(os.getenv("GDRIVE_SYNC_DIR", os.path.expanduser("~/drive-sync")))
    database_url = os.getenv(
        "INGESTION_DATABASE_URL",
        "postgresql://postgres:postgres@localhost:5432/postgres"
    )
    qdrant_url = os.getenv("QDRANT_URL", "http://localhost:6333")
    docling_url = os.getenv("DOCLING_URL", "http://localhost:5001")
    voyage_api_key = os.getenv("VOYAGE_API_KEY")

    if not voyage_api_key:
        logging.error("VOYAGE_API_KEY is required")
        return 1

    if not sync_dir.exists():
        logging.error(f"Sync directory does not exist: {sync_dir}")
        return 1

    # Create connection pool
    pool = await asyncpg.create_pool(database_url)

    try:
        # Initialize components
        state_manager = StateManager(pool=pool)
        dlq = DeadLetterQueue(pool=pool)

        docling_config = DoclingConfig(base_url=docling_url)
        async with DoclingClient(docling_config) as docling_client:
            indexer = GDriveIndexer(
                qdrant_url=qdrant_url,
                voyage_api_key=voyage_api_key,
            )

            file_processor = FileProcessor(
                docling_client=docling_client,
                indexer=indexer,
                sync_dir=sync_dir,
            )

            orchestrator = IngestionOrchestrator(
                sync_dir=sync_dir,
                state_manager=state_manager,
                file_processor=file_processor,
                dlq=dlq,
            )

            if args.watch:
                logging.info(f"Starting continuous ingestion (interval={args.interval}s)")
                await orchestrator.run_continuous(interval=args.interval)
            else:
                logging.info("Running single ingestion pass")
                stats = await orchestrator.run_once()
                logging.info(
                    f"Complete: processed={stats.files_processed}, "
                    f"failed={stats.files_failed}, deleted={stats.files_deleted}"
                )

    finally:
        await pool.close()

    return 0


async def show_status(args: argparse.Namespace) -> int:
    """Show ingestion status."""
    import asyncpg

    from src.ingestion.state_manager import StateManager
    from src.ingestion.dead_letter import DeadLetterQueue

    database_url = os.getenv(
        "INGESTION_DATABASE_URL",
        "postgresql://postgres:postgres@localhost:5432/postgres"
    )

    pool = await asyncpg.create_pool(database_url)

    try:
        state_manager = StateManager(pool=pool)
        dlq = DeadLetterQueue(pool=pool)

        state_stats = await state_manager.get_stats()
        dlq_stats = await dlq.get_stats()

        print("\n=== Ingestion Status ===")
        print("\nFile States:")
        for status, count in sorted(state_stats.items()):
            print(f"  {status}: {count}")

        print("\nDead Letter Queue:")
        print(f"  Unresolved: {dlq_stats.get('unresolved', 0)}")
        print(f"  Resolved: {dlq_stats.get('resolved', 0)}")
        print(f"  Exhausted (max retries): {dlq_stats.get('exhausted', 0)}")

    finally:
        await pool.close()

    return 0


def main() -> int:
    """Main entry point."""
    load_dotenv()

    parser = argparse.ArgumentParser(description="Ingestion Pipeline CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # Run command
    run_parser = subparsers.add_parser("run", help="Run ingestion")
    run_parser.add_argument("--watch", action="store_true", help="Continuous mode")
    run_parser.add_argument("--interval", type=int, default=60, help="Poll interval (seconds)")
    run_parser.add_argument("-v", "--verbose", action="store_true", help="Verbose logging")

    # Status command
    status_parser = subparsers.add_parser("status", help="Show status")
    status_parser.add_argument("-v", "--verbose", action="store_true", help="Verbose output")

    args = parser.parse_args()
    setup_logging(args.verbose)

    if args.command == "run":
        return asyncio.run(run_ingestion(args))
    elif args.command == "status":
        return asyncio.run(show_status(args))

    return 1


if __name__ == "__main__":
    sys.exit(main())
```

**Step 2: Test CLI help**

Run: `uv run python -m src.ingestion.cli --help`

Expected: Help output with `run` and `status` commands

**Step 3: Commit**

```bash
git add src/ingestion/cli.py
git commit -m "feat(ingestion): add CLI entry point"
```

---

### Task 8: Update Makefile

**Files:**
- Modify: `Makefile`

**Step 1: Add new targets (append to existing ingestion section)**

Find the ingestion section in Makefile and update it:

```makefile
# Unified Ingestion Pipeline
.PHONY: ingest-db-setup ingest-run-unified ingest-watch-unified ingest-status-unified

ingest-db-setup: ## Setup Postgres tables for ingestion state
	docker cp docker/postgres/init/03-ingestion.sql dev-postgres:/tmp/
	docker exec dev-postgres psql -U postgres -f /tmp/03-ingestion.sql

ingest-run-unified: ## Run unified ingestion once (with Postgres state)
	set -a && source .env && set +a && uv run python -m src.ingestion.cli run

ingest-watch-unified: ## Run unified ingestion continuously
	set -a && source .env && set +a && uv run python -m src.ingestion.cli run --watch --interval 60

ingest-status-unified: ## Show unified ingestion status
	set -a && source .env && set +a && uv run python -m src.ingestion.cli status
```

**Step 2: Verify targets work**

Run: `make help | grep ingest`

Expected: Shows all ingest-* targets

**Step 3: Commit**

```bash
git add Makefile
git commit -m "feat(ingestion): add Makefile targets for unified pipeline"
```

---

## Phase 4: Integration

### Task 9: Update GDriveIndexer for New Interface

**Files:**
- Modify: `src/ingestion/gdrive_indexer.py`

**Step 1: Add delete_by_file_id method if missing**

Check if method exists:

Run: `grep -n "delete_by_file_id\|delete.*file_id" src/ingestion/gdrive_indexer.py`

If not found, add this method to GDriveIndexer class:

```python
async def delete_by_file_id(self, file_id: str) -> int:
    """Delete all points for a file_id.

    Returns number of points deleted.
    """
    # Get current count
    result = self.qdrant_client.scroll(
        collection_name=self.collection_name,
        scroll_filter=models.Filter(
            must=[
                models.FieldCondition(
                    key="file_id",
                    match=models.MatchValue(value=file_id),
                )
            ]
        ),
        limit=1,
        with_payload=False,
        with_vectors=False,
    )

    # Delete
    self.qdrant_client.delete(
        collection_name=self.collection_name,
        points_selector=models.FilterSelector(
            filter=models.Filter(
                must=[
                    models.FieldCondition(
                        key="file_id",
                        match=models.MatchValue(value=file_id),
                    )
                ]
            )
        ),
    )

    return len(result[0]) if result else 0
```

**Step 2: Verify method exists**

Run: `uv run python -c "from src.ingestion.gdrive_indexer import GDriveIndexer; print(hasattr(GDriveIndexer, 'delete_by_file_id'))"`

Expected: `True`

**Step 3: Commit if changed**

```bash
git add src/ingestion/gdrive_indexer.py
git commit -m "feat(ingestion): add delete_by_file_id to GDriveIndexer"
```

---

### Task 10: Integration Test

**Files:**
- Create: `tests/integration/test_unified_ingestion.py`

**Step 1: Create integration test**

```python
# tests/integration/test_unified_ingestion.py
"""Integration tests for unified ingestion pipeline."""

import os
import pytest
from pathlib import Path

pytestmark = pytest.mark.skipif(
    not os.getenv("RUN_INTEGRATION_TESTS"),
    reason="Integration tests disabled (set RUN_INTEGRATION_TESTS=1)"
)


@pytest.fixture
def test_sync_dir(tmp_path):
    """Create test sync directory with sample files."""
    sync_dir = tmp_path / "drive-sync"
    sync_dir.mkdir()

    # Create test markdown file
    test_md = sync_dir / "test_doc.md"
    test_md.write_text("# Test Document\n\nThis is test content for ingestion.")

    return sync_dir


@pytest.mark.asyncio
async def test_new_file_indexed(test_sync_dir):
    """New file in sync dir gets indexed to Qdrant."""
    import asyncpg
    from qdrant_client import QdrantClient

    from src.ingestion.orchestrator import IngestionOrchestrator, compute_file_id
    from src.ingestion.state_manager import StateManager
    from src.ingestion.dead_letter import DeadLetterQueue
    from src.ingestion.file_processor import FileProcessor
    from src.ingestion.docling_client import DoclingClient, DoclingConfig
    from src.ingestion.gdrive_indexer import GDriveIndexer

    # Setup
    database_url = os.getenv("INGESTION_DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/postgres")
    qdrant_url = os.getenv("QDRANT_URL", "http://localhost:6333")
    docling_url = os.getenv("DOCLING_URL", "http://localhost:5001")
    voyage_api_key = os.getenv("VOYAGE_API_KEY")

    pool = await asyncpg.create_pool(database_url)

    try:
        state_manager = StateManager(pool=pool)
        dlq = DeadLetterQueue(pool=pool)

        docling_config = DoclingConfig(base_url=docling_url)
        async with DoclingClient(docling_config) as docling_client:
            indexer = GDriveIndexer(
                qdrant_url=qdrant_url,
                voyage_api_key=voyage_api_key,
                collection_name="test_unified_ingestion",
            )

            file_processor = FileProcessor(
                docling_client=docling_client,
                indexer=indexer,
                sync_dir=test_sync_dir,
            )

            orchestrator = IngestionOrchestrator(
                sync_dir=test_sync_dir,
                state_manager=state_manager,
                file_processor=file_processor,
                dlq=dlq,
            )

            # Run ingestion
            stats = await orchestrator.run_once()

            # Verify
            assert stats.files_processed == 1
            assert stats.files_failed == 0

            # Check Qdrant
            qdrant = QdrantClient(url=qdrant_url)
            test_file = test_sync_dir / "test_doc.md"
            file_id = compute_file_id(test_sync_dir, test_file)

            results = qdrant.scroll(
                collection_name="test_unified_ingestion",
                scroll_filter={"must": [{"key": "file_id", "match": {"value": file_id}}]},
                limit=10,
            )

            assert len(results[0]) > 0, "Chunks should be in Qdrant"

            # Cleanup
            await indexer.delete_by_file_id(file_id)
            await state_manager.mark_deleted(file_id)

    finally:
        await pool.close()
```

**Step 2: Run integration test (if services available)**

Run: `RUN_INTEGRATION_TESTS=1 uv run pytest tests/integration/test_unified_ingestion.py -v 2>&1 | tail -20`

Expected: PASS (or SKIP if services not available)

**Step 3: Commit**

```bash
git add tests/integration/test_unified_ingestion.py
git commit -m "test(ingestion): add integration test for unified pipeline"
```

---

## Phase 5: Documentation

### Task 11: Update docs/INGESTION.md

**Files:**
- Modify: `docs/INGESTION.md`

**Step 1: Add unified pipeline section**

Append to the end of `docs/INGESTION.md`:

```markdown

## Unified Pipeline (Production)

### Architecture

```
Google Drive → rclone sync (5min) → /data/drive-sync
                                          ↓
                              CocoIndex Orchestrator (60s poll)
                                          ↓
                              Postgres State Tracking
                                          ↓
                    ┌─────────────────────┼─────────────────────┐
                    ▼                     ▼                     ▼
               [NEW FILE]          [MODIFIED]            [DELETED]
                    │                     │                     │
                    ▼                     ▼                     ▼
              docling-serve         DELETE+ADD           DELETE chunks
                    │
                    ▼
            Voyage + BM42 embeddings
                    │
                    ▼
              Qdrant upsert
```

### Quick Start

```bash
# 1. Setup Postgres tables
make ingest-db-setup

# 2. Run once
make ingest-run-unified

# 3. Or run continuously
make ingest-watch-unified

# 4. Check status
make ingest-status-unified
```

### State Tracking

Files are tracked in Postgres with states:
- `pending` - New/modified, awaiting processing
- `processing` - Currently being processed
- `indexed` - Successfully indexed
- `error` - Failed (will retry up to 3 times)
- `deleted` - File removed from Drive

### Dead Letter Queue

Failed files (after 3 retries) go to DLQ. To view/retry:

```bash
# View DLQ
psql -U postgres -c "SELECT * FROM dead_letter_queue WHERE resolved_at IS NULL;"

# Manual retry via CLI (future)
# uv run python -m src.ingestion.cli dlq --retry --limit 10
```

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `GDRIVE_SYNC_DIR` | `~/drive-sync` | rclone sync directory |
| `INGESTION_DATABASE_URL` | `postgresql://...` | Postgres connection |
| `QDRANT_URL` | `http://localhost:6333` | Qdrant server |
| `DOCLING_URL` | `http://localhost:5001` | Docling server |
| `VOYAGE_API_KEY` | - | Required for embeddings |
```

**Step 2: Commit**

```bash
git add docs/INGESTION.md
git commit -m "docs(ingestion): add unified pipeline documentation"
```

---

## Summary

### Files Created
- `docker/postgres/init/03-ingestion.sql`
- `src/ingestion/state_manager.py`
- `src/ingestion/dead_letter.py`
- `src/ingestion/orchestrator.py`
- `src/ingestion/file_processor.py`
- `src/ingestion/cli.py`
- `tests/unit/ingestion/test_state_manager.py`
- `tests/unit/ingestion/test_dead_letter.py`
- `tests/unit/ingestion/test_orchestrator.py`
- `tests/unit/ingestion/test_file_processor.py`
- `tests/integration/test_unified_ingestion.py`

### Files Modified
- `src/ingestion/__init__.py`
- `src/ingestion/gdrive_indexer.py`
- `Makefile`
- `docs/INGESTION.md`

### Verification

```bash
# Run all new tests
uv run pytest tests/unit/ingestion/test_state_manager.py \
              tests/unit/ingestion/test_dead_letter.py \
              tests/unit/ingestion/test_orchestrator.py \
              tests/unit/ingestion/test_file_processor.py -v

# Setup and test
make ingest-db-setup
make ingest-status-unified
```
