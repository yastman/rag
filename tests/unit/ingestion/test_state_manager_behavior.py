# tests/unit/ingestion/test_state_manager_behavior.py
"""Behavior tests for UnifiedStateManager sync methods.

Tests the actual business logic:
- should_process_sync: hash comparison, status checks, DLQ detection
- mark_indexed_sync: SQL structure, error field reset
- mark_error_sync: retry_count increment, exponential backoff formula, DLQ threshold
- State transitions: pending → indexed, error → retry → indexed, error → DLQ
- Edge cases: null hash, stale retry_after, sync_context pool reuse
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch

import pytest

from src.ingestion.unified.state_manager import UnifiedStateManager


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_pool():
    """Create a mock asyncpg pool for sync method testing."""
    pool = AsyncMock()
    pool.execute = AsyncMock()
    pool.fetch = AsyncMock(return_value=[])
    pool.fetchrow = AsyncMock(return_value=None)
    pool.close = AsyncMock()
    return pool


def _make_state_row(
    *,
    file_id: str = "f1",
    status: str = "indexed",
    content_hash: str | None = "hash1",
    retry_count: int = 0,
    retry_after: datetime | None = None,
    error_message: str | None = None,
) -> dict:
    """Return a dict matching asyncpg Record fields for ingestion_state."""
    return {
        "file_id": file_id,
        "source_path": None,
        "file_name": None,
        "mime_type": None,
        "file_size": None,
        "modified_time": None,
        "content_hash": content_hash,
        "parser_version": None,
        "chunker_version": None,
        "embedding_model": "bge-m3",
        "chunk_count": 5,
        "collection_name": None,
        "pipeline_version": "v3.2.1",
        "indexed_at": None,
        "status": status,
        "error_message": error_message,
        "retry_count": retry_count,
        "retry_after": retry_after,
    }


# ---------------------------------------------------------------------------
# SQL identifier hardening
# ---------------------------------------------------------------------------


class TestSqlIdentifierValidation:
    """Verify SQL table identifier validation guard."""

    def test_rejects_unsafe_identifier(self) -> None:
        with pytest.raises(ValueError, match="Unsafe SQL identifier"):
            UnifiedStateManager._safe_identifier("ingestion_state;DROP TABLE users")


# ---------------------------------------------------------------------------
# should_process_sync — hash comparison behavior
# ---------------------------------------------------------------------------


class TestShouldProcessSyncHashComparison:
    """Verify hash-based skip/process logic for should_process_sync."""

    def test_new_file_no_state_returns_true(self, mock_pool):
        """A file with no existing state (new file) must be processed."""
        mock_pool.fetchrow.return_value = None

        with patch("asyncpg.create_pool", new=AsyncMock(return_value=mock_pool)):
            mgr = UnifiedStateManager(database_url="postgres://localhost/test")
            result = mgr.should_process_sync("new_file", "hash1")

        assert result is True

    def test_indexed_file_same_hash_returns_false(self, mock_pool):
        """Indexed file with unchanged hash must be skipped."""
        mock_pool.fetchrow.return_value = _make_state_row(
            status="indexed", content_hash="same_hash"
        )

        with patch("asyncpg.create_pool", new=AsyncMock(return_value=mock_pool)):
            mgr = UnifiedStateManager(database_url="postgres://localhost/test")
            result = mgr.should_process_sync("f1", "same_hash")

        assert result is False

    def test_indexed_file_changed_hash_returns_true(self, mock_pool):
        """Indexed file whose content has changed must be reprocessed."""
        mock_pool.fetchrow.return_value = _make_state_row(status="indexed", content_hash="old_hash")

        with patch("asyncpg.create_pool", new=AsyncMock(return_value=mock_pool)):
            mgr = UnifiedStateManager(database_url="postgres://localhost/test")
            result = mgr.should_process_sync("f1", "new_hash")

        assert result is True

    def test_null_stored_hash_triggers_reprocessing(self, mock_pool):
        """If the stored hash is None, content is unknown — process the file."""
        mock_pool.fetchrow.return_value = _make_state_row(status="indexed", content_hash=None)

        with patch("asyncpg.create_pool", new=AsyncMock(return_value=mock_pool)):
            mgr = UnifiedStateManager(database_url="postgres://localhost/test")
            result = mgr.should_process_sync("f1", "some_hash")

        assert result is True


# ---------------------------------------------------------------------------
# should_process_sync — error/backoff/DLQ logic
# ---------------------------------------------------------------------------


class TestShouldProcessSyncBackoffAndDlq:
    """Verify error status, backoff, and DLQ behavior."""

    def test_error_with_future_retry_after_returns_false(self, mock_pool):
        """Error status in active backoff window must be skipped."""
        future = datetime.now(UTC) + timedelta(hours=1)
        mock_pool.fetchrow.return_value = _make_state_row(
            status="error",
            content_hash="h",
            retry_count=1,
            retry_after=future,
        )

        with patch("asyncpg.create_pool", new=AsyncMock(return_value=mock_pool)):
            mgr = UnifiedStateManager(database_url="postgres://localhost/test")
            result = mgr.should_process_sync("f1", "h")

        assert result is False

    def test_error_with_stale_retry_after_returns_true(self, mock_pool):
        """Error status with expired retry_after allows retry."""
        past = datetime.now(UTC) - timedelta(hours=1)
        mock_pool.fetchrow.return_value = _make_state_row(
            status="error",
            content_hash="h",
            retry_count=1,
            retry_after=past,
        )

        with patch("asyncpg.create_pool", new=AsyncMock(return_value=mock_pool)):
            mgr = UnifiedStateManager(database_url="postgres://localhost/test")
            result = mgr.should_process_sync("f1", "h")

        assert result is True

    def test_exceeded_max_retries_returns_false_dlq(self, mock_pool):
        """retry_count >= 3 means file is in DLQ — do not reprocess."""
        mock_pool.fetchrow.return_value = _make_state_row(
            status="error",
            content_hash="h",
            retry_count=3,
            retry_after=None,
        )

        with patch("asyncpg.create_pool", new=AsyncMock(return_value=mock_pool)):
            mgr = UnifiedStateManager(database_url="postgres://localhost/test")
            result = mgr.should_process_sync("f1", "h")

        assert result is False

    def test_retry_count_just_below_max_returns_true(self, mock_pool):
        """retry_count=2 is still below max (3) — can retry if backoff expired."""
        past = datetime.now(UTC) - timedelta(minutes=5)
        mock_pool.fetchrow.return_value = _make_state_row(
            status="error",
            content_hash="h",
            retry_count=2,
            retry_after=past,
        )

        with patch("asyncpg.create_pool", new=AsyncMock(return_value=mock_pool)):
            mgr = UnifiedStateManager(database_url="postgres://localhost/test")
            result = mgr.should_process_sync("f1", "h")

        assert result is True


# ---------------------------------------------------------------------------
# mark_indexed_sync — SQL structure and error field reset
# ---------------------------------------------------------------------------


class TestMarkIndexedSyncBehavior:
    """Verify mark_indexed_sync SQL and parameter behavior."""

    def test_executes_upsert_sql_with_on_conflict(self, mock_pool):
        """mark_indexed_sync uses INSERT ... ON CONFLICT semantics."""
        with patch("asyncpg.create_pool", new=AsyncMock(return_value=mock_pool)):
            mgr = UnifiedStateManager(database_url="postgres://localhost/test")
            mgr.mark_indexed_sync("file_001", chunk_count=15, content_hash="hash_abc")

        mock_pool.execute.assert_called_once()
        sql = mock_pool.execute.call_args[0][0]
        assert "ON CONFLICT" in sql
        assert "indexed" in sql

    def test_passes_file_id_chunk_count_content_hash(self, mock_pool):
        """Positional params: file_id at $1, chunk_count at $2, content_hash at $3."""
        with patch("asyncpg.create_pool", new=AsyncMock(return_value=mock_pool)):
            mgr = UnifiedStateManager(database_url="postgres://localhost/test")
            mgr.mark_indexed_sync("file_001", chunk_count=15, content_hash="hash_abc")

        args = mock_pool.execute.call_args[0]
        assert args[1] == "file_001"
        assert args[2] == 15
        assert args[3] == "hash_abc"

    def test_resets_error_message_to_null(self, mock_pool):
        """mark_indexed_sync must clear error_message after successful index."""
        with patch("asyncpg.create_pool", new=AsyncMock(return_value=mock_pool)):
            mgr = UnifiedStateManager(database_url="postgres://localhost/test")
            mgr.mark_indexed_sync("file_001", chunk_count=5, content_hash="h")

        sql = mock_pool.execute.call_args[0][0]
        assert "error_message = NULL" in sql

    def test_resets_retry_count_to_zero(self, mock_pool):
        """mark_indexed_sync must clear retry_count after successful index."""
        with patch("asyncpg.create_pool", new=AsyncMock(return_value=mock_pool)):
            mgr = UnifiedStateManager(database_url="postgres://localhost/test")
            mgr.mark_indexed_sync("file_001", chunk_count=5, content_hash="h")

        sql = mock_pool.execute.call_args[0][0]
        assert "retry_count = 0" in sql

    def test_resets_retry_after_to_null(self, mock_pool):
        """mark_indexed_sync must clear retry_after after successful index."""
        with patch("asyncpg.create_pool", new=AsyncMock(return_value=mock_pool)):
            mgr = UnifiedStateManager(database_url="postgres://localhost/test")
            mgr.mark_indexed_sync("file_001", chunk_count=5, content_hash="h")

        sql = mock_pool.execute.call_args[0][0]
        assert "retry_after = NULL" in sql


# ---------------------------------------------------------------------------
# mark_error_sync — DLQ / retry logic
# ---------------------------------------------------------------------------


class TestMarkErrorSyncBehavior:
    """Verify mark_error_sync SQL structure and DLQ transition behavior."""

    def test_increments_retry_count_in_sql(self, mock_pool):
        """mark_error uses SQL expression to increment retry_count atomically."""
        with patch("asyncpg.create_pool", new=AsyncMock(return_value=mock_pool)):
            mgr = UnifiedStateManager(database_url="postgres://localhost/test")
            mgr.mark_error_sync("file_002", "Connection timeout")

        sql = mock_pool.execute.call_args[0][0]
        assert "retry_count = retry_count + 1" in sql

    def test_sets_exponential_backoff_with_power_function(self, mock_pool):
        """retry_after uses POWER() for exponential backoff capped at 3 attempts."""
        with patch("asyncpg.create_pool", new=AsyncMock(return_value=mock_pool)):
            mgr = UnifiedStateManager(database_url="postgres://localhost/test")
            mgr.mark_error_sync("file_002", "err")

        sql = mock_pool.execute.call_args[0][0]
        assert "POWER" in sql
        assert "retry_after" in sql
        assert "LEAST" in sql

    def test_truncates_error_message_to_1000_chars(self, mock_pool):
        """Error messages longer than 1000 chars are truncated before storing."""
        long_error = "x" * 2000

        with patch("asyncpg.create_pool", new=AsyncMock(return_value=mock_pool)):
            mgr = UnifiedStateManager(database_url="postgres://localhost/test")
            mgr.mark_error_sync("file_002", long_error)

        passed_error = mock_pool.execute.call_args[0][2]
        assert len(passed_error) == 1000

    def test_sets_error_status_in_sql(self, mock_pool):
        """mark_error must set status = 'error' via SQL UPDATE."""
        with patch("asyncpg.create_pool", new=AsyncMock(return_value=mock_pool)):
            mgr = UnifiedStateManager(database_url="postgres://localhost/test")
            mgr.mark_error_sync("file_002", "fail")

        sql = mock_pool.execute.call_args[0][0]
        assert "status = 'error'" in sql

    def test_uses_update_not_insert(self, mock_pool):
        """mark_error is a pure UPDATE (no upsert — file must already exist)."""
        with patch("asyncpg.create_pool", new=AsyncMock(return_value=mock_pool)):
            mgr = UnifiedStateManager(database_url="postgres://localhost/test")
            mgr.mark_error_sync("file_002", "err")

        sql = mock_pool.execute.call_args[0][0].strip().upper()
        assert sql.startswith("UPDATE")
        assert "INSERT" not in sql


# ---------------------------------------------------------------------------
# State transition tests
# ---------------------------------------------------------------------------


class TestStateTransitionBehavior:
    """High-level state machine: pending → indexed, error → retry, error → DLQ."""

    def test_new_file_then_indexed_skips_second_process(self, mock_pool):
        """After mark_indexed, same-hash query returns False."""
        # Round 1: file is new
        mock_pool.fetchrow.return_value = None
        with patch("asyncpg.create_pool", new=AsyncMock(return_value=mock_pool)):
            mgr = UnifiedStateManager(database_url="postgres://localhost/test")
            assert mgr.should_process_sync("f1", "hash1") is True

        # Round 2: file is now indexed with the same hash
        mock_pool.fetchrow.return_value = _make_state_row(status="indexed", content_hash="hash1")
        with patch("asyncpg.create_pool", new=AsyncMock(return_value=mock_pool)):
            mgr2 = UnifiedStateManager(database_url="postgres://localhost/test")
            assert mgr2.should_process_sync("f1", "hash1") is False

    def test_error_then_retry_after_backoff_expires(self, mock_pool):
        """After backoff window passes, should_process returns True."""
        past = datetime.now(UTC) - timedelta(minutes=1)
        mock_pool.fetchrow.return_value = _make_state_row(
            status="error",
            retry_count=1,
            retry_after=past,
        )

        with patch("asyncpg.create_pool", new=AsyncMock(return_value=mock_pool)):
            mgr = UnifiedStateManager(database_url="postgres://localhost/test")
            assert mgr.should_process_sync("f1", "h") is True

    def test_error_enters_dlq_after_max_retries(self, mock_pool):
        """After retry_count reaches 3, file is in DLQ — skip forever."""
        mock_pool.fetchrow.return_value = _make_state_row(
            status="error",
            retry_count=3,
            retry_after=None,
        )

        with patch("asyncpg.create_pool", new=AsyncMock(return_value=mock_pool)):
            mgr = UnifiedStateManager(database_url="postgres://localhost/test")
            assert mgr.should_process_sync("f1", "h") is False


# ---------------------------------------------------------------------------
# sync_context pool reuse
# ---------------------------------------------------------------------------


class TestSyncContextPoolReuse:
    """Verify sync_context shares a single pool across calls."""

    def test_pool_created_once_per_sync_context(self, mock_pool):
        """asyncpg.create_pool is called exactly once per sync_context block."""
        mock_pool.fetchrow.return_value = None
        create_pool_mock = AsyncMock(return_value=mock_pool)

        with patch("asyncpg.create_pool", new=create_pool_mock):
            mgr = UnifiedStateManager(database_url="postgres://localhost/test")
            with mgr.sync_context():
                mgr.should_process_sync("f1", "h1")
                mgr.mark_indexed_sync("f1", chunk_count=10, content_hash="h1")

        assert create_pool_mock.call_count == 1
