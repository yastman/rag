# tests/unit/ingestion/test_state_manager_reliability.py
"""Tests for #2941 reliability fixes:
1. Backoff formula (docstring matches POWER(5, LEAST(retry_count,2)) schedule).
2. Atomic claim: claim_processing returns None when already processing/indexed.
3. Reaper: reap_stuck_processing resets stale processing rows back to pending.
"""

from __future__ import annotations

import asyncio
import inspect
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

    async def test_backoff_comment_documents_25min(self) -> None:
        """mark_error must document the real 25min cap (not 30min) in its source.

        The schedule comment lives inline in the function body, so checking
        __doc__ proved nothing (it is None). Inspect the actual source instead.
        """
        source = inspect.getsource(UnifiedStateManager.mark_error)
        assert "25min" in source, "backoff comment must document the real 25min cap"
        assert "30min" not in source, (
            "source claims 30min but POWER(5, LEAST(retry_count, 2)) caps at 25min"
        )

    async def test_backoff_schedule_values_are_1_5_25(
        self, manager: UnifiedStateManager, mock_pool: AsyncMock
    ) -> None:
        """The backoff SQL must encode the 1/5/25 minute schedule, not 30."""
        await manager.mark_error("f1", "err")
        sql = mock_pool.execute.call_args[0][0]
        assert "POWER(5, LEAST(retry_count, 2))" in sql
        assert "30" not in sql


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

    async def test_claim_processing_uses_single_atomic_insert_on_conflict(
        self, manager: UnifiedStateManager, mock_pool: AsyncMock
    ) -> None:
        """Must be a single INSERT ... ON CONFLICT DO UPDATE ... RETURNING — no SELECT first."""
        mock_pool.fetchrow.return_value = None

        await manager.claim_processing("f1")

        # Only fetchrow was called (the atomic INSERT ... ON CONFLICT ... RETURNING)
        mock_pool.fetch.assert_not_called()
        assert mock_pool.fetchrow.call_count == 1
        sql = mock_pool.fetchrow.call_args[0][0].strip().upper()
        assert sql.startswith("INSERT")
        assert "ON CONFLICT" in sql
        assert "RETURNING" in sql

    async def test_claim_processing_new_file_returns_file_state(
        self, manager: UnifiedStateManager, mock_pool: AsyncMock
    ) -> None:
        """New file (no existing row) → INSERT path → returns FileState with status=processing."""
        mock_pool.fetchrow.return_value = {
            "file_id": "new-file-1",
            "source_path": None,
            "file_name": None,
            "mime_type": None,
            "file_size": None,
            "modified_time": None,
            "content_hash": "h_new",
            "parser_version": None,
            "chunker_version": None,
            "embedding_model": "bge-m3",
            "chunk_count": 0,
            "collection_name": None,
            "pipeline_version": "v3",
            "indexed_at": None,
            "status": "processing",
            "error_message": None,
            "retry_count": 0,
            "retry_after": None,
        }

        result = await manager.claim_processing("new-file-1", "h_new", "bge-m3", "v3")

        # Must not be None — new files must be claimed on first call
        assert result is not None, "claim_processing must return FileState for new files, not None"
        assert isinstance(result, FileState)
        assert result.file_id == "new-file-1"
        assert result.status == "processing"

    async def test_claim_processing_excludes_processing_and_indexed(
        self, manager: UnifiedStateManager, mock_pool: AsyncMock
    ) -> None:
        """WHERE clause must exclude both 'processing' and 'indexed' statuses."""
        mock_pool.fetchrow.return_value = None

        await manager.claim_processing("f1")

        sql = mock_pool.fetchrow.call_args[0][0]
        assert "processing" in sql
        assert "indexed" in sql

    async def test_claim_processing_persists_metadata_on_insert(
        self, manager: UnifiedStateManager, mock_pool: AsyncMock
    ) -> None:
        """INSERT must persist file metadata so source_path is non-NULL after first claim.

        Regression for BLOCKER-2: upsert_state_sync (the previous metadata writer)
        was removed, so claim_processing is now the only first-touch writer. The
        metadata columns must be in the INSERT column list and passed as bind
        parameters — otherwise source_path/file_name/etc. stay NULL forever.
        """
        mock_pool.fetchrow.return_value = None

        await manager.claim_processing(
            "f1",
            content_hash="h1",
            embedding_model="bge-m3-api",
            pipeline_version="v3.2.1",
            source_path="docs/doc.txt",
            file_name="doc.txt",
            mime_type="text/plain",
            file_size=5,
            collection_name="col",
        )

        call = mock_pool.fetchrow.call_args
        sql = call[0][0]
        # Metadata columns present in the INSERT
        for col in ("source_path", "file_name", "mime_type", "file_size", "collection_name"):
            assert col in sql, f"INSERT must include {col} column"
        # Metadata values passed as bind parameters (non-NULL on first insert)
        bind_args = call[0][1:]
        assert "docs/doc.txt" in bind_args
        assert "doc.txt" in bind_args
        assert "text/plain" in bind_args
        assert "col" in bind_args

    async def test_claim_processing_does_not_overwrite_metadata_on_conflict(
        self, manager: UnifiedStateManager, mock_pool: AsyncMock
    ) -> None:
        """On re-claim (ON CONFLICT) only status/updated_at change — metadata stays.

        The DO UPDATE SET clause must NOT touch source_path/file_name/etc., so a
        re-claim of an existing row preserves the originally-persisted metadata.
        """
        mock_pool.fetchrow.return_value = None

        await manager.claim_processing("f1", source_path="docs/doc.txt")

        sql = mock_pool.fetchrow.call_args[0][0]
        # Isolate the DO UPDATE SET ... WHERE clause
        upper = sql.upper()
        set_start = upper.index("DO UPDATE")
        set_end = upper.index("WHERE", set_start)
        set_clause = sql[set_start:set_end]
        for col in ("source_path", "file_name", "mime_type", "file_size", "collection_name"):
            assert col not in set_clause, (
                f"{col} must not be in the conflict-update SET clause (metadata is insert-only)"
            )
        assert "status" in set_clause
        assert "updated_at" in set_clause


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


# ---------------------------------------------------------------------------
# Fix 3 (wiring): orchestrator must actually CALL the reaper each poll pass
# ---------------------------------------------------------------------------


class TestReaperWiredIntoOrchestrator:
    """BLOCKER-3: reap_stuck_processing must have a live caller in the loop."""

    async def test_run_watch_reaps_stuck_processing_each_pass(self) -> None:
        """run_watch must invoke the reaper with the configured threshold."""
        from src.ingestion.unified.orchestrator import UnifiedIngestionOrchestrator

        stop_event = asyncio.Event()

        async def _detect(_collection: str) -> list:
            # Stop after the first pass so the loop terminates.
            stop_event.set()
            return []

        change_manager = AsyncMock()
        change_manager.detect_changes = AsyncMock(side_effect=_detect)
        writer = AsyncMock()
        state_manager = AsyncMock()

        orchestrator = UnifiedIngestionOrchestrator(
            change_manager=change_manager,
            writer=writer,
            state_manager=state_manager,
        )

        await orchestrator.run_watch(
            "col",
            stop_event=stop_event,
            poll_interval=0,
            reap_threshold_minutes=30,
        )

        state_manager.reap_stuck_processing.assert_awaited_once_with(30)
