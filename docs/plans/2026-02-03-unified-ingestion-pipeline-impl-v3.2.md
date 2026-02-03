# Unified Ingestion Pipeline v3.2 (CocoIndex Orchestrator + Custom Target)

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Production unified ingestion: rclone → CocoIndex (orchestrator) → Custom Qdrant Target (Docling + Voyage + BM42) → Postgres state + Loki monitoring.

**Architecture:**
```
Google Drive
     ↓ (systemd timer, 5min)
rclone sync → GDRIVE_SYNC_DIR (/data/drive-sync)
     ↓ (CocoIndex poll, 60s)
CocoIndex Flow (orchestrator)
     ├─ sources.LocalFile (detect changes)
     ├─ collector (file_id, metadata)
     └─ export → QdrantHybridTarget (custom)
                    ├─ DoclingClient (chunking)
                    ├─ VoyageService (dense 1024)
                    ├─ FastEmbed BM42 (sparse)
                    ├─ Qdrant (delete + upsert)
                    └─ Postgres (state + DLQ)
     ↓
Docker container → Loki → Alertmanager → Telegram
```

**Key Decisions:**
- ✅ **CocoIndex = orchestrator** (change detection, incremental, lineage)
- ✅ **Custom target connector** (full control: payload, vectors, semantics)
- ✅ **Reuse existing services** (VoyageService, DoclingClient, CacheService)
- ✅ **Extend existing Postgres schema** (ALTER TABLE, not new tables)
- ✅ **Docker service for ingestion** (unified Loki monitoring)
- ✅ **Payload contract enforced** (page_content + metadata.doc_id/order/source/file_id)

---

## Architectural Decisions (Fixed Before Code)

### 0.1 Source of Truth for Incrementality
- rclone syncs Drive → `GDRIVE_SYNC_DIR` (default: `/data/drive-sync` or `~/drive-sync`)
- CocoIndex reads only local folder via `sources.LocalFile`
- CocoIndex handles change detection (new/modified/deleted)

### 0.2 CocoIndex + Custom Target
CocoIndex builtin `targets.Qdrant` is too limited for our hybrid (named vectors + replace semantics + payload contract). Solution:
- **CocoIndex = orchestrator / change detector**
- **QdrantHybridTarget = custom target connector** that:
  - Calls DoclingClient for chunking
  - Generates embeddings (Voyage + BM42)
  - Implements delete-by-filter + upsert
  - Writes state/DLQ to Postgres

### 0.3 Payload Contract (REQUIRED)
All Qdrant points MUST have:
```python
{
    "page_content": str,  # Chunk text (required by retrieval)
    "metadata": {
        "file_id": str,      # sha256(relative_path)[:16]
        "doc_id": str,       # = file_id (for small-to-big)
        "order": int,        # Chunk order in document
        "chunk_order": int,  # Alias for compatibility
        "source": str,       # Relative path (for citations)
        "file_name": str,
        "mime_type": str,
        "content_hash": str,
        "modified_time": str,
        "headings": list[str],
        "chunk_location": str,
        "page_range": list[int] | None,
    },
    "file_id": str,  # Flat copy for fast delete-by-filter
}
```

### 0.4 Identifiers and Idempotency
- `file_id`: `sha256(relative_path)[:16]`
- `point_id`: `uuid5(file_id + chunk_location)`
- `chunk_location` priority:
  1. Docling meta (page/offset/refs)
  2. Fallback: `seq_no` from docling
  3. Last resort: `chunk_{i}` (avoid)

### 0.5 Update Semantics
MVP (reliable):
- On file update: `DELETE WHERE metadata.file_id == X` → `UPSERT` new chunks
- On file delete: `DELETE WHERE metadata.file_id == X`

---

## Phase 1: Qdrant Schema Setup

### Task 1.1: Extend Collection Setup Scripts

**Files:**
- Modify: `scripts/setup_scalar_collection.py`
- Modify: `scripts/setup_binary_collection.py`

**Step 1: Add required payload indexes**

Add to `create_payload_indexes()` in both scripts:

```python
# Required indexes for unified ingestion
required_keyword_fields = [
    "file_id",           # Flat, for fast delete
    "metadata.file_id",  # In metadata
    "metadata.doc_id",   # For small-to-big
    "metadata.source",   # For citations
]

required_integer_fields = [
    "metadata.order",        # For small-to-big sorting
    "metadata.chunk_order",  # Alias
]
```

**Step 2: Run**

```bash
uv run python scripts/setup_scalar_collection.py --source gdrive_documents --force
uv run python scripts/setup_binary_collection.py --source gdrive_documents --force
```

**Step 3: Verify indexes**

```bash
docker exec dev-qdrant curl -s localhost:6333/collections/gdrive_documents_scalar | jq '.result.payload_schema'
```

Expected: Shows `file_id`, `metadata.file_id`, `metadata.doc_id`, `metadata.order` indexes.

**Step 4: Commit**

```bash
git add scripts/setup_scalar_collection.py scripts/setup_binary_collection.py
git commit -m "feat(qdrant): add required payload indexes for unified ingestion

- file_id keyword (flat for fast delete)
- metadata.file_id, metadata.doc_id keyword (small-to-big)
- metadata.order, metadata.chunk_order integer (sorting)"
```

---

## Phase 2: Postgres Schema Extension

### Task 2.1: Create Migration Script

**Files:**
- Create: `docker/postgres/init/03-unified-ingestion-alter.sql`

**Step 1: Create idempotent migration**

```sql
-- docker/postgres/init/03-unified-ingestion-alter.sql
-- Unified ingestion pipeline schema extensions (idempotent)
-- Extends 02-cocoindex.sql tables

\c cocoindex;

-- Add missing columns to ingestion_state (idempotent)
DO $$
BEGIN
    -- Source info
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_name = 'ingestion_state' AND column_name = 'source_path') THEN
        ALTER TABLE ingestion_state ADD COLUMN source_path VARCHAR(1000);
    END IF;

    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_name = 'ingestion_state' AND column_name = 'file_size') THEN
        ALTER TABLE ingestion_state ADD COLUMN file_size BIGINT;
    END IF;

    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_name = 'ingestion_state' AND column_name = 'file_modified_at') THEN
        ALTER TABLE ingestion_state ADD COLUMN file_modified_at TIMESTAMPTZ;
    END IF;

    -- Pipeline versioning
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_name = 'ingestion_state' AND column_name = 'pipeline_version') THEN
        ALTER TABLE ingestion_state ADD COLUMN pipeline_version VARCHAR(20) DEFAULT 'v3.2';
    END IF;

    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_name = 'ingestion_state' AND column_name = 'chunk_location_version') THEN
        ALTER TABLE ingestion_state ADD COLUMN chunk_location_version VARCHAR(20) DEFAULT 'docling';
    END IF;

    -- Collection tracking
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_name = 'ingestion_state' AND column_name = 'collection_name') THEN
        ALTER TABLE ingestion_state ADD COLUMN collection_name VARCHAR(100);
    END IF;
END $$;

-- Add indexes for new columns
CREATE INDEX IF NOT EXISTS idx_ingestion_source_path ON ingestion_state(source_path);
CREATE INDEX IF NOT EXISTS idx_ingestion_collection ON ingestion_state(collection_name);
CREATE INDEX IF NOT EXISTS idx_ingestion_pipeline_version ON ingestion_state(pipeline_version);

-- Add retry_after for exponential backoff
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_name = 'ingestion_state' AND column_name = 'retry_after') THEN
        ALTER TABLE ingestion_state ADD COLUMN retry_after TIMESTAMPTZ;
    END IF;
END $$;

COMMENT ON TABLE ingestion_state IS 'Unified ingestion state tracking (v3.2)';
```

**Step 2: Apply migration**

```bash
docker exec -i dev-postgres psql -U postgres < docker/postgres/init/03-unified-ingestion-alter.sql
```

**Step 3: Verify**

```bash
docker exec dev-postgres psql -U postgres -d cocoindex -c "\d ingestion_state"
```

Expected: Shows new columns `source_path`, `file_size`, `file_modified_at`, `pipeline_version`, etc.

**Step 4: Commit**

```bash
git add docker/postgres/init/03-unified-ingestion-alter.sql
git commit -m "feat(db): add unified ingestion schema extensions

- source_path, file_size, file_modified_at for file tracking
- pipeline_version, chunk_location_version for versioning
- collection_name for multi-collection support
- retry_after for exponential backoff"
```

---

## Phase 3: Custom Target Connector (Core)

### Task 3.1: Create Module Structure

**Files:**
- Create: `src/ingestion/unified/__init__.py`
- Create: `src/ingestion/unified/config.py`

**Step 1: Create config.py**

```python
# src/ingestion/unified/config.py
"""Configuration for unified ingestion pipeline."""

import os
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class UnifiedConfig:
    """Unified ingestion pipeline configuration."""

    # Paths
    sync_dir: Path = field(
        default_factory=lambda: Path(os.getenv("GDRIVE_SYNC_DIR", os.path.expanduser("~/drive-sync")))
    )

    # Database
    database_url: str = field(
        default_factory=lambda: os.getenv(
            "INGESTION_DATABASE_URL",
            "postgresql://postgres:postgres@localhost:5432/cocoindex"
        )
    )

    ***REMOVED***
    qdrant_url: str = field(default_factory=lambda: os.getenv("QDRANT_URL", "http://localhost:6333"))
    qdrant_api_key: str | None = field(default_factory=lambda: os.getenv("QDRANT_API_KEY"))
    collection_name: str = field(
        default_factory=lambda: os.getenv("GDRIVE_COLLECTION_NAME", "gdrive_documents_scalar")
    )

    # Docling
    docling_url: str = field(default_factory=lambda: os.getenv("DOCLING_URL", "http://localhost:5001"))
    docling_timeout: float = 300.0
    max_tokens_per_chunk: int = 512

    ***REMOVED***
    voyage_api_key: str = field(default_factory=lambda: os.getenv("VOYAGE_API_KEY", ""))
    voyage_model: str = "voyage-4-large"

    # BM42
    bm42_model: str = "Qdrant/bm42-all-minilm-l6-v2-attentions"

    # Pipeline
    poll_interval_seconds: int = 60
    max_retries: int = 3
    pipeline_version: str = "v3.2"

    # Supported extensions
    supported_extensions: frozenset[str] = frozenset({
        ".pdf", ".docx", ".doc", ".xlsx", ".pptx",
        ".md", ".txt", ".html", ".htm", ".csv"
    })
```

**Step 2: Create __init__.py**

```python
# src/ingestion/unified/__init__.py
"""Unified ingestion pipeline with CocoIndex orchestration."""

from src.ingestion.unified.config import UnifiedConfig

__all__ = ["UnifiedConfig"]
```

**Step 3: Commit**

```bash
git add src/ingestion/unified/
git commit -m "feat(ingestion): add unified pipeline config module"
```

---

### Task 3.2: Create State Manager

**Files:**
- Create: `src/ingestion/unified/state_manager.py`

**Step 1: Create state_manager.py**

```python
# src/ingestion/unified/state_manager.py
"""State manager using existing Postgres ingestion_state table."""

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

import asyncpg


@dataclass
class FileState:
    """Maps to ingestion_state table."""

    file_id: str
    source_path: str | None = None
    file_name: str | None = None
    mime_type: str | None = None
    file_size: int | None = None
    file_modified_at: datetime | None = None
    content_hash: str | None = None
    parser_version: str | None = None
    chunker_version: str | None = None
    embedding_model: str = "voyage-4-large"
    chunk_count: int = 0
    collection_name: str | None = None
    pipeline_version: str = "v3.2"
    indexed_at: datetime | None = None
    status: str = "pending"
    error_message: str | None = None
    retry_count: int = 0
    retry_after: datetime | None = None

    @classmethod
    def from_row(cls, row: asyncpg.Record) -> "FileState":
        """Create from database row."""
        return cls(**{k: v for k, v in dict(row).items() if k in cls.__dataclass_fields__})


class UnifiedStateManager:
    """Manages ingestion state in Postgres."""

    def __init__(
        self,
        pool: asyncpg.Pool | None = None,
        database_url: str | None = None,
    ):
        self._pool = pool
        self._database_url = database_url
        self._owns_pool = pool is None
        # Tables are in public schema of cocoindex database
        self._table = "ingestion_state"
        self._dlq_table = "ingestion_dead_letter"

    async def _get_pool(self) -> asyncpg.Pool:
        if self._pool is None:
            if self._database_url is None:
                raise ValueError("Either pool or database_url required")
            self._pool = await asyncpg.create_pool(self._database_url, min_size=1, max_size=5)
        return self._pool

    async def close(self) -> None:
        if self._owns_pool and self._pool:
            await self._pool.close()
            self._pool = None

    async def get_state(self, file_id: str) -> FileState | None:
        pool = await self._get_pool()
        row = await pool.fetchrow(
            f"SELECT * FROM {self._table} WHERE file_id = $1", file_id
        )
        return FileState.from_row(row) if row else None

    async def upsert_state(self, state: FileState) -> None:
        pool = await self._get_pool()
        await pool.execute(
            f"""
            INSERT INTO {self._table} (
                file_id, source_path, file_name, mime_type, file_size,
                file_modified_at, content_hash, parser_version, chunker_version,
                embedding_model, chunk_count, collection_name, pipeline_version,
                status, error_message, retry_count, retry_after, updated_at
            ) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17,NOW())
            ON CONFLICT (file_id) DO UPDATE SET
                source_path = EXCLUDED.source_path,
                file_name = EXCLUDED.file_name,
                mime_type = EXCLUDED.mime_type,
                file_size = EXCLUDED.file_size,
                file_modified_at = EXCLUDED.file_modified_at,
                content_hash = EXCLUDED.content_hash,
                parser_version = EXCLUDED.parser_version,
                chunker_version = EXCLUDED.chunker_version,
                collection_name = EXCLUDED.collection_name,
                pipeline_version = EXCLUDED.pipeline_version,
                status = EXCLUDED.status,
                error_message = EXCLUDED.error_message,
                retry_count = EXCLUDED.retry_count,
                retry_after = EXCLUDED.retry_after,
                updated_at = NOW()
            """,
            state.file_id, state.source_path, state.file_name, state.mime_type,
            state.file_size, state.file_modified_at, state.content_hash,
            state.parser_version, state.chunker_version, state.embedding_model,
            state.chunk_count, state.collection_name, state.pipeline_version,
            state.status, state.error_message, state.retry_count, state.retry_after,
        )

    async def mark_processing(self, file_id: str) -> None:
        pool = await self._get_pool()
        await pool.execute(
            f"UPDATE {self._table} SET status = 'processing', updated_at = NOW() WHERE file_id = $1",
            file_id,
        )

    async def mark_indexed(self, file_id: str, chunk_count: int, content_hash: str) -> None:
        pool = await self._get_pool()
        await pool.execute(
            f"""
            UPDATE {self._table}
            SET status = 'indexed', chunk_count = $2, content_hash = $3,
                indexed_at = NOW(), error_message = NULL, retry_count = 0, retry_after = NULL,
                updated_at = NOW()
            WHERE file_id = $1
            """,
            file_id, chunk_count, content_hash,
        )

    async def mark_error(self, file_id: str, error: str) -> None:
        pool = await self._get_pool()
        # Exponential backoff: 1min, 5min, 30min
        await pool.execute(
            f"""
            UPDATE {self._table}
            SET status = 'error',
                error_message = $2,
                retry_count = retry_count + 1,
                retry_after = NOW() + (INTERVAL '1 minute' * POWER(5, LEAST(retry_count, 3))),
                updated_at = NOW()
            WHERE file_id = $1
            """,
            file_id, error[:1000],  # Truncate error message
        )

    async def mark_deleted(self, file_id: str) -> None:
        pool = await self._get_pool()
        await pool.execute(
            f"UPDATE {self._table} SET status = 'deleted', updated_at = NOW() WHERE file_id = $1",
            file_id,
        )

    async def should_process(self, file_id: str, content_hash: str) -> bool:
        """Check if file needs processing (new or changed)."""
        state = await self.get_state(file_id)
        if state is None:
            return True  # New file
        if state.status == "indexed" and state.content_hash == content_hash:
            return False  # Unchanged
        if state.status == "error" and state.retry_after and state.retry_after > datetime.utcnow():
            return False  # Still in backoff
        if state.retry_count >= 3:
            return False  # Exceeded retries (in DLQ)
        return True

    async def get_all_indexed_file_ids(self) -> set[str]:
        pool = await self._get_pool()
        rows = await pool.fetch(
            f"SELECT file_id FROM {self._table} WHERE status = 'indexed'"
        )
        return {row["file_id"] for row in rows}

    async def add_to_dlq(
        self,
        file_id: str,
        error_type: str,
        error_message: str,
        payload: dict | None = None,
    ) -> int:
        pool = await self._get_pool()
        row = await pool.fetchrow(
            f"""
            INSERT INTO {self._dlq_table} (file_id, error_type, error_message, payload)
            VALUES ($1, $2, $3, $4::jsonb) RETURNING id
            """,
            file_id, error_type, error_message[:2000],
            __import__("json").dumps(payload) if payload else None,
        )
        return row["id"]

    async def get_stats(self) -> dict[str, int]:
        pool = await self._get_pool()
        rows = await pool.fetch(
            f"SELECT status, COUNT(*) as count FROM {self._table} GROUP BY status"
        )
        return {row["status"]: row["count"] for row in rows}

    async def get_dlq_count(self) -> int:
        pool = await self._get_pool()
        row = await pool.fetchrow(f"SELECT COUNT(*) as count FROM {self._dlq_table}")
        return row["count"]
```

**Step 2: Update __init__.py**

```python
# src/ingestion/unified/__init__.py
"""Unified ingestion pipeline with CocoIndex orchestration."""

from src.ingestion.unified.config import UnifiedConfig
from src.ingestion.unified.state_manager import UnifiedStateManager, FileState

__all__ = ["UnifiedConfig", "UnifiedStateManager", "FileState"]
```

**Step 3: Test import**

```bash
uv run python -c "from src.ingestion.unified import UnifiedStateManager; print('OK')"
```

**Step 4: Commit**

```bash
git add src/ingestion/unified/
git commit -m "feat(ingestion): add UnifiedStateManager with Postgres backend

- Uses existing ingestion_state table
- Exponential backoff for retries
- DLQ support for failed files
- Content hash based change detection"
```

---

### Task 3.3: Create Qdrant Writer

**Files:**
- Create: `src/ingestion/unified/qdrant_writer.py`

**Step 1: Create qdrant_writer.py**

```python
# src/ingestion/unified/qdrant_writer.py
"""Qdrant writer with payload contract and replace semantics."""

import hashlib
import logging
import uuid
from dataclasses import dataclass
from typing import Any

from fastembed import SparseTextEmbedding
from qdrant_client import QdrantClient
from qdrant_client.models import (
    FieldCondition,
    Filter,
    MatchValue,
    PointStruct,
    SparseVector,
)

from telegram_bot.services import VoyageService


logger = logging.getLogger(__name__)

# Namespace for deterministic UUID generation
NAMESPACE_GDRIVE = uuid.UUID("6ba7b810-9dad-11d1-80b4-00c04fd430c8")


@dataclass
class WriteStats:
    """Statistics from write operation."""

    points_deleted: int = 0
    points_upserted: int = 0
    errors: list[str] | None = None


class QdrantHybridWriter:
    """Writes chunks to Qdrant with hybrid vectors and payload contract.

    Payload Contract:
    - page_content: str (chunk text)
    - metadata: dict (doc_id, order, source, file_id, ...)
    - file_id: str (flat, for fast delete)

    Vector Names:
    - dense: Voyage 1024-dim
    - bm42: FastEmbed sparse
    """

    VOYAGE_BATCH_SIZE = 128

    def __init__(
        self,
        qdrant_url: str,
        qdrant_api_key: str | None = None,
        voyage_api_key: str | None = None,
        voyage_model: str = "voyage-4-large",
        bm42_model: str = "Qdrant/bm42-all-minilm-l6-v2-attentions",
    ):
        ***REMOVED*** client
        self.client = QdrantClient(
            url=qdrant_url,
            api_key=qdrant_api_key,
            timeout=120,
        )

        ***REMOVED*** for dense embeddings
        self.voyage = VoyageService(
            api_key=voyage_api_key,
            model_docs=voyage_model,
        )

        # FastEmbed BM42 for sparse
        self.sparse_model = SparseTextEmbedding(model_name=bm42_model)

        logger.info(f"QdrantHybridWriter initialized: {voyage_model} + {bm42_model}")

    @staticmethod
    def generate_point_id(file_id: str, chunk_location: str) -> str:
        """Generate deterministic point ID."""
        combined = f"{file_id}::{chunk_location}"
        return str(uuid.uuid5(NAMESPACE_GDRIVE, combined))

    @staticmethod
    def get_chunk_location(chunk: Any, index: int) -> str:
        """Get stable chunk location from docling metadata or fallback.

        Priority:
        1. Docling meta with page/offset
        2. seq_no from docling
        3. Fallback: chunk_{index}
        """
        # Check for docling metadata
        extra = getattr(chunk, "extra_metadata", {}) or {}
        docling_meta = extra.get("docling_meta", {})

        # Priority 1: Page + offset from docling
        if "page" in docling_meta or "page_start" in docling_meta:
            page = docling_meta.get("page") or docling_meta.get("page_start", 0)
            offset = docling_meta.get("offset", index)
            return f"page_{page}_offset_{offset}"

        # Priority 2: seq_no from docling
        if hasattr(chunk, "extra_metadata") and extra.get("chunk_order") is not None:
            return f"seq_{extra['chunk_order']}"

        # Priority 3: Use order if available
        if hasattr(chunk, "order") and chunk.order is not None:
            return f"order_{chunk.order}"

        # Fallback
        return f"chunk_{index}"

    def build_payload(
        self,
        chunk: Any,
        file_id: str,
        source_path: str,
        chunk_location: str,
        file_metadata: dict[str, Any],
    ) -> dict[str, Any]:
        """Build payload with enforced contract.

        Required fields:
        - page_content: chunk text
        - metadata.file_id, metadata.doc_id, metadata.order, metadata.source
        - file_id (flat for delete)
        """
        order = getattr(chunk, "order", 0) or getattr(chunk, "chunk_id", 0)
        extra = getattr(chunk, "extra_metadata", {}) or {}

        metadata = {
            # Identity (required for small-to-big)
            "file_id": file_id,
            "doc_id": file_id,  # Same as file_id for small-to-big compatibility

            # Order (required for small-to-big sorting)
            "order": order,
            "chunk_order": order,  # Alias

            # Source (required for citations)
            "source": source_path,
            "file_name": getattr(chunk, "document_name", file_metadata.get("file_name")),

            # Chunk position
            "chunk_id": getattr(chunk, "chunk_id", order),
            "chunk_location": chunk_location,

            # Document structure
            "section": getattr(chunk, "section", None),
            "headings": extra.get("headings", []),

            # Page info
            "page_range": list(chunk.page_range) if getattr(chunk, "page_range", None) else None,

            # File info
            "mime_type": file_metadata.get("mime_type"),
            "modified_time": file_metadata.get("modified_time"),
            "content_hash": file_metadata.get("content_hash"),
        }

        # Clean None values
        metadata = {k: v for k, v in metadata.items() if v is not None}

        return {
            "page_content": chunk.text,
            "metadata": metadata,
            "file_id": file_id,  # Flat for fast delete
        }

    async def delete_file(self, file_id: str, collection_name: str) -> int:
        """Delete all points for a file.

        Uses metadata.file_id filter (more reliable than flat file_id).
        """
        # Count before delete
        count_result = self.client.count(
            collection_name=collection_name,
            count_filter=Filter(
                must=[FieldCondition(key="metadata.file_id", match=MatchValue(value=file_id))]
            ),
        )
        count = count_result.count

        if count > 0:
            # Delete by metadata.file_id
            self.client.delete(
                collection_name=collection_name,
                points_selector=Filter(
                    must=[FieldCondition(key="metadata.file_id", match=MatchValue(value=file_id))]
                ),
            )
            logger.info(f"Deleted {count} points for file_id={file_id}")

        return count

    async def upsert_chunks(
        self,
        chunks: list[Any],
        file_id: str,
        source_path: str,
        file_metadata: dict[str, Any],
        collection_name: str,
    ) -> WriteStats:
        """Upsert chunks with replace semantics.

        1. Delete existing points for file_id
        2. Generate embeddings
        3. Build points with payload contract
        4. Upsert to Qdrant
        """
        stats = WriteStats()

        if not chunks:
            return stats

        try:
            # Step 1: Delete existing (replace semantics)
            stats.points_deleted = await self.delete_file(file_id, collection_name)

            # Step 2: Extract texts
            texts = [chunk.text for chunk in chunks]

            # Step 3: Generate embeddings
            dense_embeddings = await self.voyage.embed_documents(texts)
            sparse_embeddings = list(self.sparse_model.embed(texts))

            # Step 4: Build points
            points = []
            for i, (chunk, dense_vec, sparse_emb) in enumerate(
                zip(chunks, dense_embeddings, sparse_embeddings, strict=True)
            ):
                chunk_location = self.get_chunk_location(chunk, i)
                point_id = self.generate_point_id(file_id, chunk_location)
                payload = self.build_payload(
                    chunk, file_id, source_path, chunk_location, file_metadata
                )

                point = PointStruct(
                    id=point_id,
                    vector={
                        "dense": dense_vec,
                        "bm42": SparseVector(
                            indices=sparse_emb.indices.tolist(),
                            values=sparse_emb.values.tolist(),
                        ),
                    },
                    payload=payload,
                )
                points.append(point)

            # Step 5: Upsert
            self.client.upsert(collection_name=collection_name, points=points)
            stats.points_upserted = len(points)

            logger.info(
                f"Upserted {stats.points_upserted} points for {source_path} "
                f"(replaced {stats.points_deleted})"
            )

        except Exception as e:
            stats.errors = [str(e)]
            logger.error(f"Error upserting chunks: {e}", exc_info=True)

        return stats
```

**Step 2: Test import**

```bash
uv run python -c "from src.ingestion.unified.qdrant_writer import QdrantHybridWriter; print('OK')"
```

**Step 3: Commit**

```bash
git add src/ingestion/unified/qdrant_writer.py
git commit -m "feat(ingestion): add QdrantHybridWriter with payload contract

- Enforces page_content + metadata structure
- Stable chunk_location from docling meta
- Deterministic point_id via uuid5
- Replace semantics (delete + upsert)
- Voyage dense + BM42 sparse vectors"
```

---

### Task 3.4: Create Payload Contract Test

**Files:**
- Create: `tests/unit/ingestion/test_payload_contract.py`

**Step 1: Write test**

```python
# tests/unit/ingestion/test_payload_contract.py
"""Tests for payload contract compliance."""

import pytest
from unittest.mock import MagicMock


class TestPayloadContract:
    """Test that payload meets bot requirements."""

    def test_payload_has_required_fields(self):
        """Payload must have page_content, metadata dict, and flat file_id."""
        from src.ingestion.unified.qdrant_writer import QdrantHybridWriter

        writer = QdrantHybridWriter.__new__(QdrantHybridWriter)

        chunk = MagicMock()
        chunk.text = "Test content"
        chunk.chunk_id = 0
        chunk.order = 0
        chunk.document_name = "test.pdf"
        chunk.section = "Introduction"
        chunk.page_range = (1, 2)
        chunk.extra_metadata = {"headings": ["Title"], "chunk_order": 0}

        file_metadata = {
            "file_name": "test.pdf",
            "mime_type": "application/pdf",
            "modified_time": "2026-02-03T12:00:00Z",
            "content_hash": "abc123",
        }

        payload = writer.build_payload(
            chunk=chunk,
            file_id="file123",
            source_path="docs/test.pdf",
            chunk_location="page_1_offset_0",
            file_metadata=file_metadata,
        )

        # Required top-level fields
        assert "page_content" in payload
        assert payload["page_content"] == "Test content"
        assert "metadata" in payload
        assert isinstance(payload["metadata"], dict)
        assert "file_id" in payload  # Flat for delete

        # Required metadata fields (for small-to-big)
        assert payload["metadata"]["file_id"] == "file123"
        assert payload["metadata"]["doc_id"] == "file123"
        assert payload["metadata"]["order"] == 0
        assert payload["metadata"]["chunk_order"] == 0
        assert payload["metadata"]["source"] == "docs/test.pdf"

    def test_chunk_location_stability(self):
        """chunk_location should be stable for same input."""
        from src.ingestion.unified.qdrant_writer import QdrantHybridWriter

        chunk1 = MagicMock()
        chunk1.extra_metadata = {"docling_meta": {"page": 1, "offset": 100}}

        chunk2 = MagicMock()
        chunk2.extra_metadata = {"docling_meta": {"page": 1, "offset": 100}}

        loc1 = QdrantHybridWriter.get_chunk_location(chunk1, 0)
        loc2 = QdrantHybridWriter.get_chunk_location(chunk2, 0)

        assert loc1 == loc2
        assert loc1 == "page_1_offset_100"

    def test_point_id_deterministic(self):
        """point_id should be deterministic for same file_id + chunk_location."""
        from src.ingestion.unified.qdrant_writer import QdrantHybridWriter

        id1 = QdrantHybridWriter.generate_point_id("file123", "page_1_offset_0")
        id2 = QdrantHybridWriter.generate_point_id("file123", "page_1_offset_0")
        id3 = QdrantHybridWriter.generate_point_id("file123", "page_1_offset_1")

        assert id1 == id2  # Same input = same output
        assert id1 != id3  # Different chunk_location = different ID

    def test_fallback_chunk_location(self):
        """Should fallback gracefully when no docling meta."""
        from src.ingestion.unified.qdrant_writer import QdrantHybridWriter

        # No metadata
        chunk = MagicMock()
        chunk.extra_metadata = None
        chunk.order = None

        loc = QdrantHybridWriter.get_chunk_location(chunk, 5)
        assert loc == "chunk_5"

        # With order
        chunk.order = 3
        loc = QdrantHybridWriter.get_chunk_location(chunk, 5)
        assert loc == "order_3"
```

**Step 2: Run test**

```bash
uv run pytest tests/unit/ingestion/test_payload_contract.py -v
```

Expected: All tests PASS.

**Step 3: Commit**

```bash
git add tests/unit/ingestion/test_payload_contract.py
git commit -m "test(ingestion): add payload contract tests

- page_content + metadata structure
- chunk_location stability
- point_id determinism
- Fallback behavior"
```

---

### Task 3.5: Create QdrantHybridTarget (CocoIndex Custom Target)

**Files:**
- Create: `src/ingestion/unified/targets/__init__.py`
- Create: `src/ingestion/unified/targets/qdrant_hybrid.py`

**Step 1: Create targets/__init__.py**

```python
# src/ingestion/unified/targets/__init__.py
"""Custom CocoIndex target connectors."""

from src.ingestion.unified.targets.qdrant_hybrid import QdrantHybridTarget

__all__ = ["QdrantHybridTarget"]
```

**Step 2: Create qdrant_hybrid.py**

```python
# src/ingestion/unified/targets/qdrant_hybrid.py
"""CocoIndex custom target for Qdrant hybrid search.

This target connector receives mutations from CocoIndex and:
1. Parses documents via DoclingClient
2. Generates embeddings (Voyage + BM42)
3. Writes to Qdrant with payload contract
4. Updates state in Postgres
"""

import asyncio
import hashlib
import logging
from datetime import datetime, UTC
from pathlib import Path
from typing import Any

from src.ingestion.docling_client import DoclingClient, DoclingConfig
from src.ingestion.unified.config import UnifiedConfig
from src.ingestion.unified.qdrant_writer import QdrantHybridWriter
from src.ingestion.unified.state_manager import UnifiedStateManager, FileState


logger = logging.getLogger(__name__)


def compute_content_hash(file_path: Path) -> str:
    """Compute SHA256 hash of file content."""
    hasher = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            hasher.update(chunk)
    return hasher.hexdigest()[:16]


class QdrantHybridTarget:
    """CocoIndex-compatible target for Qdrant hybrid search.

    Receives mutations (insert/update/delete) from CocoIndex and processes them.
    """

    def __init__(
        self,
        config: UnifiedConfig,
        state_manager: UnifiedStateManager,
        qdrant_writer: QdrantHybridWriter,
        docling_client: DoclingClient | None = None,
    ):
        self.config = config
        self.state_manager = state_manager
        self.qdrant_writer = qdrant_writer
        self._docling = docling_client
        self._owns_docling = docling_client is None

    async def _get_docling(self) -> DoclingClient:
        if self._docling is None:
            docling_config = DoclingConfig(
                base_url=self.config.docling_url,
                timeout=self.config.docling_timeout,
                max_tokens=self.config.max_tokens_per_chunk,
            )
            self._docling = DoclingClient(docling_config)
            await self._docling.connect()
        return self._docling

    async def close(self) -> None:
        if self._owns_docling and self._docling:
            await self._docling.close()
            self._docling = None

    async def handle_delete(self, file_id: str) -> bool:
        """Handle file deletion."""
        try:
            await self.qdrant_writer.delete_file(file_id, self.config.collection_name)
            await self.state_manager.mark_deleted(file_id)
            logger.info(f"Deleted: file_id={file_id}")
            return True
        except Exception as e:
            logger.error(f"Delete failed for {file_id}: {e}")
            return False

    async def handle_upsert(
        self,
        file_id: str,
        abs_path: Path,
        source_path: str,
        file_metadata: dict[str, Any],
    ) -> bool:
        """Handle file insert/update."""
        try:
            # Check if processing needed
            content_hash = compute_content_hash(abs_path)
            if not await self.state_manager.should_process(file_id, content_hash):
                logger.debug(f"Skipping unchanged: {source_path}")
                return True

            # Mark processing
            await self.state_manager.mark_processing(file_id)

            # Get docling client
            docling = await self._get_docling()

            # Parse and chunk
            docling_chunks = await docling.chunk_file(abs_path)
            if not docling_chunks:
                # Empty file or unsupported
                await self.state_manager.mark_indexed(file_id, 0, content_hash)
                logger.warning(f"No chunks from: {source_path}")
                return True

            # Convert to standard chunks
            chunks = docling.to_ingestion_chunks(
                docling_chunks,
                source=source_path,
                source_type=abs_path.suffix.lstrip("."),
            )

            # Enrich file_metadata
            file_metadata = {
                **file_metadata,
                "content_hash": content_hash,
                "modified_time": datetime.now(UTC).isoformat(),
            }

            # Write to Qdrant
            stats = await self.qdrant_writer.upsert_chunks(
                chunks=chunks,
                file_id=file_id,
                source_path=source_path,
                file_metadata=file_metadata,
                collection_name=self.config.collection_name,
            )

            if stats.errors:
                raise Exception("; ".join(stats.errors))

            # Update state
            await self.state_manager.mark_indexed(file_id, stats.points_upserted, content_hash)
            logger.info(f"Indexed: {source_path} ({stats.points_upserted} chunks)")
            return True

        except Exception as e:
            logger.error(f"Upsert failed for {source_path}: {e}")
            await self.state_manager.mark_error(file_id, str(e))

            # Check if should go to DLQ
            state = await self.state_manager.get_state(file_id)
            if state and state.retry_count >= self.config.max_retries:
                await self.state_manager.add_to_dlq(
                    file_id=file_id,
                    error_type=type(e).__name__,
                    error_message=str(e),
                    payload={"source_path": source_path},
                )
                logger.warning(f"Moved to DLQ: {source_path}")

            return False

    async def mutate(self, mutation: dict[str, Any] | None, file_id: str) -> bool:
        """CocoIndex-style mutation handler.

        Args:
            mutation: None for delete, dict with file info for upsert
            file_id: File identifier

        Returns:
            True if successful
        """
        if mutation is None:
            return await self.handle_delete(file_id)
        else:
            return await self.handle_upsert(
                file_id=file_id,
                abs_path=Path(mutation["abs_path"]),
                source_path=mutation["source_path"],
                file_metadata=mutation.get("metadata", {}),
            )
```

**Step 3: Update __init__.py**

```python
# src/ingestion/unified/__init__.py
"""Unified ingestion pipeline with CocoIndex orchestration."""

from src.ingestion.unified.config import UnifiedConfig
from src.ingestion.unified.state_manager import UnifiedStateManager, FileState
from src.ingestion.unified.qdrant_writer import QdrantHybridWriter
from src.ingestion.unified.targets import QdrantHybridTarget

__all__ = [
    "UnifiedConfig",
    "UnifiedStateManager",
    "FileState",
    "QdrantHybridWriter",
    "QdrantHybridTarget",
]
```

**Step 4: Commit**

```bash
git add src/ingestion/unified/
git commit -m "feat(ingestion): add QdrantHybridTarget for CocoIndex

- Custom target connector for full control
- Integrates DoclingClient, QdrantHybridWriter
- Handles upsert with content hash checking
- DLQ support for failed files"
```

---

## Phase 4: CocoIndex Flow

### Task 4.1: Create CocoIndex Orchestrator Flow

**Files:**
- Create: `src/ingestion/unified/coco_flow.py`

**Step 1: Create coco_flow.py**

```python
# src/ingestion/unified/coco_flow.py
"""CocoIndex flow for unified ingestion pipeline.

CocoIndex acts as the orchestrator:
- Watches GDRIVE_SYNC_DIR for changes
- Detects new/modified/deleted files
- Calls QdrantHybridTarget for each mutation
"""

import asyncio
import hashlib
import logging
import os
from dataclasses import dataclass
from datetime import datetime, UTC
from pathlib import Path
from typing import Any

from src.ingestion.unified.config import UnifiedConfig
from src.ingestion.unified.state_manager import UnifiedStateManager
from src.ingestion.unified.qdrant_writer import QdrantHybridWriter
from src.ingestion.unified.targets import QdrantHybridTarget


logger = logging.getLogger(__name__)


def compute_file_id(sync_dir: Path, file_path: Path) -> str:
    """Compute file_id from relative path."""
    relative = file_path.relative_to(sync_dir)
    return hashlib.sha256(str(relative).encode()).hexdigest()[:16]


@dataclass
class FileInfo:
    """Information about a file in sync directory."""

    file_id: str
    abs_path: Path
    source_path: str  # Relative path
    file_name: str
    mime_type: str
    file_size: int
    modified_time: datetime


class UnifiedIngestionFlow:
    """Orchestrates file ingestion using CocoIndex-style change detection."""

    MIME_TYPES = {
        ".pdf": "application/pdf",
        ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ".doc": "application/msword",
        ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        ".md": "text/markdown",
        ".txt": "text/plain",
        ".html": "text/html",
        ".htm": "text/html",
        ".csv": "text/csv",
    }

    def __init__(self, config: UnifiedConfig):
        self.config = config
        self._state_manager: UnifiedStateManager | None = None
        self._target: QdrantHybridTarget | None = None

    async def _init_components(self) -> None:
        """Initialize state manager and target."""
        if self._state_manager is None:
            self._state_manager = UnifiedStateManager(database_url=self.config.database_url)

        if self._target is None:
            writer = QdrantHybridWriter(
                qdrant_url=self.config.qdrant_url,
                qdrant_api_key=self.config.qdrant_api_key,
                voyage_api_key=self.config.voyage_api_key,
                voyage_model=self.config.voyage_model,
                bm42_model=self.config.bm42_model,
            )
            self._target = QdrantHybridTarget(
                config=self.config,
                state_manager=self._state_manager,
                qdrant_writer=writer,
            )

    async def close(self) -> None:
        """Clean up resources."""
        if self._target:
            await self._target.close()
        if self._state_manager:
            await self._state_manager.close()

    def _is_supported(self, path: Path) -> bool:
        """Check if file is supported for ingestion."""
        if path.name.startswith(".") or path.name.startswith("~$"):
            return False
        return path.suffix.lower() in self.config.supported_extensions

    def _scan_files(self) -> dict[str, FileInfo]:
        """Scan sync directory for supported files."""
        files = {}
        sync_dir = self.config.sync_dir

        if not sync_dir.exists():
            logger.warning(f"Sync directory does not exist: {sync_dir}")
            return files

        for path in sync_dir.rglob("*"):
            if not path.is_file() or not self._is_supported(path):
                continue

            file_id = compute_file_id(sync_dir, path)
            stat = path.stat()

            files[file_id] = FileInfo(
                file_id=file_id,
                abs_path=path,
                source_path=str(path.relative_to(sync_dir)),
                file_name=path.name,
                mime_type=self.MIME_TYPES.get(path.suffix.lower(), "application/octet-stream"),
                file_size=stat.st_size,
                modified_time=datetime.fromtimestamp(stat.st_mtime, tz=UTC),
            )

        return files

    async def detect_changes(self) -> tuple[list[FileInfo], list[str]]:
        """Detect new/modified files and deleted files.

        Returns:
            (files_to_process, file_ids_to_delete)
        """
        await self._init_components()

        current_files = self._scan_files()
        current_ids = set(current_files.keys())
        indexed_ids = await self._state_manager.get_all_indexed_file_ids()

        # New files
        new_ids = current_ids - indexed_ids
        files_to_process = [current_files[fid] for fid in new_ids]

        # Modified files (check in target.handle_upsert via content_hash)
        existing_ids = current_ids & indexed_ids
        for fid in existing_ids:
            files_to_process.append(current_files[fid])

        # Deleted files
        deleted_ids = list(indexed_ids - current_ids)

        logger.info(
            f"Changes detected: {len(new_ids)} new, "
            f"{len(existing_ids)} to check, {len(deleted_ids)} deleted"
        )

        return files_to_process, deleted_ids

    async def run_once(self) -> dict[str, int]:
        """Run one ingestion cycle.

        Returns:
            Stats dict with processed/failed/deleted counts
        """
        await self._init_components()

        stats = {"processed": 0, "failed": 0, "deleted": 0, "skipped": 0}

        files_to_process, deleted_ids = await self.detect_changes()

        # Handle deletions
        for file_id in deleted_ids:
            success = await self._target.handle_delete(file_id)
            if success:
                stats["deleted"] += 1
            else:
                stats["failed"] += 1

        # Handle upserts
        for file_info in files_to_process:
            mutation = {
                "abs_path": str(file_info.abs_path),
                "source_path": file_info.source_path,
                "metadata": {
                    "file_name": file_info.file_name,
                    "mime_type": file_info.mime_type,
                    "file_size": file_info.file_size,
                },
            }
            success = await self._target.mutate(mutation, file_info.file_id)
            if success:
                stats["processed"] += 1
            else:
                stats["failed"] += 1

        return stats

    async def run_watch(self, interval: int | None = None) -> None:
        """Run continuous ingestion loop.

        Args:
            interval: Poll interval in seconds (default from config)
        """
        interval = interval or self.config.poll_interval_seconds
        logger.info(f"Starting watch mode: {self.config.sync_dir} (interval={interval}s)")

        try:
            while True:
                stats = await self.run_once()
                if stats["processed"] or stats["deleted"] or stats["failed"]:
                    logger.info(
                        f"Cycle complete: processed={stats['processed']}, "
                        f"deleted={stats['deleted']}, failed={stats['failed']}"
                    )
                await asyncio.sleep(interval)
        except asyncio.CancelledError:
            logger.info("Watch mode cancelled")
        finally:
            await self.close()
```

**Step 2: Commit**

```bash
git add src/ingestion/unified/coco_flow.py
git commit -m "feat(ingestion): add UnifiedIngestionFlow orchestrator

- Scans sync directory for supported files
- Detects changes (new/modified/deleted)
- Calls QdrantHybridTarget for mutations
- Watch mode with configurable interval"
```

---

## Phase 5: CLI and Docker Integration

### Task 5.1: Create CLI

**Files:**
- Create: `src/ingestion/unified/cli.py`

**Step 1: Create cli.py**

```python
# src/ingestion/unified/cli.py
"""CLI for unified ingestion pipeline."""

import argparse
import asyncio
import logging
import sys

from dotenv import load_dotenv


def setup_logging(verbose: bool = False) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )
    # Quiet noisy loggers
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)


async def cmd_run(args: argparse.Namespace) -> int:
    """Run ingestion."""
    from src.ingestion.unified.config import UnifiedConfig
    from src.ingestion.unified.coco_flow import UnifiedIngestionFlow

    config = UnifiedConfig()
    flow = UnifiedIngestionFlow(config)

    try:
        if args.watch:
            logging.info(f"Starting watch mode: {config.sync_dir}")
            await flow.run_watch(interval=args.interval)
        else:
            stats = await flow.run_once()
            logging.info(
                f"Done: processed={stats['processed']}, "
                f"deleted={stats['deleted']}, failed={stats['failed']}"
            )
    finally:
        await flow.close()

    return 0


async def cmd_status(args: argparse.Namespace) -> int:
    """Show ingestion status."""
    from src.ingestion.unified.config import UnifiedConfig
    from src.ingestion.unified.state_manager import UnifiedStateManager

    config = UnifiedConfig()
    manager = UnifiedStateManager(database_url=config.database_url)

    try:
        stats = await manager.get_stats()
        dlq_count = await manager.get_dlq_count()

        print("\n=== Ingestion Status ===")
        total = sum(stats.values())
        for status, count in sorted(stats.items()):
            pct = count / total * 100 if total else 0
            print(f"  {status}: {count} ({pct:.1f}%)")
        print(f"  TOTAL: {total}")
        print(f"\n  DLQ: {dlq_count} items")
        print(f"  Collection: {config.collection_name}")
        print(f"  Sync dir: {config.sync_dir}")
    finally:
        await manager.close()

    return 0


async def cmd_reprocess(args: argparse.Namespace) -> int:
    """Reprocess a specific file or all errors."""
    from src.ingestion.unified.config import UnifiedConfig
    from src.ingestion.unified.state_manager import UnifiedStateManager

    config = UnifiedConfig()
    manager = UnifiedStateManager(database_url=config.database_url)

    try:
        if args.file_id:
            # Reset specific file
            pool = await manager._get_pool()
            await pool.execute(
                "UPDATE ingestion_state SET status = 'pending', retry_count = 0, retry_after = NULL WHERE file_id = $1",
                args.file_id,
            )
            print(f"Reset file: {args.file_id}")
        elif args.errors:
            # Reset all errors
            pool = await manager._get_pool()
            result = await pool.execute(
                "UPDATE ingestion_state SET status = 'pending', retry_count = 0, retry_after = NULL WHERE status = 'error'"
            )
            print(f"Reset error files: {result}")
    finally:
        await manager.close()

    return 0


def main() -> int:
    load_dotenv()

    parser = argparse.ArgumentParser(
        description="Unified Ingestion Pipeline (v3.2)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="Verbose output")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # run
    run_p = subparsers.add_parser("run", help="Run ingestion")
    run_p.add_argument("--watch", "-w", action="store_true", help="Continuous mode")
    run_p.add_argument("--interval", "-i", type=int, default=60, help="Poll interval (s)")

    # status
    subparsers.add_parser("status", help="Show status")

    # reprocess
    reprocess_p = subparsers.add_parser("reprocess", help="Reprocess files")
    reprocess_p.add_argument("--file-id", help="Specific file ID")
    reprocess_p.add_argument("--errors", action="store_true", help="All error files")

    args = parser.parse_args()
    setup_logging(args.verbose)

    if args.command == "run":
        return asyncio.run(cmd_run(args))
    elif args.command == "status":
        return asyncio.run(cmd_status(args))
    elif args.command == "reprocess":
        return asyncio.run(cmd_reprocess(args))

    return 1


if __name__ == "__main__":
    sys.exit(main())
```

**Step 2: Commit**

```bash
git add src/ingestion/unified/cli.py
git commit -m "feat(ingestion): add unified pipeline CLI

- run: single or watch mode
- status: show stats from Postgres
- reprocess: reset errors or specific file"
```

---

### Task 5.2: Add Docker Service

**Files:**
- Modify: `docker-compose.dev.yml`

**Step 1: Add ingestion service**

Add after the bot service:

```yaml
  # Unified Ingestion Pipeline (v3.2)
  ingestion:
    build:
      context: .
      dockerfile: Dockerfile
    container_name: dev-ingestion
    restart: unless-stopped
    command: ["uv", "run", "python", "-m", "src.ingestion.unified.cli", "run", "--watch"]
    environment:
      - GDRIVE_SYNC_DIR=/data/drive-sync
      - INGESTION_DATABASE_URL=postgresql://postgres:postgres@postgres:5432/cocoindex
      - QDRANT_URL=http://qdrant:6333
      - DOCLING_URL=http://docling:5001
      - VOYAGE_API_KEY=${VOYAGE_API_KEY}
      - GDRIVE_COLLECTION_NAME=gdrive_documents_scalar
    volumes:
      - ${GDRIVE_SYNC_DIR:-~/drive-sync}:/data/drive-sync:ro
    depends_on:
      postgres:
        condition: service_healthy
      qdrant:
        condition: service_started
      docling:
        condition: service_started
    healthcheck:
      test: ["CMD", "pgrep", "-f", "src.ingestion.unified.cli"]
      interval: 30s
      timeout: 10s
      retries: 3
    logging:
      driver: "json-file"
      options:
        max-size: "10m"
        max-file: "3"
```

**Step 2: Commit**

```bash
git add docker-compose.dev.yml
git commit -m "feat(docker): add unified ingestion service

- Runs in watch mode by default
- Mounts sync dir read-only
- Connects to postgres, qdrant, docling
- JSON logging for Loki"
```

---

### Task 5.3: Add Makefile Targets

**Files:**
- Modify: `Makefile`

**Step 1: Add targets**

```makefile
# =============================================================================
# UNIFIED INGESTION PIPELINE (v3.2)
# =============================================================================

.PHONY: ingest-unified ingest-unified-watch ingest-unified-status ingest-unified-reprocess

ingest-unified: ## Run unified ingestion once
	set -a && source .env && set +a && uv run python -m src.ingestion.unified.cli run

ingest-unified-watch: ## Run unified ingestion continuously
	set -a && source .env && set +a && uv run python -m src.ingestion.unified.cli run --watch

ingest-unified-status: ## Show unified ingestion status
	set -a && source .env && set +a && uv run python -m src.ingestion.unified.cli status

ingest-unified-reprocess: ## Reprocess all error files
	set -a && source .env && set +a && uv run python -m src.ingestion.unified.cli reprocess --errors

ingest-unified-logs: ## Show ingestion service logs
	docker logs dev-ingestion -f --tail 100
```

**Step 2: Verify**

```bash
make help | grep ingest-unified
```

**Step 3: Commit**

```bash
git add Makefile
git commit -m "feat(make): add unified ingestion targets"
```

---

## Phase 6: Monitoring (Loki Rules)

### Task 6.1: Create Ingestion Alert Rules

**Files:**
- Create: `docker/monitoring/rules/ingestion.yaml`

**Step 1: Create LogQL-based rules**

```yaml
# docker/monitoring/rules/ingestion.yaml
# Alert rules for unified ingestion pipeline (LogQL)

groups:
  - name: ingestion
    interval: 1m
    rules:
      # Pipeline stalled
      - alert: IngestionPipelineStalled
        expr: |
          count_over_time({container="dev-ingestion"} |~ "Cycle complete" [1h]) == 0
          and
          count_over_time({container="dev-ingestion"} |~ "Starting watch" [24h]) > 0
        for: 30m
        labels:
          severity: warning
          service: ingestion
        annotations:
          summary: "Ingestion pipeline stalled"
          description: "No ingestion cycles completed in 1 hour"

      # High failure rate
      - alert: IngestionHighFailureRate
        expr: |
          sum(count_over_time({container="dev-ingestion"} |~ "failed=" [15m]))
          / sum(count_over_time({container="dev-ingestion"} |~ "Cycle complete" [15m])) > 0.3
        for: 15m
        labels:
          severity: warning
          service: ingestion
        annotations:
          summary: "Ingestion failure rate >30%"
          description: "Check docling, voyage, or qdrant connectivity"

      # DLQ growing
      - alert: IngestionDLQGrowing
        expr: |
          count_over_time({container="dev-ingestion"} |~ "Moved to DLQ" [1h]) > 3
        for: 15m
        labels:
          severity: warning
          service: ingestion
        annotations:
          summary: "Files moving to dead letter queue"
          description: "Multiple files failed after retries"

      # Docling errors
      - alert: DoclingErrors
        expr: |
          count_over_time({container="dev-ingestion"} |~ "(?i)docling.*error|docling.*timeout" [10m]) > 2
        for: 5m
        labels:
          severity: warning
          service: docling
        annotations:
          summary: "Docling processing errors"
          description: "Check dev-docling container health"

      ***REMOVED*** rate limiting
      - alert: VoyageRateLimited
        expr: |
          count_over_time({container="dev-ingestion"} |~ "(?i)voyage.*429|rate.*limit" [5m]) > 1
        for: 5m
        labels:
          severity: warning
          service: voyage
        annotations:
          summary: "Voyage API rate limited"
          description: "Consider reducing batch concurrency"

      # Container down
      - alert: IngestionContainerDown
        expr: |
          count_over_time({container="dev-ingestion"} [10m]) == 0
        for: 5m
        labels:
          severity: critical
          service: ingestion
        annotations:
          summary: "Ingestion container is down"
          description: "No logs from dev-ingestion container"
```

**Step 2: Commit**

```bash
git add docker/monitoring/rules/ingestion.yaml
git commit -m "feat(monitoring): add ingestion pipeline alert rules

- Pipeline stall detection
- Failure rate monitoring
- DLQ growth alerts
- Docling/Voyage error detection
- Container health"
```

---

## Phase 7: Integration Test

### Task 7.1: Create E2E Test

**Files:**
- Create: `tests/integration/test_unified_ingestion_e2e.py`

**Step 1: Create test**

```python
# tests/integration/test_unified_ingestion_e2e.py
"""E2E test for unified ingestion pipeline."""

import os
import pytest
from pathlib import Path

pytestmark = pytest.mark.skipif(
    not os.getenv("RUN_INTEGRATION_TESTS"),
    reason="Set RUN_INTEGRATION_TESTS=1"
)


@pytest.fixture
def temp_sync_dir(tmp_path):
    """Create temporary sync directory with test files."""
    sync_dir = tmp_path / "sync"
    sync_dir.mkdir()

    # Create test file
    test_file = sync_dir / "test.md"
    test_file.write_text("# Test Document\n\nThis is test content for ingestion.")

    return sync_dir


@pytest.mark.asyncio
async def test_unified_pipeline_e2e(temp_sync_dir):
    """File goes through pipeline with correct payload format."""
    from qdrant_client import QdrantClient

    from src.ingestion.unified.config import UnifiedConfig
    from src.ingestion.unified.coco_flow import UnifiedIngestionFlow, compute_file_id

    # Configure
    config = UnifiedConfig()
    config.sync_dir = temp_sync_dir
    config.collection_name = "test_unified_e2e"

    flow = UnifiedIngestionFlow(config)

    try:
        # Run ingestion
        stats = await flow.run_once()
        assert stats["processed"] >= 1, f"Expected at least 1 processed, got {stats}"

        # Verify in Qdrant
        qdrant = QdrantClient(url=config.qdrant_url)
        test_file = temp_sync_dir / "test.md"
        file_id = compute_file_id(temp_sync_dir, test_file)

        results, _ = qdrant.scroll(
            collection_name=config.collection_name,
            scroll_filter={
                "must": [{"key": "metadata.file_id", "match": {"value": file_id}}]
            },
            limit=10,
            with_payload=True,
        )

        assert len(results) > 0, "No points found in Qdrant"

        # Check payload contract
        payload = results[0].payload
        assert "page_content" in payload
        assert "metadata" in payload
        assert isinstance(payload["metadata"], dict)

        # Required metadata fields
        assert payload["metadata"]["file_id"] == file_id
        assert payload["metadata"]["doc_id"] == file_id
        assert "order" in payload["metadata"]
        assert "source" in payload["metadata"]

        # Flat file_id for delete
        assert payload["file_id"] == file_id

        # Cleanup
        qdrant.delete_collection(config.collection_name)

    finally:
        await flow.close()


@pytest.mark.asyncio
async def test_delete_removes_points(temp_sync_dir):
    """Deleting file removes points from Qdrant."""
    from qdrant_client import QdrantClient

    from src.ingestion.unified.config import UnifiedConfig
    from src.ingestion.unified.coco_flow import UnifiedIngestionFlow, compute_file_id

    config = UnifiedConfig()
    config.sync_dir = temp_sync_dir
    config.collection_name = "test_unified_delete"

    flow = UnifiedIngestionFlow(config)

    try:
        # First run - index file
        stats = await flow.run_once()
        assert stats["processed"] >= 1

        # Delete file
        test_file = temp_sync_dir / "test.md"
        file_id = compute_file_id(temp_sync_dir, test_file)
        test_file.unlink()

        # Second run - should detect deletion
        stats = await flow.run_once()
        assert stats["deleted"] >= 1

        # Verify points removed
        qdrant = QdrantClient(url=config.qdrant_url)
        count = qdrant.count(
            collection_name=config.collection_name,
            count_filter={
                "must": [{"key": "metadata.file_id", "match": {"value": file_id}}]
            },
        )
        assert count.count == 0, "Points should be deleted"

        # Cleanup
        qdrant.delete_collection(config.collection_name)

    finally:
        await flow.close()
```

**Step 2: Run test**

```bash
RUN_INTEGRATION_TESTS=1 uv run pytest tests/integration/test_unified_ingestion_e2e.py -v
```

**Step 3: Commit**

```bash
git add tests/integration/test_unified_ingestion_e2e.py
git commit -m "test(ingestion): add E2E tests for unified pipeline

- Payload contract verification
- Delete semantics test"
```

---

## Summary

### Files Created

| File | Purpose |
|------|---------|
| `src/ingestion/unified/__init__.py` | Module exports |
| `src/ingestion/unified/config.py` | Configuration |
| `src/ingestion/unified/state_manager.py` | Postgres state tracking |
| `src/ingestion/unified/qdrant_writer.py` | Qdrant write with payload contract |
| `src/ingestion/unified/targets/__init__.py` | Target exports |
| `src/ingestion/unified/targets/qdrant_hybrid.py` | CocoIndex custom target |
| `src/ingestion/unified/coco_flow.py` | Orchestrator flow |
| `src/ingestion/unified/cli.py` | CLI entry point |
| `docker/postgres/init/03-unified-ingestion-alter.sql` | Schema migration |
| `docker/monitoring/rules/ingestion.yaml` | Alert rules (LogQL) |
| `tests/unit/ingestion/test_payload_contract.py` | Payload tests |
| `tests/integration/test_unified_ingestion_e2e.py` | E2E tests |

### Files Modified

| File | Change |
|------|--------|
| `scripts/setup_scalar_collection.py` | Added required payload indexes |
| `scripts/setup_binary_collection.py` | Added required payload indexes |
| `docker-compose.dev.yml` | Added ingestion service |
| `Makefile` | Added unified targets |

### Components Reused (NOT duplicated)

| Component | Source | Usage |
|-----------|--------|-------|
| VoyageService | `telegram_bot/services/voyage.py` | Dense embeddings |
| DoclingClient | `src/ingestion/docling_client.py` | Parsing/chunking |
| FastEmbed BM42 | fastembed library | Sparse embeddings |
| Postgres schema | `docker/postgres/init/02-cocoindex.sql` | Extended, not replaced |

### Verification Commands

```bash
# Setup
docker exec -i dev-postgres psql -U postgres < docker/postgres/init/03-unified-ingestion-alter.sql
uv run python scripts/setup_scalar_collection.py --source gdrive_documents --force

# Tests
uv run pytest tests/unit/ingestion/test_payload_contract.py -v
RUN_INTEGRATION_TESTS=1 uv run pytest tests/integration/test_unified_ingestion_e2e.py -v

# Run
make ingest-unified-status
make ingest-unified
make ingest-unified-watch

# Docker
docker compose -f docker-compose.dev.yml up -d ingestion
docker logs dev-ingestion -f
```

### Acceptance Criteria

- [ ] `page_content` + `metadata.doc_id/order/source/file_id` in all points
- [ ] `point_id` stable for same file_id + chunk_location
- [ ] Add file → points appear with correct payload
- [ ] Modify file → points replaced (no duplicates)
- [ ] Delete file → points removed
- [ ] Docling error → DLQ entry, pipeline continues
- [ ] `make ingest-unified-status` shows stats
