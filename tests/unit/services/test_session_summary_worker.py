"""Tests for SessionSummaryWorker (#445 Task 5)."""

import asyncio
import time
from unittest.mock import AsyncMock, MagicMock

import pytest

from telegram_bot.services.session_summary_worker import SessionSummaryWorker


@pytest.fixture
def worker():
    return SessionSummaryWorker(
        redis=AsyncMock(),
        llm=MagicMock(),
        kommo_client=None,
        idle_timeout_min=30,
        poll_interval_sec=10,  # fast for tests
    )


async def test_worker_starts_and_stops(worker):
    await worker.start()
    assert worker._task is not None
    await worker.stop()
    assert worker._task.done()


async def test_no_idle_sessions(worker):
    worker._redis.scan = AsyncMock(return_value=(0, []))
    result = await worker._check_idle_sessions()
    assert result == 0


async def test_idle_session_detected(worker):
    worker._redis.scan = AsyncMock(return_value=(0, [b"session:last_active:123"]))
    worker._redis.get = AsyncMock(return_value=str(time.time() - 2000).encode())
    worker._redis.delete = AsyncMock()
    worker._get_conversation_history = AsyncMock(
        return_value=[
            {"role": "user", "content": "Looking for 2-room apartment"},
            {"role": "assistant", "content": "I found several options..."},
        ]
    )
    worker._generate_summary = AsyncMock(return_value="Client looking for 2-room apartment")
    count = await worker._check_idle_sessions()
    assert count == 1
    worker._redis.delete.assert_called_once()


async def test_skip_short_conversations(worker):
    worker._redis.scan = AsyncMock(return_value=(0, [b"session:last_active:456"]))
    worker._redis.get = AsyncMock(return_value=str(time.time() - 2000).encode())
    worker._get_conversation_history = AsyncMock(
        return_value=[
            {"role": "user", "content": "Hi"},
        ]
    )
    count = await worker._check_idle_sessions()
    assert count == 0  # < 2 messages, skip


async def test_graceful_stop_during_processing(worker):
    """Worker stops cleanly even if already running."""
    await worker.start()
    assert worker._task is not None
    # stop() must complete without hanging
    await asyncio.wait_for(worker.stop(), timeout=3.0)
    assert worker._task.done()


async def test_recent_session_not_processed(worker):
    """Session active 5 min ago should not be processed (under 30 min threshold)."""
    worker._redis.scan = AsyncMock(return_value=(0, [b"session:last_active:789"]))
    # 5 minutes ago — under idle_timeout_min=30
    worker._redis.get = AsyncMock(return_value=str(time.time() - 300).encode())
    worker._generate_summary = AsyncMock()
    count = await worker._check_idle_sessions()
    assert count == 0
    worker._generate_summary.assert_not_called()


async def test_kommo_write_skipped_without_lead_id(worker):
    """Kommo add_note is skipped when lead_id is not yet resolved (entity_id=0 guard)."""
    mock_kommo = AsyncMock()
    worker._kommo = mock_kommo
    worker._redis.scan = AsyncMock(return_value=(0, [b"session:last_active:111"]))
    worker._redis.get = AsyncMock(return_value=str(time.time() - 2000).encode())
    worker._redis.delete = AsyncMock()
    worker._get_conversation_history = AsyncMock(
        return_value=[
            {"role": "user", "content": "Budget is 80k EUR"},
            {"role": "assistant", "content": "Great, I have options in your range"},
        ]
    )
    worker._generate_summary = AsyncMock(return_value="Budget 80k EUR client")
    await worker._check_idle_sessions()
    # lead_id not yet resolved — add_note should NOT be called
    mock_kommo.add_note.assert_not_called()


async def test_none_redis_key_skipped(worker):
    """Keys that have been expired (get returns None) are skipped."""
    worker._redis.scan = AsyncMock(return_value=(0, [b"session:last_active:999"]))
    worker._redis.get = AsyncMock(return_value=None)
    worker._generate_summary = AsyncMock()
    count = await worker._check_idle_sessions()
    assert count == 0
    worker._generate_summary.assert_not_called()


async def test_scan_multi_page_cursor_accumulation(worker):
    """SCAN loop accumulates keys across multiple pages (cursor non-zero then zero)."""
    # First page returns cursor=5 (more pages), second page returns cursor=0 (done)
    worker._redis.scan = AsyncMock(
        side_effect=[
            (5, [b"session:last_active:101"]),
            (0, [b"session:last_active:102"]),
        ]
    )
    # Both keys are old enough to process
    worker._redis.get = AsyncMock(return_value=str(time.time() - 2000).encode())
    worker._redis.delete = AsyncMock()
    worker._get_conversation_history = AsyncMock(
        return_value=[
            {"role": "user", "content": "msg"},
            {"role": "assistant", "content": "reply"},
        ]
    )
    worker._generate_summary = AsyncMock(return_value="summary")
    count = await worker._check_idle_sessions()
    # Both keys from both pages should be processed
    assert count == 2
    assert worker._redis.scan.call_count == 2
