"""Transition-focused tests for UnifiedStateManager.

These tests cover state transition SQL and sync cleanup behavior without a
real Postgres connection.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from src.ingestion.unified.state_manager import UnifiedStateManager


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


async def test_mark_processing_upserts_processing_for_new_file(
    manager: UnifiedStateManager,
    mock_pool: AsyncMock,
) -> None:
    await manager.mark_processing("file-a")

    mock_pool.execute.assert_awaited_once()
    sql, file_id = mock_pool.execute.await_args.args
    assert "INSERT INTO ingestion_state" in sql
    assert "processing" in sql
    assert "ON CONFLICT" in sql
    assert file_id == "file-a"


async def test_mark_indexed_resets_error_retry_fields(
    manager: UnifiedStateManager,
    mock_pool: AsyncMock,
) -> None:
    await manager.mark_indexed("file-a", chunk_count=12, content_hash="hash-a")

    mock_pool.execute.assert_awaited_once()
    args = mock_pool.execute.await_args.args
    sql = args[0]
    assert "status = 'indexed'" in sql
    assert "error_message = NULL" in sql
    assert "retry_count = 0" in sql
    assert "retry_after = NULL" in sql
    assert args[1:] == ("file-a", 12, "hash-a")


async def test_mark_error_updates_retry_backoff_atomically(
    manager: UnifiedStateManager,
    mock_pool: AsyncMock,
) -> None:
    await manager.mark_error("file-a", "x" * 1500)

    mock_pool.execute.assert_awaited_once()
    args = mock_pool.execute.await_args.args
    sql = args[0]
    assert "status = 'error'" in sql
    assert "retry_count = retry_count + 1" in sql
    assert "retry_after = NOW()" in sql
    assert "POWER" in sql
    assert args[1] == "file-a"
    assert len(args[2]) == 1000


async def test_concurrent_mark_processing_records_all_file_ids(
    manager: UnifiedStateManager,
    mock_pool: AsyncMock,
) -> None:
    file_ids = [f"file-{i}" for i in range(5)]

    await asyncio.gather(*(manager.mark_processing(file_id) for file_id in file_ids))

    seen_file_ids = [call.args[1] for call in mock_pool.execute.await_args_list]
    assert sorted(seen_file_ids) == file_ids


def test_sync_context_closes_pool_and_resets_runner(mock_pool: AsyncMock) -> None:
    create_pool = AsyncMock(return_value=mock_pool)

    with patch("asyncpg.create_pool", new=create_pool):
        manager = UnifiedStateManager(database_url="postgresql://localhost/test")
        with manager.sync_context():
            assert manager.should_process_sync("file-a", "hash-a") is True
            assert manager._runner is not None
            assert manager._pool is mock_pool

        assert manager._runner is None
        assert manager._pool is None
        mock_pool.close.assert_awaited_once()
