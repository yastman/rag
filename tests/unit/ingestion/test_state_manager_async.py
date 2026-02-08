# tests/unit/ingestion/test_state_manager_async.py
"""Tests for async methods in UnifiedStateManager."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock

import pytest

from src.ingestion.unified.state_manager import FileState, UnifiedStateManager


@pytest.fixture
def mock_pool():
    """Create a mock asyncpg pool."""
    pool = AsyncMock()
    pool.execute = AsyncMock()
    pool.fetch = AsyncMock(return_value=[])
    pool.fetchrow = AsyncMock(return_value=None)
    pool.close = AsyncMock()
    return pool


@pytest.fixture
def manager(mock_pool):
    """Create UnifiedStateManager with pre-injected mock pool."""
    return UnifiedStateManager(pool=mock_pool)


@pytest.fixture
def sample_state():
    """Create a sample FileState for testing."""
    return FileState(
        file_id="abc123",
        source_path="/docs/test.pdf",
        file_name="test.pdf",
        mime_type="application/pdf",
        file_size=1024,
        modified_time=datetime(2025, 1, 1, tzinfo=UTC),
        content_hash="sha256_hash",
        parser_version="docling-2.0",
        chunker_version="v1",
        embedding_model="bge-m3",
        chunk_count=10,
        collection_name="gdrive_documents_bge",
        pipeline_version="v3.2.1",
        status="indexed",
        indexed_at=datetime(2025, 1, 2, tzinfo=UTC),
    )


class TestGetStats:
    """Tests for get_stats async method."""

    async def test_returns_status_counts(self, manager, mock_pool):
        mock_pool.fetch.return_value = [
            {"status": "indexed", "count": 42},
            {"status": "error", "count": 3},
            {"status": "processing", "count": 1},
        ]

        result = await manager.get_stats()

        assert result == {"indexed": 42, "error": 3, "processing": 1}
        mock_pool.fetch.assert_called_once()
        call_sql = mock_pool.fetch.call_args[0][0]
        assert "GROUP BY status" in call_sql

    async def test_returns_empty_dict_when_no_rows(self, manager, mock_pool):
        mock_pool.fetch.return_value = []

        result = await manager.get_stats()

        assert result == {}

    async def test_single_status(self, manager, mock_pool):
        mock_pool.fetch.return_value = [{"status": "pending", "count": 100}]

        result = await manager.get_stats()

        assert result == {"pending": 100}


class TestGetDlqCount:
    """Tests for get_dlq_count async method."""

    async def test_returns_count(self, manager, mock_pool):
        mock_pool.fetchrow.return_value = {"count": 7}

        result = await manager.get_dlq_count()

        assert result == 7
        call_sql = mock_pool.fetchrow.call_args[0][0]
        assert "ingestion_dead_letter" in call_sql

    async def test_returns_zero_when_empty(self, manager, mock_pool):
        mock_pool.fetchrow.return_value = {"count": 0}

        result = await manager.get_dlq_count()

        assert result == 0


class TestMarkIndexed:
    """Tests for mark_indexed async method."""

    async def test_calls_execute_with_correct_params(self, manager, mock_pool):
        await manager.mark_indexed("file_001", chunk_count=15, content_hash="hash_abc")

        mock_pool.execute.assert_called_once()
        args = mock_pool.execute.call_args[0]
        sql = args[0]
        assert "status" in sql and "indexed" in sql
        assert "chunk_count" in sql
        assert "content_hash" in sql
        assert "ON CONFLICT" in sql
        assert args[1] == "file_001"
        assert args[2] == 15
        assert args[3] == "hash_abc"

    async def test_resets_error_fields(self, manager, mock_pool):
        await manager.mark_indexed("file_001", chunk_count=5, content_hash="h")

        sql = mock_pool.execute.call_args[0][0]
        assert "error_message = NULL" in sql
        assert "retry_count = 0" in sql
        assert "retry_after = NULL" in sql


class TestMarkError:
    """Tests for mark_error async method."""

    async def test_calls_update_with_error_status(self, manager, mock_pool):
        await manager.mark_error("file_002", "Connection timeout")

        mock_pool.execute.assert_called_once()
        args = mock_pool.execute.call_args[0]
        sql = args[0]
        assert "status = 'error'" in sql
        assert "error_message" in sql
        assert "retry_count = retry_count + 1" in sql
        assert args[1] == "file_002"
        assert args[2] == "Connection timeout"

    async def test_truncates_long_error_message(self, manager, mock_pool):
        long_error = "x" * 2000

        await manager.mark_error("file_002", long_error)

        passed_error = mock_pool.execute.call_args[0][2]
        assert len(passed_error) == 1000

    async def test_exponential_backoff_in_sql(self, manager, mock_pool):
        await manager.mark_error("file_002", "err")

        sql = mock_pool.execute.call_args[0][0]
        assert "POWER" in sql
        assert "retry_after" in sql


class TestUpsertState:
    """Tests for upsert_state async method."""

    async def test_insert_on_conflict(self, manager, mock_pool, sample_state):
        await manager.upsert_state(sample_state)

        mock_pool.execute.assert_called_once()
        args = mock_pool.execute.call_args[0]
        sql = args[0]
        assert "INSERT INTO" in sql
        assert "ON CONFLICT (file_id) DO UPDATE" in sql
        assert args[1] == "abc123"

    async def test_passes_all_state_fields(self, manager, mock_pool, sample_state):
        await manager.upsert_state(sample_state)

        args = mock_pool.execute.call_args[0]
        # file_id, source_path, file_name, mime_type, file_size, modified_time,
        # content_hash, parser_version, chunker_version, embedding_model,
        # chunk_count, collection_name, pipeline_version, status, error_message,
        # retry_count, retry_after, indexed_at = 18 params
        assert args[1] == "abc123"
        assert args[2] == "/docs/test.pdf"
        assert args[3] == "test.pdf"
        assert args[4] == "application/pdf"
        assert args[5] == 1024
        assert args[10] == "bge-m3"
        assert args[11] == 10
        assert args[14] == "indexed"


class TestGetState:
    """Tests for get_state async method."""

    async def test_returns_file_state_when_found(self, manager, mock_pool):
        mock_pool.fetchrow.return_value = {
            "file_id": "f1",
            "source_path": "/a.pdf",
            "file_name": "a.pdf",
            "mime_type": "application/pdf",
            "file_size": 512,
            "modified_time": None,
            "content_hash": "h1",
            "parser_version": None,
            "chunker_version": None,
            "embedding_model": "bge-m3",
            "chunk_count": 5,
            "collection_name": "col1",
            "pipeline_version": "v3.2.1",
            "indexed_at": None,
            "status": "indexed",
            "error_message": None,
            "retry_count": 0,
            "retry_after": None,
        }

        result = await manager.get_state("f1")

        assert isinstance(result, FileState)
        assert result.file_id == "f1"
        assert result.chunk_count == 5
        assert result.status == "indexed"

    async def test_returns_none_when_not_found(self, manager, mock_pool):
        mock_pool.fetchrow.return_value = None

        result = await manager.get_state("nonexistent")

        assert result is None


class TestMarkProcessing:
    """Tests for mark_processing async method."""

    async def test_sets_processing_status(self, manager, mock_pool):
        await manager.mark_processing("file_003")

        mock_pool.execute.assert_called_once()
        args = mock_pool.execute.call_args[0]
        assert "processing" in args[0]
        assert "ON CONFLICT" in args[0]
        assert args[1] == "file_003"


class TestMarkDeleted:
    """Tests for mark_deleted async method."""

    async def test_sets_deleted_status(self, manager, mock_pool):
        await manager.mark_deleted("file_004")

        mock_pool.execute.assert_called_once()
        args = mock_pool.execute.call_args[0]
        assert "deleted" in args[0]
        assert args[1] == "file_004"


class TestShouldProcess:
    """Tests for should_process async method."""

    async def test_new_file_returns_true(self, manager, mock_pool):
        mock_pool.fetchrow.return_value = None

        result = await manager.should_process("new_file", "hash1")

        assert result is True

    async def test_unchanged_indexed_file_returns_false(self, manager, mock_pool):
        mock_pool.fetchrow.return_value = {
            "file_id": "f1",
            "source_path": None,
            "file_name": None,
            "mime_type": None,
            "file_size": None,
            "modified_time": None,
            "content_hash": "same_hash",
            "parser_version": None,
            "chunker_version": None,
            "embedding_model": "bge-m3",
            "chunk_count": 5,
            "collection_name": None,
            "pipeline_version": "v3.2.1",
            "indexed_at": None,
            "status": "indexed",
            "error_message": None,
            "retry_count": 0,
            "retry_after": None,
        }

        result = await manager.should_process("f1", "same_hash")

        assert result is False

    async def test_changed_hash_returns_true(self, manager, mock_pool):
        mock_pool.fetchrow.return_value = {
            "file_id": "f1",
            "source_path": None,
            "file_name": None,
            "mime_type": None,
            "file_size": None,
            "modified_time": None,
            "content_hash": "old_hash",
            "parser_version": None,
            "chunker_version": None,
            "embedding_model": "bge-m3",
            "chunk_count": 5,
            "collection_name": None,
            "pipeline_version": "v3.2.1",
            "indexed_at": None,
            "status": "indexed",
            "error_message": None,
            "retry_count": 0,
            "retry_after": None,
        }

        result = await manager.should_process("f1", "new_hash")

        assert result is True

    async def test_error_in_backoff_returns_false(self, manager, mock_pool):
        future_time = datetime.now(UTC) + timedelta(hours=1)
        mock_pool.fetchrow.return_value = {
            "file_id": "f1",
            "source_path": None,
            "file_name": None,
            "mime_type": None,
            "file_size": None,
            "modified_time": None,
            "content_hash": "h",
            "parser_version": None,
            "chunker_version": None,
            "embedding_model": "bge-m3",
            "chunk_count": 0,
            "collection_name": None,
            "pipeline_version": "v3.2.1",
            "indexed_at": None,
            "status": "error",
            "error_message": "fail",
            "retry_count": 1,
            "retry_after": future_time,
        }

        result = await manager.should_process("f1", "h")

        assert result is False

    async def test_exceeded_retries_returns_false(self, manager, mock_pool):
        mock_pool.fetchrow.return_value = {
            "file_id": "f1",
            "source_path": None,
            "file_name": None,
            "mime_type": None,
            "file_size": None,
            "modified_time": None,
            "content_hash": "h",
            "parser_version": None,
            "chunker_version": None,
            "embedding_model": "bge-m3",
            "chunk_count": 0,
            "collection_name": None,
            "pipeline_version": "v3.2.1",
            "indexed_at": None,
            "status": "error",
            "error_message": "fail",
            "retry_count": 3,
            "retry_after": None,
        }

        result = await manager.should_process("f1", "h")

        assert result is False


class TestGetAllIndexedFileIds:
    """Tests for get_all_indexed_file_ids async method."""

    async def test_returns_set_of_ids(self, manager, mock_pool):
        mock_pool.fetch.return_value = [
            {"file_id": "a"},
            {"file_id": "b"},
            {"file_id": "c"},
        ]

        result = await manager.get_all_indexed_file_ids()

        assert result == {"a", "b", "c"}

    async def test_returns_empty_set(self, manager, mock_pool):
        mock_pool.fetch.return_value = []

        result = await manager.get_all_indexed_file_ids()

        assert result == set()


class TestAddToDlq:
    """Tests for add_to_dlq async method."""

    async def test_inserts_and_returns_id(self, manager, mock_pool):
        mock_pool.fetchrow.return_value = {"id": 42}

        result = await manager.add_to_dlq("file_005", "parse_error", "Bad format")

        assert result == 42
        args = mock_pool.fetchrow.call_args[0]
        assert "ingestion_dead_letter" in args[0]
        assert "RETURNING id" in args[0]
        assert args[1] == "file_005"
        assert args[2] == "parse_error"
        assert args[3] == "Bad format"

    async def test_truncates_long_error(self, manager, mock_pool):
        mock_pool.fetchrow.return_value = {"id": 1}
        long_msg = "e" * 3000

        await manager.add_to_dlq("f", "err", long_msg)

        passed_msg = mock_pool.fetchrow.call_args[0][3]
        assert len(passed_msg) == 2000

    async def test_serializes_payload_as_json(self, manager, mock_pool):
        mock_pool.fetchrow.return_value = {"id": 1}
        payload = {"chunks": [1, 2], "source": "test.pdf"}

        await manager.add_to_dlq("f", "err", "msg", payload=payload)

        passed_payload = mock_pool.fetchrow.call_args[0][4]
        assert json.loads(passed_payload) == payload

    async def test_none_payload(self, manager, mock_pool):
        mock_pool.fetchrow.return_value = {"id": 1}

        await manager.add_to_dlq("f", "err", "msg", payload=None)

        passed_payload = mock_pool.fetchrow.call_args[0][4]
        assert passed_payload is None


class TestClose:
    """Tests for close async method."""

    async def test_closes_owned_pool(self):
        pool = AsyncMock()
        mgr = UnifiedStateManager(pool=None, database_url="postgres://localhost/test")
        mgr._pool = pool
        mgr._owns_pool = True

        await mgr.close()

        pool.close.assert_called_once()
        assert mgr._pool is None

    async def test_does_not_close_external_pool(self, manager, mock_pool):
        # pool was injected, so _owns_pool = False
        await manager.close()

        mock_pool.close.assert_not_called()


class TestPoolNotInitialized:
    """Edge case: pool is None and no database_url."""

    async def test_get_stats_raises_without_pool_or_url(self):
        mgr = UnifiedStateManager(pool=None, database_url=None)

        with pytest.raises(ValueError, match="Either pool or database_url required"):
            await mgr.get_stats()

    async def test_mark_indexed_raises_without_pool_or_url(self):
        mgr = UnifiedStateManager(pool=None, database_url=None)

        with pytest.raises(ValueError, match="Either pool or database_url required"):
            await mgr.mark_indexed("f", 1, "h")

    async def test_get_dlq_count_raises_without_pool_or_url(self):
        mgr = UnifiedStateManager(pool=None, database_url=None)

        with pytest.raises(ValueError, match="Either pool or database_url required"):
            await mgr.get_dlq_count()


class TestConnectionError:
    """Edge case: pool operations raise exceptions."""

    async def test_get_stats_propagates_connection_error(self, manager, mock_pool):
        mock_pool.fetch.side_effect = OSError("Connection refused")

        with pytest.raises(OSError, match="Connection refused"):
            await manager.get_stats()

    async def test_mark_error_propagates_connection_error(self, manager, mock_pool):
        mock_pool.execute.side_effect = OSError("Connection refused")

        with pytest.raises(OSError, match="Connection refused"):
            await manager.mark_error("f", "err")

    async def test_upsert_state_propagates_connection_error(self, manager, mock_pool, sample_state):
        mock_pool.execute.side_effect = OSError("Connection refused")

        with pytest.raises(OSError, match="Connection refused"):
            await manager.upsert_state(sample_state)
