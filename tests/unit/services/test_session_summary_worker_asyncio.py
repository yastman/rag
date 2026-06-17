"""Tests for SessionSummaryWorker asyncio-native periodic task (#2617).

Verifies that start/tick/graceful-cancel work without APScheduler.
"""

import asyncio
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
        poll_interval_sec=1,  # fast for tests
    )


@pytest.mark.asyncio
async def test_start_creates_asyncio_task_not_apscheduler(worker):
    """start() must use asyncio.create_task, not APScheduler."""
    await worker.start()

    assert worker._task is not None
    assert isinstance(worker._task, asyncio.Task)

    await worker.stop()


@pytest.mark.asyncio
async def test_start_does_not_import_or_use_apscheduler():
    """session_summary_worker module must not reference AsyncIOScheduler after migration."""
    import telegram_bot.services.session_summary_worker as mod

    assert not hasattr(mod, "AsyncIOScheduler"), (
        "AsyncIOScheduler should not be imported in session_summary_worker"
    )


@pytest.mark.asyncio
async def test_stop_cancels_task(worker):
    """stop() must cancel and clear the background task."""
    await worker.start()
    task = worker._task
    assert task is not None

    await worker.stop()

    assert task.done()
    assert worker._task is None


@pytest.mark.asyncio
async def test_tick_is_called_on_schedule():
    """_check_idle_sessions must be invoked by the periodic loop."""
    worker = SessionSummaryWorker(
        redis=AsyncMock(),
        llm=MagicMock(),
        poll_interval_sec=1,
    )

    call_count = 0

    async def fake_tick():
        nonlocal call_count
        call_count += 1
        return 0

    worker._check_idle_sessions = fake_tick  # type: ignore[method-assign]
    await worker.start()
    await asyncio.sleep(1.2)
    await worker.stop()

    assert call_count >= 1, f"Expected at least 1 tick, got {call_count}"


@pytest.mark.asyncio
async def test_exception_in_tick_does_not_stop_loop():
    """An exception in _check_idle_sessions must not kill the background loop."""
    worker = SessionSummaryWorker(
        redis=AsyncMock(),
        llm=MagicMock(),
        poll_interval_sec=1,
    )

    call_count = 0

    async def failing_tick():
        nonlocal call_count
        call_count += 1
        raise RuntimeError("transient error")

    worker._check_idle_sessions = failing_tick  # type: ignore[method-assign]
    await worker.start()
    await asyncio.sleep(2.2)
    await worker.stop()

    assert call_count >= 2, f"Expected at least 2 ticks despite exception, got {call_count}"


@pytest.mark.asyncio
async def test_graceful_cancel_on_stop(worker):
    """stop() with a long interval still terminates cleanly."""
    slow_worker = SessionSummaryWorker(
        redis=AsyncMock(),
        llm=MagicMock(),
        poll_interval_sec=600,  # would normally sleep for 10 minutes
    )
    await slow_worker.start()
    task = slow_worker._task
    assert task is not None and not task.done()

    await slow_worker.stop()

    assert task.done()
