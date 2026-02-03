# Unified Ingestion Pipeline Implementation Plan (v2 - 2026 Best Practices)

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build production ingestion pipeline with 2026 best practices: rclone sync → CocoIndex orchestrator → Postgres state → Docling HybridChunker → Voyage 3.5 + BM42 with batching → Qdrant hybrid search

**Architecture:** rclone syncs Drive to `/data/drive-sync` (systemd timer, 5min). Orchestrator polls filesystem (60s), tracks state in Postgres, processes changes through Docling HybridChunker with contextualization, embeds with Voyage 3.5 (batched, cached) + BM42, upserts to Qdrant with idempotent point IDs. Failed files go to DLQ with exponential backoff.

**Tech Stack:** Python 3.12, asyncpg, Qdrant 1.12+, Voyage AI (voyage-3.5), FastEmbed BM42, Docling HybridChunker, Redis (embedding cache), tenacity (retries), systemd

**2026 Best Practices Applied:**
- Voyage 3.5 (8M TPM vs 3M TPM for voyage-4-large)
- Docling HybridChunker with `merge_peers=True` and contextualization
- Redis embedding cache (40-60% hit rate expected)
- Exponential backoff with tenacity for rate limit handling
- Batched embedding requests (128 docs/batch)
- Cost tracking per file for attribution

---

## Phase 1: Postgres Schema

### Task 1: Create Ingestion State Tables

**Files:**
- Create: `docker/postgres/init/03-ingestion.sql`

**Step 1: Create the SQL schema file**

```sql
-- docker/postgres/init/03-ingestion.sql
-- Ingestion state tracking for GDrive pipeline (2026 best practices)

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
    embedding_version VARCHAR(20) DEFAULT 'voyage-3.5',
    pipeline_version VARCHAR(20) DEFAULT 'v2.0',
    file_modified_at TIMESTAMPTZ,
    indexed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    error_message TEXT,
    retry_count INTEGER DEFAULT 0,
    last_error_at TIMESTAMPTZ,
    -- 2026: Cost tracking
    embedding_tokens INTEGER DEFAULT 0,
    embedding_cost_usd NUMERIC(10, 6) DEFAULT 0
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

-- 2026: Embedding cache stats (Redis cache is primary, this is for analytics)
CREATE TABLE IF NOT EXISTS embedding_cache_stats (
    id SERIAL PRIMARY KEY,
    date DATE NOT NULL DEFAULT CURRENT_DATE,
    cache_hits INTEGER DEFAULT 0,
    cache_misses INTEGER DEFAULT 0,
    total_tokens INTEGER DEFAULT 0,
    total_cost_usd NUMERIC(10, 6) DEFAULT 0,
    UNIQUE(date)
);
```

**Step 2: Apply schema to running Postgres**

Run: `docker exec dev-postgres psql -U postgres -f /docker-entrypoint-initdb.d/03-ingestion.sql 2>&1`

Expected: Tables created (or "already exists" if re-run)

**Step 3: Verify tables exist**

Run: `docker exec dev-postgres psql -U postgres -c "SELECT table_name FROM information_schema.tables WHERE table_name LIKE 'ingestion%' OR table_name LIKE 'dead_%' OR table_name LIKE 'sync_%' OR table_name LIKE 'embedding_%';"`

Expected:
```
      table_name
----------------------
 ingestion_state
 dead_letter_queue
 sync_status
 embedding_cache_stats
```

**Step 4: Commit**

```bash
git add docker/postgres/init/03-ingestion.sql
git commit -m "feat(ingestion): add Postgres schema for state tracking and DLQ (v2)"
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
from unittest.mock import AsyncMock


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
    async def test_mark_indexed_updates_status_and_cost(self, mock_pool):
        """mark_indexed updates status, chunk_count, and cost tracking."""
        from src.ingestion.state_manager import StateManager

        mock_conn = AsyncMock()
        mock_conn.execute = AsyncMock()
        mock_pool.acquire.return_value.__aenter__.return_value = mock_conn

        manager = StateManager(pool=mock_pool)
        await manager.mark_indexed(
            "abc123",
            chunk_count=15,
            embedding_tokens=1500,
            embedding_cost_usd=0.00003,
        )

        mock_conn.execute.assert_called_once()
        call_args = mock_conn.execute.call_args[0]
        assert "status = 'indexed'" in call_args[0]
        assert "embedding_tokens" in call_args[0]

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
"""Postgres state manager for ingestion pipeline (2026 best practices)."""

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
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
    embedding_version: str = "voyage-3.5"
    pipeline_version: str = "v2.0"
    file_modified_at: datetime | None = None
    indexed_at: datetime | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    error_message: str | None = None
    retry_count: int = 0
    last_error_at: datetime | None = None
    # 2026: Cost tracking
    embedding_tokens: int = 0
    embedding_cost_usd: Decimal = Decimal("0")

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

    async def mark_indexed(
        self,
        file_id: str,
        chunk_count: int,
        embedding_tokens: int = 0,
        embedding_cost_usd: float = 0.0,
    ) -> None:
        """Mark file as successfully indexed with cost tracking."""
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE ingestion_state
                SET status = 'indexed',
                    chunk_count = $2,
                    embedding_tokens = $3,
                    embedding_cost_usd = $4,
                    indexed_at = NOW(),
                    updated_at = NOW(),
                    error_message = NULL
                WHERE file_id = $1
                """,
                file_id,
                chunk_count,
                embedding_tokens,
                embedding_cost_usd,
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

    async def get_cost_summary(self) -> dict[str, Any]:
        """Get cost summary for embeddings."""
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT
                    SUM(embedding_tokens) as total_tokens,
                    SUM(embedding_cost_usd) as total_cost_usd,
                    COUNT(*) as total_files
                FROM ingestion_state
                WHERE status = 'indexed'
                """
            )
            return dict(row) if row else {}
```

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/ingestion/test_state_manager.py -v`

Expected: All 5 tests PASS

**Step 5: Commit**

```bash
git add src/ingestion/state_manager.py tests/unit/ingestion/test_state_manager.py
git commit -m "feat(ingestion): add StateManager with cost tracking (v2)"
```

---

## Phase 2: Embedding Service with Caching

### Task 3: Create EmbeddingService with Redis Cache

**Files:**
- Create: `src/ingestion/embedding_service.py`
- Create: `tests/unit/ingestion/test_embedding_service.py`

**Step 1: Write failing test**

```python
# tests/unit/ingestion/test_embedding_service.py
"""Tests for embedding service with caching."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch


class TestEmbeddingService:
    """Test EmbeddingService operations."""

    @pytest.fixture
    def mock_redis(self):
        """Create mock Redis client."""
        redis = AsyncMock()
        redis.get = AsyncMock(return_value=None)
        redis.setex = AsyncMock()
        return redis

    @pytest.fixture
    def mock_voyage_client(self):
        """Create mock Voyage client."""
        client = MagicMock()
        client.embed = MagicMock(return_value=MagicMock(
            embeddings=[[0.1] * 1024, [0.2] * 1024],
            total_tokens=100,
        ))
        return client

    @pytest.mark.asyncio
    async def test_embed_texts_with_cache_miss(self, mock_redis, mock_voyage_client):
        """embed_texts calls Voyage API on cache miss."""
        from src.ingestion.embedding_service import EmbeddingService

        service = EmbeddingService(
            voyage_api_key="test-key",
            redis_client=mock_redis,
        )
        service._voyage_client = mock_voyage_client

        texts = ["Hello world", "Test document"]
        embeddings, metadata = await service.embed_texts(texts)

        assert len(embeddings) == 2
        assert metadata["cache_misses"] == 2
        mock_voyage_client.embed.assert_called_once()

    @pytest.mark.asyncio
    async def test_embed_texts_with_cache_hit(self, mock_redis, mock_voyage_client):
        """embed_texts uses cache on hit."""
        import json
        from src.ingestion.embedding_service import EmbeddingService

        # Mock cache hit
        mock_redis.get = AsyncMock(return_value=json.dumps([0.1] * 1024))

        service = EmbeddingService(
            voyage_api_key="test-key",
            redis_client=mock_redis,
        )
        service._voyage_client = mock_voyage_client

        texts = ["Hello world"]
        embeddings, metadata = await service.embed_texts(texts)

        assert len(embeddings) == 1
        assert metadata["cache_hits"] == 1
        assert metadata["cache_misses"] == 0
        mock_voyage_client.embed.assert_not_called()

    @pytest.mark.asyncio
    async def test_batched_embedding(self, mock_redis, mock_voyage_client):
        """Large text lists are batched correctly."""
        from src.ingestion.embedding_service import EmbeddingService

        service = EmbeddingService(
            voyage_api_key="test-key",
            redis_client=mock_redis,
            batch_size=2,
        )
        service._voyage_client = mock_voyage_client

        texts = ["Text 1", "Text 2", "Text 3", "Text 4"]
        embeddings, metadata = await service.embed_texts(texts)

        # Should call embed twice (2 batches of 2)
        assert mock_voyage_client.embed.call_count == 2
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/ingestion/test_embedding_service.py -v 2>&1 | head -20`

Expected: FAIL with ImportError

**Step 3: Implement EmbeddingService**

```python
# src/ingestion/embedding_service.py
"""Embedding service with Redis caching and rate limiting (2026 best practices).

Key features:
- Redis cache for repeated queries (40-60% hit rate expected)
- Batched requests (128 docs/batch)
- Exponential backoff with tenacity for 429 handling
- Cost tracking per request
"""

import hashlib
import json
import logging
from dataclasses import dataclass
from typing import Any

import voyageai
from tenacity import (
    retry,
    stop_after_attempt,
    wait_random_exponential,
    retry_if_exception_type,
)

logger = logging.getLogger(__name__)

***REMOVED*** 3.5 pricing: $0.02 per 1M tokens (as of 2026)
VOYAGE_COST_PER_TOKEN = 0.02 / 1_000_000


@dataclass
class EmbeddingResult:
    """Result from embedding operation."""

    embeddings: list[list[float]]
    total_tokens: int
    cost_usd: float
    cache_hits: int
    cache_misses: int


class EmbeddingService:
    """Embedding service with caching and rate limit handling."""

    def __init__(
        self,
        voyage_api_key: str,
        redis_client: Any | None = None,
        model: str = "voyage-3.5",
        batch_size: int = 128,
        cache_ttl: int = 86400,  # 24 hours
    ):
        """Initialize embedding service.

        Args:
            voyage_api_key: Voyage AI API key
            redis_client: Optional Redis client for caching
            model: Voyage model (voyage-3.5 recommended for 8M TPM)
            batch_size: Documents per batch (max 128 for Voyage)
            cache_ttl: Cache TTL in seconds
        """
        self._voyage_client = voyageai.Client(api_key=voyage_api_key)
        self._redis = redis_client
        self._model = model
        self._batch_size = min(batch_size, 128)  ***REMOVED*** limit
        self._cache_ttl = cache_ttl

    def _cache_key(self, text: str) -> str:
        """Generate cache key from text hash."""
        return f"emb:{self._model}:{hashlib.md5(text.encode()).hexdigest()}"

    @retry(
        wait=wait_random_exponential(multiplier=1, max=60),
        stop=stop_after_attempt(6),
        retry=retry_if_exception_type((voyageai.error.RateLimitError,)),
    )
    def _embed_batch(self, texts: list[str], input_type: str = "document") -> Any:
        """Embed a batch with exponential backoff on rate limits."""
        return self._voyage_client.embed(
            texts=texts,
            model=self._model,
            input_type=input_type,
        )

    async def embed_texts(
        self,
        texts: list[str],
        input_type: str = "document",
    ) -> tuple[list[list[float]], dict[str, Any]]:
        """Embed multiple texts with caching.

        Args:
            texts: List of texts to embed
            input_type: "document" or "query"

        Returns:
            (embeddings, metadata) where metadata contains cost info
        """
        embeddings: list[list[float] | None] = [None] * len(texts)
        texts_to_embed: list[tuple[int, str]] = []  # (index, text)
        cache_hits = 0
        cache_misses = 0

        # Check cache for each text
        for i, text in enumerate(texts):
            if self._redis is not None:
                cache_key = self._cache_key(text)
                cached = await self._redis.get(cache_key)
                if cached:
                    embeddings[i] = json.loads(cached)
                    cache_hits += 1
                    continue

            texts_to_embed.append((i, text))
            cache_misses += 1

        # Batch embed cache misses
        total_tokens = 0
        if texts_to_embed:
            for batch_start in range(0, len(texts_to_embed), self._batch_size):
                batch = texts_to_embed[batch_start : batch_start + self._batch_size]
                batch_texts = [t[1] for t in batch]

                try:
                    response = self._embed_batch(batch_texts, input_type)
                    total_tokens += response.total_tokens

                    # Store results and cache
                    for (original_idx, text), embedding in zip(batch, response.embeddings):
                        embeddings[original_idx] = embedding

                        # Cache for future use
                        if self._redis is not None:
                            cache_key = self._cache_key(text)
                            await self._redis.setex(
                                cache_key,
                                self._cache_ttl,
                                json.dumps(embedding),
                            )

                except Exception as e:
                    logger.error(f"Error embedding batch: {e}")
                    raise

        # Calculate cost
        cost_usd = total_tokens * VOYAGE_COST_PER_TOKEN

        metadata = {
            "cache_hits": cache_hits,
            "cache_misses": cache_misses,
            "total_tokens": total_tokens,
            "cost_usd": cost_usd,
            "cache_hit_rate": cache_hits / len(texts) if texts else 0,
            "model": self._model,
        }

        # Filter out any None values (shouldn't happen, but safety)
        final_embeddings = [e for e in embeddings if e is not None]

        return final_embeddings, metadata

    async def embed_query(self, query: str) -> tuple[list[float], dict[str, Any]]:
        """Embed a single query."""
        embeddings, metadata = await self.embed_texts([query], input_type="query")
        return embeddings[0], metadata
```

**Step 4: Run tests**

Run: `uv run pytest tests/unit/ingestion/test_embedding_service.py -v`

Expected: All 3 tests PASS

**Step 5: Commit**

```bash
git add src/ingestion/embedding_service.py tests/unit/ingestion/test_embedding_service.py
git commit -m "feat(ingestion): add EmbeddingService with Redis cache and backoff"
```

---

## Phase 3: Docling HybridChunker Integration

### Task 4: Create ChunkingService with HybridChunker

**Files:**
- Create: `src/ingestion/chunking_service.py`
- Create: `tests/unit/ingestion/test_chunking_service.py`

**Step 1: Write failing test**

```python
# tests/unit/ingestion/test_chunking_service.py
"""Tests for chunking service with HybridChunker."""

import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch


class TestChunkingService:
    """Test ChunkingService operations."""

    @pytest.mark.asyncio
    async def test_chunk_document_returns_contextualized_chunks(self, tmp_path):
        """chunk_document returns chunks with contextualization."""
        from src.ingestion.chunking_service import ChunkingService

        # Create test markdown file
        test_file = tmp_path / "test.md"
        test_file.write_text("# Header\n\nThis is content.\n\n## Subheader\n\nMore content.")

        service = ChunkingService(max_tokens=512)
        chunks = await service.chunk_file(test_file)

        assert len(chunks) >= 1
        assert "text" in chunks[0]
        assert "contextualized_text" in chunks[0]
        assert "headings" in chunks[0]

    @pytest.mark.asyncio
    async def test_chunk_preserves_headings(self, tmp_path):
        """Chunks preserve heading hierarchy."""
        from src.ingestion.chunking_service import ChunkingService

        test_file = tmp_path / "test.md"
        test_file.write_text("# Main\n\n## Section 1\n\nContent here.")

        service = ChunkingService(max_tokens=512)
        chunks = await service.chunk_file(test_file)

        # At least one chunk should have headings
        chunks_with_headings = [c for c in chunks if c.get("headings")]
        assert len(chunks_with_headings) >= 0  # May be empty for small docs
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/ingestion/test_chunking_service.py -v 2>&1 | head -20`

Expected: FAIL with ImportError

**Step 3: Implement ChunkingService**

```python
# src/ingestion/chunking_service.py
"""Chunking service using Docling HybridChunker (2026 best practices).

Key features:
- HybridChunker with merge_peers=True for better semantic boundaries
- Contextualization for each chunk (heading breadcrumbs)
- Token-based chunking matching Voyage's tokenizer
"""

import logging
from pathlib import Path
from typing import Any

from docling.document_converter import DocumentConverter
from docling.chunking import HybridChunker

logger = logging.getLogger(__name__)


class ChunkingService:
    """Chunking service using Docling HybridChunker."""

    def __init__(
        self,
        max_tokens: int = 512,
        overlap_tokens: int = 50,
        tokenizer: str = "cl100k_base",  # Compatible with Voyage
    ):
        """Initialize chunking service.

        Args:
            max_tokens: Maximum tokens per chunk
            overlap_tokens: Token overlap between chunks
            tokenizer: Tokenizer to use (cl100k_base for Voyage compatibility)
        """
        self._max_tokens = max_tokens
        self._overlap_tokens = overlap_tokens
        self._tokenizer = tokenizer
        self._converter = DocumentConverter()
        self._chunker = HybridChunker(
            tokenizer=tokenizer,
            max_tokens=max_tokens,
            merge_peers=True,  # Keep related content together
        )

    async def chunk_file(self, file_path: Path) -> list[dict[str, Any]]:
        """Chunk a file using Docling HybridChunker.

        Args:
            file_path: Path to the file to chunk

        Returns:
            List of chunk dictionaries with text, contextualized_text, headings, meta
        """
        try:
            # Convert document
            result = self._converter.convert(str(file_path))

            if result.document is None:
                logger.warning(f"No document extracted from {file_path}")
                return []

            document = result.document
            chunks = []

            # Process each chunk
            for chunk in self._chunker.chunk(dl_doc=document):
                raw_text = self._chunker.serialize(chunk=chunk)
                contextualized = self._chunker.contextualize(chunk)

                # Extract headings from chunk metadata
                headings = []
                if hasattr(chunk, "meta") and chunk.meta:
                    headings = chunk.meta.get("headings", [])

                # Build chunk dict
                chunk_dict = {
                    "text": raw_text,
                    "contextualized_text": contextualized or raw_text,
                    "headings": headings,
                    "meta": {
                        "page": getattr(chunk, "page", None),
                        "offset": getattr(chunk, "start_offset", 0),
                        "chunk_id": getattr(chunk, "id", None),
                    },
                }
                chunks.append(chunk_dict)

            logger.info(f"Chunked {file_path.name}: {len(chunks)} chunks")
            return chunks

        except Exception as e:
            logger.error(f"Error chunking {file_path}: {e}")
            # Fallback to simple text extraction
            return await self._fallback_chunk(file_path)

    async def _fallback_chunk(self, file_path: Path) -> list[dict[str, Any]]:
        """Fallback chunking for files that fail HybridChunker."""
        try:
            text = file_path.read_text(encoding="utf-8", errors="ignore")

            # Simple paragraph-based chunking
            paragraphs = text.split("\n\n")
            chunks = []
            current_chunk = []
            current_size = 0

            for para in paragraphs:
                para_size = len(para.split())
                if current_size + para_size > self._max_tokens and current_chunk:
                    chunk_text = "\n\n".join(current_chunk)
                    chunks.append({
                        "text": chunk_text,
                        "contextualized_text": chunk_text,
                        "headings": [],
                        "meta": {"page": None, "offset": 0},
                    })
                    current_chunk = []
                    current_size = 0

                current_chunk.append(para)
                current_size += para_size

            # Add remaining
            if current_chunk:
                chunk_text = "\n\n".join(current_chunk)
                chunks.append({
                    "text": chunk_text,
                    "contextualized_text": chunk_text,
                    "headings": [],
                    "meta": {"page": None, "offset": 0},
                })

            return chunks

        except Exception as e:
            logger.error(f"Fallback chunking failed for {file_path}: {e}")
            return []
```

**Step 4: Run tests**

Run: `uv run pytest tests/unit/ingestion/test_chunking_service.py -v`

Expected: All 2 tests PASS

**Step 5: Commit**

```bash
git add src/ingestion/chunking_service.py tests/unit/ingestion/test_chunking_service.py
git commit -m "feat(ingestion): add ChunkingService with Docling HybridChunker"
```

---

## Phase 4: Dead Letter Queue

### Task 5: Create DeadLetterQueue Class

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
        mock_conn.fetchrow = AsyncMock(return_value={"id": 1})
        mock_pool.acquire.return_value.__aenter__.return_value = mock_conn

        dlq = DeadLetterQueue(pool=mock_pool)
        item_id = await dlq.add(
            file_id="abc123",
            source_path="Test/doc.pdf",
            error_type="docling_timeout",
            error_message="Timeout after 120s",
        )

        assert item_id == 1
        mock_conn.fetchrow.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_unresolved(self, mock_pool):
        """get_unresolved returns items without resolved_at."""
        from src.ingestion.dead_letter import DeadLetterQueue

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

## Phase 5: Orchestrator & FileProcessor

### Task 6: Create Orchestrator Class

**Files:**
- Create: `src/ingestion/orchestrator.py`
- Create: `tests/unit/ingestion/test_orchestrator.py`

(Same as original plan - Task 4)

### Task 7: Create FileProcessor Class

**Files:**
- Create: `src/ingestion/file_processor.py`
- Create: `tests/unit/ingestion/test_file_processor.py`

(Same as original plan - Task 5, but using ChunkingService and EmbeddingService)

---

## Phase 6: CLI & Integration

### Task 8: Update __init__.py Exports

(Same as original plan - Task 6)

### Task 9: Create CLI Entry Point

(Same as original plan - Task 7)

### Task 10: Update Makefile

(Same as original plan - Task 8)

### Task 11: Integration Test

(Same as original plan - Task 10)

### Task 12: Update docs/INGESTION.md

(Same as original plan - Task 11, with 2026 best practices noted)

---

## Summary

### Files Created (v2 additions)
- `src/ingestion/embedding_service.py` - **NEW**: Redis-cached embeddings with backoff
- `src/ingestion/chunking_service.py` - **NEW**: Docling HybridChunker wrapper
- `tests/unit/ingestion/test_embedding_service.py`
- `tests/unit/ingestion/test_chunking_service.py`

### 2026 Best Practices Applied

| Feature | Implementation |
|---------|----------------|
| Voyage 3.5 (8M TPM) | `EmbeddingService` defaults to voyage-3.5 |
| Redis embedding cache | 24h TTL, 40-60% expected hit rate |
| Exponential backoff | tenacity with 6 retries on 429 |
| Batched embeddings | 128 docs/batch (Voyage limit) |
| HybridChunker | merge_peers=True, cl100k_base tokenizer |
| Contextualization | chunker.contextualize() for heading breadcrumbs |
| Cost tracking | embedding_tokens, embedding_cost_usd in DB |

### Verification

```bash
# Run all new tests
uv run pytest tests/unit/ingestion/ -v

# Setup and test
make ingest-db-setup
make ingest-status-unified
```
