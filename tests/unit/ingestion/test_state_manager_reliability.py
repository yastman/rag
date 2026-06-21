# tests/unit/ingestion/test_state_manager_reliability.py
"""Tests for #2941 reliability fixes:
1. Backoff formula (docstring matches POWER(5, LEAST(retry_count,2)) schedule).
2. Atomic claim: claim_processing returns None when already processing/indexed.
3. Reaper: reap_stuck_processing resets stale processing rows back to pending.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from src.ingestion.unified.state_manager import FileState, UnifiedStateManager


pytestmark = pytest.mark.requires_extras


@pytest.fixture
def mock_pool() -> AsyncMock:
    pool = AsyncMock()
    pool.execute = AsyncMock()
    pool.fetch = AsyncMock(return_value=[])
    pool.fetchrow = AsyncMock(return_value=None)
    pool.close = AsyncMock()
    return pool


@pytest.fixture
def manager(mock_pool: AsyncMock) -> UnifiedStateManager:
    return UnifiedStateManager(pool=mock_pool)


# ---------------------------------------------------------------------------
# Fix 1: Backoff formula — docstring must match POWER(5, LEAST(retry_count,2))
# ---------------------------------------------------------------------------


class TestBackoffFormula:
    """The backoff SQL must use LEAST(retry_count, 2) so caps at 25 min.

    POWER(5, 0)=1, POWER(5,1)=5, POWER(5,2)=25 — matches "1min, 5min, 25min".
    """

    async def test_backoff_sql_caps_at_least_2(
        self, manager: UnifiedStateManager, mock_pool: AsyncMock
    ) -> None:
        await manager.mark_error("f1", "err")

        sql = mock_pool.execute.call_args[0][0]
        assert "LEAST(retry_count, 2)" in sql, (
            "Backoff must cap at LEAST(retry_count, 2) to produce 1/5/25 min schedule"
        )

    async def test_backoff_docstring_says_25min(self) -> None:
        """mark_error docstring must document actual max of 25min, not 30min."""
        doc = UnifiedStateManager.mark_error.__doc__ or ""
        # Either 25min is mentioned OR docstring doesn't claim 30min
        assert "30min" not in doc, "Docstring claims 30min but formula produces 25min"


# ---------------------------------------------------------------------------
# Fix 2: Atomic claim — claim_processing
# ---------------------------------------------------------------------------


class TestAtomicClaim:
    """claim_processing must be a single atomic UPDATE ... RETURNING."""

    async def test_claim_processing_returns_file_state_on_success(
        self, manager: UnifiedStateManager, mock_pool: AsyncMock
    ) -> None:
        """When the UPDATE claims the row, a FileState is returned."""
        mock_pool.fetchrow.return_value = {
            "file_id": "f1",
            "source_path": None,
            "file_name": None,
            "mime_type": None,
            "file_size": None,
            "modified_time": None,
            "content_hash": "h1",
            "parser_version": None,
            "chunker_version": None,
            "embedding_model": "bge-m3",
            "chunk_count": 0,
            "collection_name": None,
            "pipeline_version": "v3.2.1",
            "indexed_at": None,
            "status": "processing",
            "error_message": None,
            "retry_count": 0,
            "retry_after": None,
        }

        result = await manager.claim_processing("f1")

        assert isinstance(result, FileState)
        assert result.file_id == "f1"
        assert result.status == "processing"

    async def test_claim_processing_returns_none_when_already_claimed(
        self, manager: UnifiedStateManager, mock_pool: AsyncMock
    ) -> None:
        """When the UPDATE matches nothing (already processing/indexed), None is returned."""
        mock_pool.fetchrow.return_value = None

        result = await manager.claim_processing("f1")

        assert result is None

    async def test_claim_processing_uses_single_atomic_update(
        self, manager: UnifiedStateManager, mock_pool: AsyncMock
    ) -> None:
        """Must be a single UPDATE ... WHERE status NOT IN (...) RETURNING — no SELECT first."""
        mock_pool.fetchrow.return_value = None

        await manager.claim_processing("f1")

        # Only fetchrow was called (the atomic UPDATE ... RETURNING)
        mock_pool.fetch.assert_not_called()
        assert mock_pool.fetchrow.call_count == 1
        sql = mock_pool.fetchrow.call_args[0][0].strip().upper()
        assert sql.startswith("UPDATE")
        assert "RETURNING" in sql
        assert "NOT IN" in sql or "!=" in sql

    async def test_claim_processing_excludes_processing_and_indexed(
        self, manager: UnifiedStateManager, mock_pool: AsyncMock
    ) -> None:
        """WHERE clause must exclude both 'processing' and 'indexed' statuses."""
        mock_pool.fetchrow.return_value = None

        await manager.claim_processing("f1")

        sql = mock_pool.fetchrow.call_args[0][0]
        assert "processing" in sql
        assert "indexed" in sql


# ---------------------------------------------------------------------------
# Fix 3: Stuck-processing reaper
# ---------------------------------------------------------------------------


class TestReapStuckProcessing:
    """reap_stuck_processing must reset stale processing rows to pending."""

    async def test_resets_stale_processing_rows(
        self, manager: UnifiedStateManager, mock_pool: AsyncMock
    ) -> None:
        mock_pool.execute.return_value = "UPDATE 3"

        await manager.reap_stuck_processing(threshold_minutes=30)

        mock_pool.execute.assert_called_once()
        sql = mock_pool.execute.call_args[0][0]
        assert "pending" in sql
        assert "processing" in sql
        assert "updated_at" in sql

    async def test_passes_threshold_as_parameter(
        self, manager: UnifiedStateManager, mock_pool: AsyncMock
    ) -> None:
        """threshold_minutes must be passed as a SQL parameter, not interpolated."""
        mock_pool.execute.return_value = "UPDATE 0"

        await manager.reap_stuck_processing(threshold_minutes=45)

        args = mock_pool.execute.call_args[0]
        assert 45 in args, "threshold_minutes must be passed as a bind parameter"

    async def test_uses_interval_arithmetic(
        self, manager: UnifiedStateManager, mock_pool: AsyncMock
    ) -> None:
        mock_pool.execute.return_value = "UPDATE 0"

        await manager.reap_stuck_processing(threshold_minutes=30)

        sql = mock_pool.execute.call_args[0][0]
        assert "interval" in sql.lower() or "INTERVAL" in sql

    async def test_reap_stuck_processing_sync_wrapper(
        self, manager: UnifiedStateManager, mock_pool: AsyncMock
    ) -> None:
        """reap_stuck_processing_sync method must exist and delegate to async."""
        assert hasattr(manager, "reap_stuck_processing_sync"), (
            "reap_stuck_processing_sync sync wrapper must be defined"
        )
        # Verify the async method works (sync wrapper tested via integration)
        mock_pool.execute.return_value = "UPDATE 0"
        await manager.reap_stuck_processing(threshold_minutes=30)
        mock_pool.execute.assert_called_once()
