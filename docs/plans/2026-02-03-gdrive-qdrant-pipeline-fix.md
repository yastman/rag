# GDrive → Qdrant Pipeline Fix Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Fix all P0 blockers and add P1 improvements to make the unified ingestion pipeline production-ready.

**Architecture:** CocoIndex orchestrates file changes, custom target connector handles Docling→Voyage→Qdrant with sync execution model to avoid event loop conflicts.

**Tech Stack:** CocoIndex 0.3.28, Voyage AI, FastEmbed BM42, Qdrant, Postgres, asyncpg

---

## Summary

| Task | Description | Priority |
|------|-------------|----------|
| 1 | P0.3: Verify cocoindex.init() with database settings | P0 |
| 2 | P0.5: Refactor mutate() to use sync execution | P0 |
| 3 | P1.1: Add --verify-only mode to collection scripts | P1 |
| 4 | P1.2: Add structured logging with metrics | P1 |
| 5 | Integration test and validation | P0 |

---

## Task 1: Verify cocoindex.init() with database settings

**Files:**
- Test: `tests/unit/ingestion/test_cocoindex_init.py`
- Verify: `src/ingestion/unified/flow.py:93-98`

**Step 1: Write test for cocoindex.init()**

```python
# tests/unit/ingestion/test_cocoindex_init.py
"""Tests for CocoIndex initialization."""

import os
import pytest
from unittest.mock import patch, MagicMock


class TestCocoIndexInit:
    """Test CocoIndex initialization with database settings."""

    def test_init_uses_config_database_url(self):
        """Verify init() receives database URL from config."""
        from src.ingestion.unified.config import UnifiedConfig

        config = UnifiedConfig(
            database_url="postgresql://test:test@localhost:5432/testdb"
        )

        assert config.database_url == "postgresql://test:test@localhost:5432/testdb"

    def test_app_namespace_normalization(self):
        """Verify app_namespace is normalized correctly."""
        from src.ingestion.unified.flow import _app_namespace_for
        from src.ingestion.unified.config import UnifiedConfig

        # Normal case
        config = UnifiedConfig(collection_name="gdrive_documents_scalar")
        ns = _app_namespace_for(config)
        assert ns == "unified__gdrive_documents_scalar"

        # With special characters
        config = UnifiedConfig(collection_name="my-collection.v2")
        ns = _app_namespace_for(config)
        assert ns == "unified__my_collection_v2"
        assert ns[0].isalpha() or ns[0] == "_"

        # Starting with number
        config = UnifiedConfig(collection_name="123_collection")
        ns = _app_namespace_for(config)
        assert ns[0] == "_"  # Should be prefixed

    @patch("cocoindex.init")
    def test_build_flow_calls_init_with_settings(self, mock_init):
        """Verify build_flow calls cocoindex.init with correct settings."""
        from src.ingestion.unified.config import UnifiedConfig

        config = UnifiedConfig(
            database_url="postgresql://test:test@localhost:5432/cocoindex",
            collection_name="test_collection",
        )

        # Mock the rest of CocoIndex
        with patch("cocoindex.flow_names", return_value=[]):
            with patch("cocoindex.open_flow"):
                from src.ingestion.unified.flow import build_flow

                try:
                    build_flow(config)
                except Exception:
                    pass  # Expected - mocked cocoindex

        # Verify init was called
        assert mock_init.called
        call_args = mock_init.call_args
        settings = call_args[0][0]

        # Check settings structure
        assert hasattr(settings, "database")
        assert hasattr(settings, "app_namespace")
```

**Step 2: Run test**

```bash
uv run pytest tests/unit/ingestion/test_cocoindex_init.py -v
```

Expected: All tests PASS.

**Step 3: Verify with real CocoIndex (manual)**

```bash
# Start Postgres
docker compose -f docker-compose.dev.yml up -d postgres

# Run minimal init test
uv run python -c "
from src.ingestion.unified.config import UnifiedConfig
from src.ingestion.unified.flow import build_flow
import cocoindex

config = UnifiedConfig()
print(f'Database URL: {config.database_url}')

# This should not raise 'Database is required' error
flow = build_flow(config)
print('SUCCESS: cocoindex.init() worked')
flow.close()
"
```

Expected: "SUCCESS: cocoindex.init() worked"

**Step 4: Commit**

```bash
git add tests/unit/ingestion/test_cocoindex_init.py
git commit -m "test(ingestion): add CocoIndex init verification tests

- Verify database URL passed from config
- Test app_namespace normalization
- Mock test for build_flow init call"
```

---

## Task 2: Refactor mutate() to use sync execution

**Problem:** `asyncio.run()` inside `mutate()` creates new event loops per mutation, causing conflicts.

**Solution:** Use sync clients throughout mutate(), leverage `loop.run_until_complete()` with a shared loop created in `prepare()`.

**Files:**
- Modify: `src/ingestion/unified/targets/qdrant_hybrid_target.py`
- Modify: `src/ingestion/unified/qdrant_writer.py`
- Create: `tests/unit/ingestion/test_target_sync_execution.py`

### Step 1: Write failing test for sync execution

```python
# tests/unit/ingestion/test_target_sync_execution.py
"""Tests for sync execution in target connector."""

import pytest
from unittest.mock import MagicMock, patch, AsyncMock
import asyncio


class TestTargetSyncExecution:
    """Test that mutate() works without asyncio.run() conflicts."""

    def test_mutate_does_not_call_asyncio_run(self):
        """mutate() should not use asyncio.run() directly."""
        import inspect
        from src.ingestion.unified.targets.qdrant_hybrid_target import (
            QdrantHybridTargetConnector,
        )

        source = inspect.getsource(QdrantHybridTargetConnector.mutate)
        assert "asyncio.run(" not in source, "mutate() should not use asyncio.run()"

    def test_handle_methods_are_sync(self):
        """_handle_delete and _handle_upsert should be sync methods."""
        from src.ingestion.unified.targets.qdrant_hybrid_target import (
            QdrantHybridTargetConnector,
        )

        # After refactor, these should not be async
        assert not asyncio.iscoroutinefunction(
            QdrantHybridTargetConnector._handle_delete
        ), "_handle_delete should be sync"
        assert not asyncio.iscoroutinefunction(
            QdrantHybridTargetConnector._handle_upsert
        ), "_handle_upsert should be sync"

    def test_writer_has_sync_methods(self):
        """QdrantHybridWriter should have sync methods."""
        from src.ingestion.unified.qdrant_writer import QdrantHybridWriter

        # Check method exists (will be added)
        assert hasattr(QdrantHybridWriter, "delete_file_sync")
        assert hasattr(QdrantHybridWriter, "upsert_chunks_sync")
```

**Step 2: Run test to verify it fails**

```bash
uv run pytest tests/unit/ingestion/test_target_sync_execution.py -v
```

Expected: FAIL (asyncio.run still in code, no sync methods)

### Step 3: Add sync methods to QdrantHybridWriter

Modify `src/ingestion/unified/qdrant_writer.py` - add sync versions:

```python
# Add after line 259 in qdrant_writer.py

    def delete_file_sync(self, file_id: str, collection_name: str) -> int:
        """Sync version of delete_file."""
        # Qdrant client is already sync
        count_result = self.client.count(
            collection_name=collection_name,
            count_filter=Filter(
                must=[FieldCondition(key="metadata.file_id", match=MatchValue(value=file_id))]
            ),
        )
        count = count_result.count

        if count > 0:
            self.client.delete(
                collection_name=collection_name,
                points_selector=Filter(
                    must=[FieldCondition(key="metadata.file_id", match=MatchValue(value=file_id))]
                ),
            )
            logger.info(f"Deleted {count} points for file_id={file_id}")

        return count

    def upsert_chunks_sync(
        self,
        chunks: list[Any],
        file_id: str,
        source_path: str,
        file_metadata: dict[str, Any],
        collection_name: str,
    ) -> WriteStats:
        """Sync version of upsert_chunks.

        Uses sync Voyage client and sync Qdrant operations.
        """
        stats = WriteStats()

        if not chunks:
            return stats

        try:
            # Step 1: Delete existing (replace semantics)
            stats.points_deleted = self.delete_file_sync(file_id, collection_name)

            # Step 2: Extract texts
            texts = [chunk.text for chunk in chunks]

            # Step 3: Generate embeddings (sync)
            dense_embeddings = self.voyage.embed_documents_sync(texts)
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

            # Step 5: Upsert (sync)
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

### Step 4: Refactor target connector to use sync execution

Replace the mutate method in `src/ingestion/unified/targets/qdrant_hybrid_target.py`:

```python
# Replace mutate() and helper methods (lines 176-295)

    @staticmethod
    def mutate(
        *all_mutations: tuple[QdrantHybridTargetSpec, dict[str, QdrantHybridTargetValues | None]],
    ) -> None:
        """Apply data mutations to Qdrant.

        Uses sync execution to avoid event loop conflicts.
        For each file_id:
        - None value: delete all points for file_id
        - Non-None value: parse, embed, upsert (replace semantics)
        """
        for spec, mutations in all_mutations:
            for file_id, mutation in mutations.items():
                try:
                    if mutation is None:
                        QdrantHybridTargetConnector._handle_delete(spec, file_id)
                    else:
                        QdrantHybridTargetConnector._handle_upsert(spec, file_id, mutation)
                except Exception as e:
                    logger.error(f"Mutation failed for {file_id}: {e}", exc_info=True)

    @classmethod
    def _handle_delete(cls, spec: QdrantHybridTargetSpec, file_id: str) -> None:
        """Handle file deletion (sync)."""
        writer = cls._get_writer(spec)
        state_manager = cls._get_state_manager(spec)

        writer.delete_file_sync(file_id, spec.collection_name)

        # State manager needs sync - use a simple approach
        import asyncio
        loop = asyncio.new_event_loop()
        try:
            loop.run_until_complete(state_manager.mark_deleted(file_id))
        finally:
            loop.close()

        logger.info(f"Deleted: file_id={file_id}")

    @classmethod
    def _handle_upsert(
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

        # Compute content hash
        content_hash = compute_content_hash(abs_path)

        # State operations need async handling
        import asyncio
        loop = asyncio.new_event_loop()

        try:
            # Check if processing needed (skip unchanged)
            should_process = loop.run_until_complete(
                state_manager.should_process(file_id, content_hash)
            )
            if not should_process:
                logger.debug(f"Skipping unchanged: {source_path}")
                return

            # Mark processing
            loop.run_until_complete(state_manager.mark_processing(file_id))

            # Connect docling if needed (async)
            if not docling._client:
                loop.run_until_complete(docling.connect())

            # Parse and chunk (async)
            docling_chunks = loop.run_until_complete(docling.chunk_file(abs_path))
            if not docling_chunks:
                loop.run_until_complete(
                    state_manager.mark_indexed(file_id, 0, content_hash)
                )
                logger.warning(f"No chunks from: {source_path}")
                return

            # Convert to ingestion chunks
            chunks = docling.to_ingestion_chunks(
                docling_chunks,
                source=source_path,
                source_type=abs_path.suffix.lstrip("."),
            )

            # File metadata
            file_metadata = {
                "file_name": mutation.file_name,
                "mime_type": mutation.mime_type,
                "file_size": mutation.file_size,
                "content_hash": content_hash,
                "modified_time": datetime.now(UTC).isoformat(),
            }

            # Write to Qdrant (sync)
            stats = writer.upsert_chunks_sync(
                chunks=chunks,
                file_id=file_id,
                source_path=source_path,
                file_metadata=file_metadata,
                collection_name=spec.collection_name,
            )

            if stats.errors:
                raise Exception("; ".join(stats.errors))

            # Update state
            loop.run_until_complete(
                state_manager.mark_indexed(file_id, stats.points_upserted, content_hash)
            )
            logger.info(f"Indexed: {source_path} ({stats.points_upserted} chunks)")

        except Exception as e:
            logger.error(f"Upsert failed for {source_path}: {e}")
            loop.run_until_complete(state_manager.mark_error(file_id, str(e)))

            # Check DLQ
            state = loop.run_until_complete(state_manager.get_state(file_id))
            if state and state.retry_count >= spec.max_retries:
                loop.run_until_complete(
                    state_manager.add_to_dlq(
                        file_id=file_id,
                        error_type=type(e).__name__,
                        error_message=str(e),
                        payload={"source_path": source_path},
                    )
                )
                logger.warning(f"Moved to DLQ: {source_path}")

            raise
        finally:
            loop.close()
```

### Step 5: Run tests to verify fix

```bash
uv run pytest tests/unit/ingestion/test_target_sync_execution.py -v
```

Expected: All tests PASS.

### Step 6: Run existing tests to ensure no regression

```bash
uv run pytest tests/unit/ingestion/ -v
```

Expected: All tests PASS.

### Step 7: Commit

```bash
git add src/ingestion/unified/targets/qdrant_hybrid_target.py src/ingestion/unified/qdrant_writer.py tests/unit/ingestion/test_target_sync_execution.py
git commit -m "fix(ingestion): refactor mutate() to use sync execution

P0.5 fix: Remove asyncio.run() from mutate() to prevent event loop conflicts.

- Add sync methods to QdrantHybridWriter (delete_file_sync, upsert_chunks_sync)
- Use dedicated event loop per mutation for async state/docling operations
- Properly close loop after each mutation
- Add tests verifying sync execution pattern"
```

---

## Task 3: Add --verify-only mode to collection scripts

**Files:**
- Modify: `scripts/setup_scalar_collection.py`
- Modify: `scripts/setup_binary_collection.py`
- Test: `tests/unit/test_collection_verify.py`

### Step 1: Write test for verify mode

```python
# tests/unit/test_collection_verify.py
"""Tests for collection verification mode."""

import pytest
from unittest.mock import MagicMock, patch


class TestCollectionVerify:
    """Test --verify-only mode."""

    def test_verify_returns_missing_indexes(self):
        """verify_collection should return list of missing indexes."""
        from scripts.setup_scalar_collection import verify_collection_indexes

        # Mock client with partial indexes
        mock_client = MagicMock()
        mock_info = MagicMock()
        mock_info.payload_schema = {
            "file_id": {"data_type": "keyword"},
            # Missing: metadata.file_id, metadata.doc_id, metadata.order, etc.
        }
        mock_client.get_collection.return_value = mock_info

        missing = verify_collection_indexes(mock_client, "test_collection")

        assert "metadata.file_id" in missing
        assert "metadata.doc_id" in missing
        assert "metadata.order" in missing

    def test_verify_returns_empty_when_complete(self):
        """verify_collection should return empty list when all indexes present."""
        from scripts.setup_scalar_collection import verify_collection_indexes

        mock_client = MagicMock()
        mock_info = MagicMock()
        mock_info.payload_schema = {
            "file_id": {"data_type": "keyword"},
            "metadata.file_id": {"data_type": "keyword"},
            "metadata.doc_id": {"data_type": "keyword"},
            "metadata.source": {"data_type": "keyword"},
            "metadata.order": {"data_type": "integer"},
            "metadata.chunk_order": {"data_type": "integer"},
        }
        mock_client.get_collection.return_value = mock_info

        missing = verify_collection_indexes(mock_client, "test_collection")

        assert missing == []
```

### Step 2: Add verify function to setup_scalar_collection.py

Add after `create_payload_indexes()` function (around line 225):

```python
def verify_collection_indexes(client: QdrantClient, collection_name: str) -> list[str]:
    """Verify required payload indexes exist.

    Returns:
        List of missing index names (empty if all present)
    """
    required_indexes = {
        # Keyword indexes (required for unified ingestion)
        "file_id": "keyword",
        "metadata.file_id": "keyword",
        "metadata.doc_id": "keyword",
        "metadata.source": "keyword",
        # Integer indexes (required for small-to-big)
        "metadata.order": "integer",
        "metadata.chunk_order": "integer",
    }

    try:
        info = client.get_collection(collection_name)
        existing = info.payload_schema or {}

        missing = []
        for field, expected_type in required_indexes.items():
            if field not in existing:
                missing.append(field)
            else:
                # Check type matches
                actual_type = existing[field].get("data_type", "unknown")
                if actual_type != expected_type:
                    missing.append(f"{field} (wrong type: {actual_type}, expected: {expected_type})")

        return missing

    except Exception as e:
        return [f"Error checking collection: {e}"]


def verify_only(source_collection: str) -> bool:
    """Verify collection has required indexes without modifying.

    Returns:
        True if all required indexes present, False otherwise
    """
    try:
        client = get_qdrant_client()
        scalar_collection = get_scalar_collection_name(source_collection)

        if not collection_exists(client, scalar_collection):
            print(f"Collection '{scalar_collection}' does not exist.")
            return False

        missing = verify_collection_indexes(client, scalar_collection)

        if missing:
            print(f"Collection '{scalar_collection}' is MISSING required indexes:")
            for field in missing:
                print(f"  - {field}")
            print("\nRun without --verify-only to add missing indexes.")
            return False

        print(f"Collection '{scalar_collection}' has all required indexes.")
        print_collection_info(client, scalar_collection)
        return True

    except Exception as e:
        print(f"Error during verification: {e}")
        return False
```

### Step 3: Add --verify-only argument to main()

Modify the argparse section in `main()`:

```python
    parser.add_argument(
        "--verify-only",
        "-v",
        action="store_true",
        help="Only verify required indexes exist, don't modify collection",
    )

    # ... existing args ...

    args = parser.parse_args()

    # Handle verify-only mode
    if args.verify_only:
        print("\n" + "=" * 60)
        print("Qdrant Collection Verification")
        print("=" * 60 + "\n")
        success = verify_only(args.source)
        return 0 if success else 1

    # ... rest of main() ...
```

### Step 4: Run tests

```bash
uv run pytest tests/unit/test_collection_verify.py -v
```

Expected: All tests PASS.

### Step 5: Test manually

```bash
# Verify existing collection
uv run python scripts/setup_scalar_collection.py --source gdrive_documents --verify-only

# Should show missing indexes or success
```

### Step 6: Apply same changes to setup_binary_collection.py

Copy the `verify_collection_indexes()` and `verify_only()` functions, update argparse.

### Step 7: Commit

```bash
git add scripts/setup_scalar_collection.py scripts/setup_binary_collection.py tests/unit/test_collection_verify.py
git commit -m "feat(scripts): add --verify-only mode to collection setup

P1.1: Verify required payload indexes without modifying collection.

Required indexes:
- Keyword: file_id, metadata.file_id, metadata.doc_id, metadata.source
- Integer: metadata.order, metadata.chunk_order

Usage: python scripts/setup_scalar_collection.py --verify-only"
```

---

## Task 4: Add structured logging with metrics

**Files:**
- Modify: `src/ingestion/unified/targets/qdrant_hybrid_target.py`
- Create: `src/ingestion/unified/metrics.py`

### Step 1: Create metrics module

```python
# src/ingestion/unified/metrics.py
"""Structured metrics logging for unified ingestion pipeline."""

import logging
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, UTC
from typing import Any


logger = logging.getLogger(__name__)


@dataclass
class IngestionMetrics:
    """Metrics for a single file ingestion."""

    file_id: str
    source_path: str
    started_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    # Timing
    docling_duration_ms: float = 0
    voyage_duration_ms: float = 0
    qdrant_duration_ms: float = 0
    total_duration_ms: float = 0

    # Counts
    chunks_created: int = 0
    chunks_deleted: int = 0

    # Status
    status: str = "pending"  # pending, success, error, skipped
    error_message: str | None = None

    def to_structured_log(self) -> dict[str, Any]:
        """Convert to structured log dict."""
        return {
            "event": "ingestion_file",
            "file_id": self.file_id,
            "source_path": self.source_path,
            "status": self.status,
            "chunks_created": self.chunks_created,
            "chunks_deleted": self.chunks_deleted,
            "docling_ms": round(self.docling_duration_ms, 1),
            "voyage_ms": round(self.voyage_duration_ms, 1),
            "qdrant_ms": round(self.qdrant_duration_ms, 1),
            "total_ms": round(self.total_duration_ms, 1),
            "error": self.error_message,
            "timestamp": self.started_at.isoformat(),
        }


@contextmanager
def timed_operation(metrics: IngestionMetrics, operation: str):
    """Context manager to time an operation and store in metrics.

    Args:
        metrics: IngestionMetrics instance to update
        operation: One of 'docling', 'voyage', 'qdrant'

    Usage:
        with timed_operation(metrics, 'docling'):
            chunks = await docling.chunk_file(path)
    """
    start = time.perf_counter()
    try:
        yield
    finally:
        duration_ms = (time.perf_counter() - start) * 1000
        attr = f"{operation}_duration_ms"
        if hasattr(metrics, attr):
            setattr(metrics, attr, duration_ms)


def log_ingestion_result(metrics: IngestionMetrics) -> None:
    """Log ingestion result as structured JSON."""
    log_data = metrics.to_structured_log()

    if metrics.status == "success":
        logger.info(
            f"Ingested {metrics.source_path}: {metrics.chunks_created} chunks "
            f"(docling={metrics.docling_duration_ms:.0f}ms, "
            f"voyage={metrics.voyage_duration_ms:.0f}ms, "
            f"qdrant={metrics.qdrant_duration_ms:.0f}ms)",
            extra={"structured": log_data},
        )
    elif metrics.status == "skipped":
        logger.debug(
            f"Skipped unchanged: {metrics.source_path}",
            extra={"structured": log_data},
        )
    elif metrics.status == "error":
        logger.error(
            f"Failed {metrics.source_path}: {metrics.error_message}",
            extra={"structured": log_data},
        )


def log_batch_summary(
    processed: int,
    skipped: int,
    failed: int,
    deleted: int,
    total_duration_ms: float,
) -> None:
    """Log batch summary."""
    logger.info(
        f"Batch complete: processed={processed}, skipped={skipped}, "
        f"failed={failed}, deleted={deleted}, duration={total_duration_ms:.0f}ms",
        extra={
            "structured": {
                "event": "ingestion_batch",
                "processed": processed,
                "skipped": skipped,
                "failed": failed,
                "deleted": deleted,
                "total_ms": round(total_duration_ms, 1),
                "timestamp": datetime.now(UTC).isoformat(),
            }
        },
    )
```

### Step 2: Integrate metrics into target connector

Update `_handle_upsert` in `qdrant_hybrid_target.py` to use metrics:

```python
# Add import at top
from src.ingestion.unified.metrics import (
    IngestionMetrics,
    timed_operation,
    log_ingestion_result,
)

# Update _handle_upsert to use metrics
@classmethod
def _handle_upsert(
    cls,
    spec: QdrantHybridTargetSpec,
    file_id: str,
    mutation: QdrantHybridTargetValues,
) -> None:
    """Handle file insert/update (sync) with metrics."""
    import time

    metrics = IngestionMetrics(
        file_id=file_id,
        source_path=mutation.source_path,
    )
    start_time = time.perf_counter()

    writer = cls._get_writer(spec)
    docling = cls._get_docling(spec)
    state_manager = cls._get_state_manager(spec)

    abs_path = Path(mutation.abs_path)
    source_path = mutation.source_path
    content_hash = compute_content_hash(abs_path)

    import asyncio
    loop = asyncio.new_event_loop()

    try:
        # Check if processing needed
        should_process = loop.run_until_complete(
            state_manager.should_process(file_id, content_hash)
        )
        if not should_process:
            metrics.status = "skipped"
            log_ingestion_result(metrics)
            return

        loop.run_until_complete(state_manager.mark_processing(file_id))

        # Docling - timed
        docling_start = time.perf_counter()
        if not docling._client:
            loop.run_until_complete(docling.connect())
        docling_chunks = loop.run_until_complete(docling.chunk_file(abs_path))
        metrics.docling_duration_ms = (time.perf_counter() - docling_start) * 1000

        if not docling_chunks:
            loop.run_until_complete(
                state_manager.mark_indexed(file_id, 0, content_hash)
            )
            metrics.status = "success"
            metrics.chunks_created = 0
            log_ingestion_result(metrics)
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

        # Voyage + Qdrant - timed together in upsert_chunks_sync
        qdrant_start = time.perf_counter()
        stats = writer.upsert_chunks_sync(
            chunks=chunks,
            file_id=file_id,
            source_path=source_path,
            file_metadata=file_metadata,
            collection_name=spec.collection_name,
        )
        metrics.qdrant_duration_ms = (time.perf_counter() - qdrant_start) * 1000

        if stats.errors:
            raise Exception("; ".join(stats.errors))

        loop.run_until_complete(
            state_manager.mark_indexed(file_id, stats.points_upserted, content_hash)
        )

        metrics.status = "success"
        metrics.chunks_created = stats.points_upserted
        metrics.chunks_deleted = stats.points_deleted

    except Exception as e:
        metrics.status = "error"
        metrics.error_message = str(e)[:500]
        loop.run_until_complete(state_manager.mark_error(file_id, str(e)))

        state = loop.run_until_complete(state_manager.get_state(file_id))
        if state and state.retry_count >= spec.max_retries:
            loop.run_until_complete(
                state_manager.add_to_dlq(
                    file_id=file_id,
                    error_type=type(e).__name__,
                    error_message=str(e),
                    payload={"source_path": source_path},
                )
            )
        raise
    finally:
        loop.close()
        metrics.total_duration_ms = (time.perf_counter() - start_time) * 1000
        log_ingestion_result(metrics)
```

### Step 3: Test metrics

```bash
# Unit test
uv run python -c "
from src.ingestion.unified.metrics import IngestionMetrics, log_ingestion_result

m = IngestionMetrics(file_id='abc123', source_path='docs/test.pdf')
m.status = 'success'
m.chunks_created = 5
m.docling_duration_ms = 1200
m.voyage_duration_ms = 800
m.qdrant_duration_ms = 150
m.total_duration_ms = 2200

log_ingestion_result(m)
print('Metrics OK')
"
```

### Step 4: Commit

```bash
git add src/ingestion/unified/metrics.py src/ingestion/unified/targets/qdrant_hybrid_target.py
git commit -m "feat(ingestion): add structured metrics logging

P1.2: Track per-file ingestion metrics:
- Timing: docling, voyage, qdrant durations
- Counts: chunks created/deleted
- Status: success/skipped/error
- Structured JSON for Loki parsing"
```

---

## Task 5: Integration test and validation

**Files:**
- Test: `tests/integration/test_unified_ingestion_e2e.py` (existing)

### Step 1: Run existing E2E tests

```bash
# Start services
docker compose -f docker-compose.dev.yml up -d postgres qdrant docling

# Wait for services
sleep 10

# Run E2E tests
RUN_INTEGRATION_TESTS=1 uv run pytest tests/integration/test_unified_ingestion_e2e.py -v
```

Expected: All tests PASS.

### Step 2: Manual validation - single file

```bash
# Create test directory
mkdir -p /tmp/test-sync
echo "# Test Document

This is a test document for ingestion.

## Section 1

Content of section 1.

## Section 2

Content of section 2." > /tmp/test-sync/test.md

# Run ingestion
GDRIVE_SYNC_DIR=/tmp/test-sync \
GDRIVE_COLLECTION_NAME=test_manual_e2e \
uv run python -m src.ingestion.unified.cli run -v

# Check results
uv run python -c "
from qdrant_client import QdrantClient
import hashlib

client = QdrantClient(url='http://localhost:6333')
file_id = hashlib.sha256('test.md'.encode()).hexdigest()[:16]

results, _ = client.scroll(
    collection_name='test_manual_e2e',
    scroll_filter={'must': [{'key': 'metadata.file_id', 'match': {'value': file_id}}]},
    limit=10,
    with_payload=True,
)

print(f'Found {len(results)} points')
if results:
    print(f'Payload keys: {list(results[0].payload.keys())}')
    print(f'Metadata keys: {list(results[0].payload.get(\"metadata\", {}).keys())}')
"

# Cleanup
rm -rf /tmp/test-sync
```

### Step 3: Check status command

```bash
make ingest-unified-status
```

Expected: Shows stats from Postgres.

### Step 4: Final commit

```bash
git add -A
git commit -m "test(ingestion): validate unified pipeline fixes

Verified:
- P0.3: cocoindex.init() works with config.database_url
- P0.5: mutate() uses sync execution without asyncio.run() conflicts
- P1.1: --verify-only mode for collection scripts
- P1.2: Structured metrics logging

E2E tests passing, manual validation successful."
```

---

## Summary

### Files Created

| File | Purpose |
|------|---------|
| `tests/unit/ingestion/test_cocoindex_init.py` | P0.3 verification tests |
| `tests/unit/ingestion/test_target_sync_execution.py` | P0.5 sync execution tests |
| `tests/unit/test_collection_verify.py` | P1.1 verify mode tests |
| `src/ingestion/unified/metrics.py` | P1.2 structured metrics |

### Files Modified

| File | Change |
|------|--------|
| `src/ingestion/unified/qdrant_writer.py` | Add sync methods |
| `src/ingestion/unified/targets/qdrant_hybrid_target.py` | Refactor mutate() to sync, add metrics |
| `scripts/setup_scalar_collection.py` | Add --verify-only mode |
| `scripts/setup_binary_collection.py` | Add --verify-only mode |

### Verification Commands

```bash
# All unit tests
uv run pytest tests/unit/ingestion/ -v

# E2E tests
RUN_INTEGRATION_TESTS=1 uv run pytest tests/integration/test_unified_ingestion_e2e.py -v

# Manual run
make ingest-unified
make ingest-unified-status

# Verify collection
uv run python scripts/setup_scalar_collection.py --source gdrive_documents --verify-only
```

### Acceptance Criteria

- [ ] P0.3: `make ingest-unified` does not fail on init()
- [ ] P0.5: No `asyncio.run()` in mutate() source code
- [ ] P0.5: Watch mode runs stable for 10+ minutes
- [ ] P1.1: `--verify-only` returns missing indexes
- [ ] P1.2: Logs show structured metrics (docling_ms, voyage_ms, etc.)
- [ ] E2E tests passing
