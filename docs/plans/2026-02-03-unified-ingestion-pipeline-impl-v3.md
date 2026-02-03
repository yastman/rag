# Unified Ingestion Pipeline Implementation Plan (v3 - Reuse Existing Components)

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Unify ingestion pipeline, reusing existing services (VoyageService, CacheService, DoclingClient) and fixing payload contract for bot compatibility.

**Architecture:**
- **Parsing:** `DoclingClient` (unchanged)
- **Chunking:** `DocumentChunker` or `DoclingClient.chunk_file()`
- **Embedding:** `VoyageService` from `telegram_bot/services/voyage.py` (has batching + retries)
- **Caching:** `CacheService` from `telegram_bot/services/cache.py` (has RedisVL)
- **State:** Existing Postgres schema `02-cocoindex.sql` (already has tables)
- **Indexing:** Refactored `gdrive_indexer.py` with correct payload contract

**Tech Stack:** Python 3.12, asyncpg, Qdrant, Voyage AI (voyage-4-large), FastEmbed BM42, Docling, Redis (RedisVL)

**Key Fix:** Payload contract `{page_content, metadata}` для совместимости с ботом (small-to-big, цитирование).

---

## Critical Payload Contract Fix

**Current (broken):**
```python
# gdrive_indexer.py writes flat payload:
{
    "file_id": "abc123",
    "text": "content...",
    "source_path": "docs/file.pdf"
}
```

**Required (for bot compatibility):**
```python
# Retrieval expects this format:
{
    "page_content": "content...",
    "metadata": {
        "file_id": "abc123",
        "source": "docs/file.pdf",  # For citations
        "parent_id": "...",          # For small-to-big
        "headings": [...],
        ...
    }
}
```

---

## Phase 1: Fix Payload Contract

### Task 1: Update GDriveIndexer Payload Format

**Files:**
- Modify: `src/ingestion/gdrive_indexer.py`
- Create: `tests/unit/ingestion/test_gdrive_indexer_payload.py`

**Step 1: Write failing test for payload format**

```python
# tests/unit/ingestion/test_gdrive_indexer_payload.py
"""Tests for gdrive indexer payload contract."""

import pytest
from unittest.mock import MagicMock, patch


class TestGDriveIndexerPayload:
    """Test payload format for bot compatibility."""

    def test_payload_has_page_content_field(self):
        """Payload must have page_content for retrieval."""
        from src.ingestion.gdrive_indexer import GDriveIndexer

        indexer = GDriveIndexer.__new__(GDriveIndexer)

        chunk = MagicMock()
        chunk.text = "Test content"
        chunk.chunk_id = 0
        chunk.document_name = "test.pdf"
        chunk.section = "Introduction"
        chunk.page_range = (1, 2)
        chunk.extra_metadata = {"custom": "value"}

        file_metadata = {
            "file_id": "abc123",
            "source_path": "docs/test.pdf",
            "mime_type": "application/pdf",
            "modified_time": "2026-02-03T12:00:00Z",
        }

        payload = indexer._build_payload(chunk, file_metadata)

        # Required fields for retrieval
        assert "page_content" in payload
        assert payload["page_content"] == "Test content"

    def test_payload_has_metadata_dict(self):
        """Payload must have metadata dict for small-to-big and citations."""
        from src.ingestion.gdrive_indexer import GDriveIndexer

        indexer = GDriveIndexer.__new__(GDriveIndexer)

        chunk = MagicMock()
        chunk.text = "Test content"
        chunk.chunk_id = 0
        chunk.document_name = "test.pdf"
        chunk.section = None
        chunk.page_range = None
        chunk.extra_metadata = None

        file_metadata = {
            "file_id": "abc123",
            "source_path": "docs/test.pdf",
        }

        payload = indexer._build_payload(chunk, file_metadata)

        # metadata must be a dict
        assert "metadata" in payload
        assert isinstance(payload["metadata"], dict)

        # Required metadata fields for bot
        assert payload["metadata"]["source"] == "docs/test.pdf"
        assert payload["metadata"]["file_id"] == "abc123"

    def test_payload_metadata_has_citation_fields(self):
        """Metadata must have fields needed for citations."""
        from src.ingestion.gdrive_indexer import GDriveIndexer

        indexer = GDriveIndexer.__new__(GDriveIndexer)

        chunk = MagicMock()
        chunk.text = "Test content"
        chunk.chunk_id = 5
        chunk.document_name = "report.pdf"
        chunk.section = "Chapter 2"
        chunk.page_range = (10, 12)
        chunk.extra_metadata = {"headings": ["Title", "Chapter 2"]}

        file_metadata = {
            "file_id": "def456",
            "source_path": "reports/report.pdf",
            "mime_type": "application/pdf",
        }

        payload = indexer._build_payload(chunk, file_metadata)

        meta = payload["metadata"]
        assert meta["source"] == "reports/report.pdf"
        assert meta["file_name"] == "report.pdf"
        assert meta["section"] == "Chapter 2"
        assert meta["page_range"] == [10, 12]
        assert meta["chunk_id"] == 5
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/ingestion/test_gdrive_indexer_payload.py -v 2>&1 | head -30`

Expected: FAIL with AttributeError (no _build_payload method)

**Step 3: Implement _build_payload in gdrive_indexer.py**

Find the section where payload is built (around line 138) and refactor:

```python
# In src/ingestion/gdrive_indexer.py

def _build_payload(self, chunk: Chunk, file_metadata: dict[str, Any]) -> dict[str, Any]:
    """Build Qdrant payload with bot-compatible format.

    Payload contract:
    - page_content: str - The actual chunk text for retrieval
    - metadata: dict - Structured metadata for citations and small-to-big

    This format is required by:
    - telegram_bot/services/qdrant.py (retrieval)
    - telegram_bot/services/small_to_big.py (parent lookup)
    - Bot citation formatting
    """
    # Build metadata dict (nested, for bot compatibility)
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

        # File metadata
        "mime_type": file_metadata.get("mime_type"),
        "modified_time": file_metadata.get("modified_time"),
        "content_hash": file_metadata.get("content_hash"),
    }

    # Merge extra_metadata if present
    if chunk.extra_metadata:
        # Headings go into metadata
        if "headings" in chunk.extra_metadata:
            metadata["headings"] = chunk.extra_metadata["headings"]
        # Other extra metadata
        for key, value in chunk.extra_metadata.items():
            if key not in metadata:
                metadata[key] = value

    # Build final payload (flat structure with nested metadata)
    payload = {
        "page_content": chunk.text,  # Required by retrieval
        "metadata": metadata,         # Required by small-to-big and citations

        # Also keep flat file_id for delete operations
        "file_id": file_metadata.get("file_id"),
    }

    return payload
```

**Step 4: Update index_file_chunks to use _build_payload**

Find the method that builds points (around line 130-160) and update:

```python
# In index_file_chunks method, replace payload building with:

for i, chunk in enumerate(chunks):
    chunk_location = f"chunk_{chunk.chunk_id}"
    point_id = self._generate_point_id(file_id, chunk_location)

    payload = self._build_payload(chunk, file_metadata)

    points.append(PointStruct(
        id=point_id,
        vector={
            "dense": dense_embeddings[i],
            "bm42": sparse_embeddings[i].as_object(),
        },
        payload=payload,
    ))
```

**Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/unit/ingestion/test_gdrive_indexer_payload.py -v`

Expected: All 3 tests PASS

**Step 6: Commit**

```bash
git add src/ingestion/gdrive_indexer.py tests/unit/ingestion/test_gdrive_indexer_payload.py
git commit -m "fix(ingestion): update gdrive_indexer payload for bot compatibility

- Add page_content field (required by retrieval)
- Add nested metadata dict (required by small-to-big and citations)
- Keep flat file_id for delete operations"
```

---

### Task 2: Update QdrantService to Handle New Payload

**Files:**
- Verify: `telegram_bot/services/qdrant.py` (should already work with new format)

**Step 1: Verify retrieval reads page_content correctly**

Run: `grep -n "page_content\|metadata" telegram_bot/services/qdrant.py | head -20`

Expected: Should show code that accesses `payload["page_content"]` or `payload.get("page_content")`

**Step 2: If needed, update result mapping**

Check the `_format_results` or similar method. The new payload should be compatible.

**Step 3: Test with existing collection (if available)**

Run: `uv run python -c "
from telegram_bot.services.qdrant import QdrantService
import asyncio

async def test():
    service = QdrantService()
    # Test that service can read page_content from results
    print('QdrantService initialized')

asyncio.run(test())
"`

Expected: No errors

---

## Phase 2: Create Unified State Manager

### Task 3: Create StateManager Using Existing Schema

**Files:**
- Create: `src/ingestion/unified/state_manager.py`
- Reference: `docker/postgres/init/02-cocoindex.sql`

**Step 1: Read existing schema**

Run: `cat docker/postgres/init/02-cocoindex.sql`

Expected: Shows `ingestion_state` and `ingestion_dead_letter` tables

**Step 2: Create StateManager that uses existing schema**

```python
# src/ingestion/unified/state_manager.py
"""State manager using existing Postgres schema (02-cocoindex.sql).

Tables used:
- ingestion_state: Track file processing status
- ingestion_dead_letter: Store failed items for retry

This reuses the schema created by Milestone J.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Any

import asyncpg


@dataclass
class FileState:
    """State of a file in ingestion pipeline.

    Maps to ingestion_state table from 02-cocoindex.sql.
    """
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
        """Create from database row."""
        return cls(**{k: v for k, v in row.items() if k in cls.__dataclass_fields__})


class UnifiedStateManager:
    """Manages ingestion state using existing Postgres tables.

    Uses tables from docker/postgres/init/02-cocoindex.sql:
    - cocoindex.ingestion_state
    - cocoindex.ingestion_dead_letter
    """

    def __init__(
        self,
        pool: asyncpg.Pool | None = None,
        database_url: str | None = None,
        schema: str = "cocoindex",
    ):
        self._pool = pool
        self._database_url = database_url
        self._owns_pool = pool is None
        self._schema = schema
        self._state_table = f"{schema}.ingestion_state"
        self._dlq_table = f"{schema}.ingestion_dead_letter"

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
        """Get current state for a file."""
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                f"SELECT * FROM {self._state_table} WHERE file_id = $1",
                file_id,
            )
            return FileState.from_row(dict(row)) if row else None

    async def upsert_state(self, state: FileState) -> None:
        """Insert or update file state."""
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                f"""
                INSERT INTO {self._state_table} (
                    file_id, drive_id, folder_id, file_name, mime_type,
                    modified_time, content_hash, parser_version, chunker_version,
                    embedding_model, chunk_count, status, error_message, retry_count
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14)
                ON CONFLICT (file_id) DO UPDATE SET
                    drive_id = EXCLUDED.drive_id,
                    folder_id = EXCLUDED.folder_id,
                    file_name = EXCLUDED.file_name,
                    mime_type = EXCLUDED.mime_type,
                    modified_time = EXCLUDED.modified_time,
                    content_hash = EXCLUDED.content_hash,
                    parser_version = EXCLUDED.parser_version,
                    chunker_version = EXCLUDED.chunker_version,
                    embedding_model = EXCLUDED.embedding_model,
                    chunk_count = EXCLUDED.chunk_count,
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
        """Mark file as successfully indexed."""
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                f"""
                UPDATE {self._state_table}
                SET status = 'indexed',
                    chunk_count = $2,
                    indexed_at = NOW(),
                    error_message = NULL
                WHERE file_id = $1
                """,
                file_id, chunk_count,
            )

    async def mark_error(self, file_id: str, error: str) -> None:
        """Mark file as errored."""
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                f"""
                UPDATE {self._state_table}
                SET status = 'error',
                    error_message = $2,
                    retry_count = retry_count + 1
                WHERE file_id = $1
                """,
                file_id, error,
            )

    async def mark_deleted(self, file_id: str) -> None:
        """Mark file as deleted (soft delete)."""
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                f"""
                UPDATE {self._state_table}
                SET status = 'deleted'
                WHERE file_id = $1
                """,
                file_id,
            )

    async def get_all_indexed_file_ids(self) -> set[str]:
        """Get all file_ids that are indexed (not deleted/error)."""
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                f"SELECT file_id FROM {self._state_table} WHERE status = 'indexed'"
            )
            return {row["file_id"] for row in rows}

    async def get_pending_files(self, limit: int = 100) -> list[FileState]:
        """Get files pending processing (including retryable errors)."""
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                f"""
                SELECT * FROM {self._state_table}
                WHERE status IN ('pending', 'error')
                AND retry_count < 3
                ORDER BY modified_time ASC NULLS LAST
                LIMIT $1
                """,
                limit,
            )
            return [FileState.from_row(dict(row)) for row in rows]

    async def add_to_dlq(
        self,
        file_id: str,
        error_type: str,
        error_message: str,
        payload: dict | None = None,
    ) -> int:
        """Add failed item to dead letter queue."""
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                f"""
                INSERT INTO {self._dlq_table} (file_id, error_type, error_message, payload)
                VALUES ($1, $2, $3, $4)
                RETURNING id
                """,
                file_id, error_type, error_message, payload,
            )
            return row["id"]

    async def get_stats(self) -> dict[str, int]:
        """Get ingestion statistics."""
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                f"""
                SELECT status, COUNT(*) as count
                FROM {self._state_table}
                GROUP BY status
                """
            )
            return {row["status"]: row["count"] for row in rows}
```

**Step 3: Create __init__.py for unified module**

```python
# src/ingestion/unified/__init__.py
"""Unified ingestion pipeline components."""

from src.ingestion.unified.state_manager import UnifiedStateManager, FileState

__all__ = ["UnifiedStateManager", "FileState"]
```

**Step 4: Run import test**

Run: `uv run python -c "from src.ingestion.unified import UnifiedStateManager; print('OK')"`

Expected: `OK`

**Step 5: Commit**

```bash
git add src/ingestion/unified/
git commit -m "feat(ingestion): add UnifiedStateManager using existing Postgres schema"
```

---

## Phase 3: Create Unified Pipeline Orchestrator

### Task 4: Create UnifiedIngestionPipeline

**Files:**
- Create: `src/ingestion/unified/pipeline.py`
- Create: `tests/unit/ingestion/test_unified_pipeline.py`

**Step 1: Write failing test**

```python
# tests/unit/ingestion/test_unified_pipeline.py
"""Tests for unified ingestion pipeline."""

import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch


class TestUnifiedIngestionPipeline:
    """Test unified pipeline orchestration."""

    @pytest.fixture
    def mock_state_manager(self):
        manager = AsyncMock()
        manager.get_all_indexed_file_ids = AsyncMock(return_value=set())
        manager.get_state = AsyncMock(return_value=None)
        manager.upsert_state = AsyncMock()
        manager.mark_indexed = AsyncMock()
        manager.mark_error = AsyncMock()
        return manager

    @pytest.fixture
    def mock_voyage_service(self):
        service = MagicMock()
        service.embed_documents = MagicMock(return_value=[[0.1] * 1024])
        return service

    @pytest.fixture
    def mock_indexer(self):
        indexer = AsyncMock()
        indexer.index_file_chunks = AsyncMock(return_value=MagicMock(
            total=1, indexed=1, failed=0
        ))
        indexer.delete_file_points = AsyncMock()
        return indexer

    @pytest.mark.asyncio
    async def test_process_file_creates_state(
        self, tmp_path, mock_state_manager, mock_voyage_service, mock_indexer
    ):
        """process_file creates initial state in Postgres."""
        from src.ingestion.unified.pipeline import UnifiedIngestionPipeline

        test_file = tmp_path / "doc.md"
        test_file.write_text("# Test\n\nContent here.")

        pipeline = UnifiedIngestionPipeline(
            state_manager=mock_state_manager,
            voyage_service=mock_voyage_service,
            indexer=mock_indexer,
            sync_dir=tmp_path,
        )

        with patch.object(pipeline, '_parse_and_chunk', return_value=[MagicMock(text="chunk")]):
            await pipeline.process_file(test_file)

        # State should be created/updated
        mock_state_manager.upsert_state.assert_called()

    @pytest.mark.asyncio
    async def test_process_file_marks_indexed_on_success(
        self, tmp_path, mock_state_manager, mock_voyage_service, mock_indexer
    ):
        """Successful processing marks file as indexed."""
        from src.ingestion.unified.pipeline import UnifiedIngestionPipeline

        test_file = tmp_path / "doc.md"
        test_file.write_text("# Test")

        pipeline = UnifiedIngestionPipeline(
            state_manager=mock_state_manager,
            voyage_service=mock_voyage_service,
            indexer=mock_indexer,
            sync_dir=tmp_path,
        )

        with patch.object(pipeline, '_parse_and_chunk', return_value=[MagicMock(text="chunk")]):
            await pipeline.process_file(test_file)

        mock_state_manager.mark_indexed.assert_called()
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/ingestion/test_unified_pipeline.py -v 2>&1 | head -20`

Expected: FAIL with ImportError

**Step 3: Implement UnifiedIngestionPipeline**

```python
# src/ingestion/unified/pipeline.py
"""Unified ingestion pipeline that reuses existing services.

Components reused:
- VoyageService (telegram_bot/services/voyage.py) - embeddings
- CacheService (telegram_bot/services/cache.py) - sparse caching (optional)
- DoclingClient (src/ingestion/docling_client.py) - parsing
- GDriveIndexer (src/ingestion/gdrive_indexer.py) - Qdrant indexing
- UnifiedStateManager - Postgres state tracking

This orchestrator ties everything together with proper error handling
and state management.
"""

import hashlib
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from src.ingestion.unified.state_manager import UnifiedStateManager, FileState
from src.ingestion.chunker import Chunk

logger = logging.getLogger(__name__)

SUPPORTED_EXTENSIONS = {
    ".pdf", ".docx", ".xlsx", ".pptx",
    ".md", ".txt", ".html", ".csv",
}


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
class ProcessingStats:
    """Statistics from processing run."""
    files_seen: int = 0
    files_processed: int = 0
    files_skipped: int = 0
    files_failed: int = 0
    files_deleted: int = 0
    chunks_indexed: int = 0


@dataclass
class FileChange:
    """Detected file change."""
    path: Path
    file_id: str
    change_type: str  # "new", "modified", "deleted"


class UnifiedIngestionPipeline:
    """Unified pipeline orchestrator.

    Reuses existing services:
    - VoyageService for embeddings (has batching + retries)
    - GDriveIndexer for Qdrant operations
    - DoclingClient for parsing
    - Postgres for state tracking
    """

    def __init__(
        self,
        state_manager: UnifiedStateManager,
        voyage_service: Any,  ***REMOVED***Service from telegram_bot
        indexer: Any,  # GDriveIndexer
        sync_dir: Path | str,
        docling_client: Any | None = None,  # Optional DoclingClient
        collection_name: str = "gdrive_documents_binary",
        parser_version: str = "docling-2.1",
        chunker_version: str = "hybrid-1.0",
    ):
        self.state_manager = state_manager
        self.voyage_service = voyage_service
        self.indexer = indexer
        self.sync_dir = Path(sync_dir)
        self.docling_client = docling_client
        self.collection_name = collection_name
        self.parser_version = parser_version
        self.chunker_version = chunker_version

    def _is_supported_file(self, path: Path) -> bool:
        """Check if file type is supported."""
        if path.name.startswith(".") or path.name.startswith("~$"):
            return False
        return path.suffix.lower() in SUPPORTED_EXTENSIONS

    def _scan_files(self) -> dict[str, Path]:
        """Scan sync directory for supported files."""
        files = {}
        for path in self.sync_dir.rglob("*"):
            if path.is_file() and self._is_supported_file(path):
                file_id = compute_file_id(self.sync_dir, path)
                files[file_id] = path
        return files

    async def detect_changes(self) -> list[FileChange]:
        """Detect new, modified, and deleted files."""
        changes = []

        # Get current files
        current_files = self._scan_files()
        current_ids = set(current_files.keys())

        # Get indexed files from Postgres
        indexed_ids = await self.state_manager.get_all_indexed_file_ids()

        # Detect new and modified
        for file_id, file_path in current_files.items():
            if file_id not in indexed_ids:
                changes.append(FileChange(file_path, file_id, "new"))
            else:
                # Check content hash
                state = await self.state_manager.get_state(file_id)
                if state and state.content_hash:
                    current_hash = compute_content_hash(file_path)
                    if current_hash != state.content_hash:
                        changes.append(FileChange(file_path, file_id, "modified"))

        # Detect deleted
        for file_id in indexed_ids - current_ids:
            changes.append(FileChange(Path(""), file_id, "deleted"))

        return changes

    async def _parse_and_chunk(self, file_path: Path) -> list[Chunk]:
        """Parse file and return chunks."""
        if self.docling_client:
            # Use DoclingClient for rich parsing
            docling_chunks = await self.docling_client.chunk_file(file_path)
            return self.docling_client.to_ingestion_chunks(
                docling_chunks,
                source=str(file_path.relative_to(self.sync_dir)),
                source_type="gdrive",
            )
        else:
            # Fallback to simple text extraction
            from src.ingestion.chunker import DocumentChunker, ChunkingStrategy

            text = file_path.read_text(encoding="utf-8", errors="ignore")
            chunker = DocumentChunker(strategy=ChunkingStrategy.FIXED_SIZE)
            return chunker.chunk_text(text, file_path.name)

    async def process_file(self, file_path: Path) -> bool:
        """Process a single file through the pipeline."""
        file_id = compute_file_id(self.sync_dir, file_path)
        relative_path = str(file_path.relative_to(self.sync_dir))

        try:
            # Create initial state
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

            # Parse and chunk
            chunks = await self._parse_and_chunk(file_path)

            if not chunks:
                logger.warning(f"No chunks from {file_path.name}")
                await self.state_manager.mark_indexed(file_id, 0)
                return True

            # Build file metadata for payload
            file_metadata = {
                "file_id": file_id,
                "source_path": relative_path,
                "mime_type": state.mime_type,
                "modified_time": file_path.stat().st_mtime,
                "content_hash": state.content_hash,
            }

            # Index (uses VoyageService internally for embeddings)
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
            return False

    async def process_deletion(self, file_id: str) -> bool:
        """Handle file deletion."""
        try:
            await self.indexer.delete_file_points(file_id, self.collection_name)
            await self.state_manager.mark_deleted(file_id)
            logger.info(f"Deleted file_id={file_id}")
            return True
        except Exception as e:
            logger.error(f"Error deleting {file_id}: {e}")
            return False

    async def run_once(self) -> ProcessingStats:
        """Run single processing pass."""
        stats = ProcessingStats()

        changes = await self.detect_changes()
        stats.files_seen = len(changes)

        for change in changes:
            if change.change_type == "deleted":
                if await self.process_deletion(change.file_id):
                    stats.files_deleted += 1
                else:
                    stats.files_failed += 1
            else:
                if await self.process_file(change.path):
                    stats.files_processed += 1
                else:
                    stats.files_failed += 1

        return stats

    def _get_mime_type(self, path: Path) -> str:
        """Get MIME type from extension."""
        ext = path.suffix.lower()
        return {
            ".pdf": "application/pdf",
            ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            ".md": "text/markdown",
            ".txt": "text/plain",
            ".html": "text/html",
            ".csv": "text/csv",
        }.get(ext, "application/octet-stream")
```

**Step 4: Run tests**

Run: `uv run pytest tests/unit/ingestion/test_unified_pipeline.py -v`

Expected: All 2 tests PASS

**Step 5: Commit**

```bash
git add src/ingestion/unified/pipeline.py tests/unit/ingestion/test_unified_pipeline.py
git commit -m "feat(ingestion): add UnifiedIngestionPipeline orchestrator"
```

---

## Phase 4: CLI & Integration

### Task 5: Create CLI Entry Point

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
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )


async def run_ingestion(args):
    """Run unified ingestion."""
    import asyncpg

    from src.ingestion.unified.state_manager import UnifiedStateManager
    from src.ingestion.unified.pipeline import UnifiedIngestionPipeline
    from src.ingestion.gdrive_indexer import GDriveIndexer
    from src.ingestion.docling_client import DoclingClient, DoclingConfig

    # Reuse VoyageService from bot
    sys.path.insert(0, str(Path(__file__).parents[3]))
    from telegram_bot.services.voyage import VoyageService

    # Config from env
    sync_dir = Path(os.getenv("GDRIVE_SYNC_DIR", os.path.expanduser("~/drive-sync")))
    database_url = os.getenv("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/cocoindex")
    collection_name = os.getenv("GDRIVE_COLLECTION_NAME", "gdrive_documents_binary")

    if not sync_dir.exists():
        logging.error(f"Sync directory not found: {sync_dir}")
        return 1

    # Initialize services
    pool = await asyncpg.create_pool(database_url)

    try:
        state_manager = UnifiedStateManager(pool=pool, schema="cocoindex")
        voyage_service = VoyageService()

        indexer = GDriveIndexer(
            qdrant_url=os.getenv("QDRANT_URL", "http://localhost:6333"),
            voyage_api_key=os.getenv("VOYAGE_API_KEY"),
        )

        docling_config = DoclingConfig(base_url=os.getenv("DOCLING_URL", "http://localhost:5001"))

        async with DoclingClient(docling_config) as docling_client:
            pipeline = UnifiedIngestionPipeline(
                state_manager=state_manager,
                voyage_service=voyage_service,
                indexer=indexer,
                sync_dir=sync_dir,
                docling_client=docling_client,
                collection_name=collection_name,
            )

            if args.watch:
                logging.info(f"Watching {sync_dir} (interval={args.interval}s)")
                while True:
                    stats = await pipeline.run_once()
                    if stats.files_processed or stats.files_deleted:
                        logging.info(f"Processed: {stats.files_processed}, Deleted: {stats.files_deleted}")
                    await asyncio.sleep(args.interval)
            else:
                stats = await pipeline.run_once()
                logging.info(f"Done: {stats.files_processed} processed, {stats.files_failed} failed")

    finally:
        await pool.close()

    return 0


async def show_status(args):
    """Show ingestion status."""
    import asyncpg
    from src.ingestion.unified.state_manager import UnifiedStateManager

    database_url = os.getenv("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/cocoindex")

    pool = await asyncpg.create_pool(database_url)
    try:
        manager = UnifiedStateManager(pool=pool, schema="cocoindex")
        stats = await manager.get_stats()

        print("\n=== Ingestion Status ===")
        for status, count in sorted(stats.items()):
            print(f"  {status}: {count}")
    finally:
        await pool.close()


def main():
    load_dotenv()

    parser = argparse.ArgumentParser(description="Unified Ingestion Pipeline")
    subparsers = parser.add_subparsers(dest="command", required=True)

    run_parser = subparsers.add_parser("run", help="Run ingestion")
    run_parser.add_argument("--watch", action="store_true", help="Continuous mode")
    run_parser.add_argument("--interval", type=int, default=60, help="Poll interval")
    run_parser.add_argument("-v", "--verbose", action="store_true")

    status_parser = subparsers.add_parser("status", help="Show status")
    status_parser.add_argument("-v", "--verbose", action="store_true")

    args = parser.parse_args()
    setup_logging(getattr(args, "verbose", False))

    if args.command == "run":
        return asyncio.run(run_ingestion(args))
    elif args.command == "status":
        return asyncio.run(show_status(args))


if __name__ == "__main__":
    sys.exit(main())
```

**Step 2: Test CLI help**

Run: `uv run python -m src.ingestion.unified.cli --help`

Expected: Help with `run` and `status` commands

**Step 3: Commit**

```bash
git add src/ingestion/unified/cli.py
git commit -m "feat(ingestion): add unified pipeline CLI"
```

---

### Task 6: Update Makefile

**Files:**
- Modify: `Makefile`

**Step 1: Add unified targets**

```makefile
# Unified Ingestion Pipeline (v3)
.PHONY: ingest-unified ingest-unified-watch ingest-unified-status

ingest-unified: ## Run unified ingestion once
	set -a && source .env && set +a && uv run python -m src.ingestion.unified.cli run

ingest-unified-watch: ## Run unified ingestion continuously
	set -a && source .env && set +a && uv run python -m src.ingestion.unified.cli run --watch

ingest-unified-status: ## Show unified ingestion status
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

## Phase 5: Integration Test

### Task 7: End-to-End Test

**Files:**
- Create: `tests/integration/test_unified_e2e.py`

**Step 1: Create E2E test**

```python
# tests/integration/test_unified_e2e.py
"""End-to-end test for unified ingestion pipeline."""

import os
import pytest
from pathlib import Path

pytestmark = pytest.mark.skipif(
    not os.getenv("RUN_INTEGRATION_TESTS"),
    reason="Set RUN_INTEGRATION_TESTS=1 to run"
)


@pytest.mark.asyncio
async def test_unified_pipeline_indexes_file(tmp_path):
    """File goes through pipeline and appears in Qdrant with correct payload."""
    import asyncpg
    from qdrant_client import QdrantClient

    from src.ingestion.unified.state_manager import UnifiedStateManager
    from src.ingestion.unified.pipeline import UnifiedIngestionPipeline, compute_file_id
    from src.ingestion.gdrive_indexer import GDriveIndexer

    # Create test file
    test_file = tmp_path / "test_doc.md"
    test_file.write_text("# Test Document\n\nThis is test content for unified pipeline.")

    # Setup
    database_url = os.getenv("DATABASE_URL")
    qdrant_url = os.getenv("QDRANT_URL", "http://localhost:6333")
    collection_name = "test_unified_e2e"

    pool = await asyncpg.create_pool(database_url)

    try:
        state_manager = UnifiedStateManager(pool=pool, schema="cocoindex")
        indexer = GDriveIndexer(
            qdrant_url=qdrant_url,
            voyage_api_key=os.getenv("VOYAGE_API_KEY"),
        )

        pipeline = UnifiedIngestionPipeline(
            state_manager=state_manager,
            voyage_service=None,  # Indexer has its own
            indexer=indexer,
            sync_dir=tmp_path,
            collection_name=collection_name,
        )

        # Run
        stats = await pipeline.run_once()

        # Verify stats
        assert stats.files_processed == 1

        # Verify Qdrant payload format
        qdrant = QdrantClient(url=qdrant_url)
        file_id = compute_file_id(tmp_path, test_file)

        results, _ = qdrant.scroll(
            collection_name=collection_name,
            scroll_filter={"must": [{"key": "file_id", "match": {"value": file_id}}]},
            limit=10,
            with_payload=True,
        )

        assert len(results) > 0
        payload = results[0].payload

        # Check payload contract
        assert "page_content" in payload, "Missing page_content"
        assert "metadata" in payload, "Missing metadata dict"
        assert payload["metadata"]["file_id"] == file_id

        # Cleanup
        await indexer.delete_file_points(file_id, collection_name)

    finally:
        await pool.close()
```

**Step 2: Run integration test**

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
- `src/ingestion/unified/__init__.py`
- `src/ingestion/unified/state_manager.py`
- `src/ingestion/unified/pipeline.py`
- `src/ingestion/unified/cli.py`
- `tests/unit/ingestion/test_gdrive_indexer_payload.py`
- `tests/unit/ingestion/test_unified_pipeline.py`
- `tests/integration/test_unified_e2e.py`

### Files Modified
- `src/ingestion/gdrive_indexer.py` - Fixed payload contract
- `Makefile` - Added unified targets

### Components Reused (not duplicated)
| Component | Source | Usage |
|-----------|--------|-------|
| VoyageService | `telegram_bot/services/voyage.py` | Embeddings |
| CacheService | `telegram_bot/services/cache.py` | Available for sparse caching |
| DoclingClient | `src/ingestion/docling_client.py` | Parsing |
| GDriveIndexer | `src/ingestion/gdrive_indexer.py` | Qdrant indexing |
| Postgres schema | `docker/postgres/init/02-cocoindex.sql` | State tracking |

### Payload Contract Fix

```python
# Before (broken):
{"text": "...", "file_id": "..."}

# After (bot-compatible):
{
    "page_content": "...",
    "metadata": {"file_id": "...", "source": "...", ...},
    "file_id": "..."  # kept for delete operations
}
```

### Verification

```bash
# Run tests
uv run pytest tests/unit/ingestion/test_gdrive_indexer_payload.py -v
uv run pytest tests/unit/ingestion/test_unified_pipeline.py -v

# Check status
make ingest-unified-status

# Run once
make ingest-unified
```
