"""Tests for RedisHealthMonitor asyncio-native periodic task (#2617).

Verifies that start/tick/graceful-cancel work without APScheduler.
"""

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from telegram_bot.services.redis_monitor import RedisHealthMonitor


@pytest.mark.asyncio
async def test_start_creates_asyncio_task_not_apscheduler():
    """start() must NOT use APScheduler; it should use asyncio.create_task."""
    monitor = RedisHealthMonitor("redis://localhost:6379")

    with (
        patch("telegram_bot.services.redis_monitor.aioredis.from_url") as mock_from_url,
    ):
        mock_client = AsyncMock()
        mock_from_url.return_value = mock_client

        await monitor.start()

    # _task is an asyncio.Task, not an APScheduler scheduler
    assert monitor._task is not None
    assert isinstance(monitor._task, asyncio.Task)

    # Clean up
    await monitor.stop()


@pytest.mark.asyncio
async def test_start_does_not_import_or_use_apscheduler():
    """redis_monitor module must not reference AsyncIOScheduler after migration."""
    import telegram_bot.services.redis_monitor as mod

    assert not hasattr(mod, "AsyncIOScheduler"), (
        "AsyncIOScheduler should not be imported in redis_monitor"
    )


@pytest.mark.asyncio
async def test_stop_cancels_asyncio_task():
    """stop() must cancel the background task and await it."""
    monitor = RedisHealthMonitor("redis://localhost:6379")

    with patch("telegram_bot.services.redis_monitor.aioredis.from_url") as mock_from_url:
        mock_client = AsyncMock()
        mock_from_url.return_value = mock_client
        await monitor.start()

    assert monitor._task is not None
    task = monitor._task

    await monitor.stop()

    assert task.cancelled() or task.done()
    assert monitor._task is None
    assert monitor._redis is None


@pytest.mark.asyncio
async def test_tick_is_called_on_schedule():
    """_check_health must be called by the periodic loop."""
    monitor = RedisHealthMonitor("redis://localhost:6379", check_interval=1)

    call_count = 0

    async def fake_check_health():
        nonlocal call_count
        call_count += 1

    with patch("telegram_bot.services.redis_monitor.aioredis.from_url") as mock_from_url:
        mock_client = AsyncMock()
        mock_from_url.return_value = mock_client
        monitor._check_health = fake_check_health  # type: ignore[assignment]
        await monitor.start()

    # Wait long enough for at least one tick
    await asyncio.sleep(1.2)
    await monitor.stop()

    assert call_count >= 1, f"Expected at least 1 tick, got {call_count}"


@pytest.mark.asyncio
async def test_exception_in_tick_does_not_stop_loop():
    """An exception in _check_health must be caught; the loop continues."""
    monitor = RedisHealthMonitor("redis://localhost:6379", check_interval=1)

    call_count = 0

    async def failing_check():
        nonlocal call_count
        call_count += 1
        raise RuntimeError("transient error")

    with patch("telegram_bot.services.redis_monitor.aioredis.from_url") as mock_from_url:
        mock_client = AsyncMock()
        mock_from_url.return_value = mock_client
        monitor._check_health = failing_check  # type: ignore[assignment]
        await monitor.start()

    await asyncio.sleep(2.2)
    await monitor.stop()

    # Loop should have continued after the exception
    assert call_count >= 2, f"Expected at least 2 ticks despite exception, got {call_count}"


@pytest.mark.asyncio
async def test_graceful_cancel_on_stop():
    """stop() must result in the task being done (cancelled or finished cleanly)."""
    monitor = RedisHealthMonitor("redis://localhost:6379", check_interval=60)

    with patch("telegram_bot.services.redis_monitor.aioredis.from_url") as mock_from_url:
        mock_client = AsyncMock()
        mock_from_url.return_value = mock_client
        await monitor.start()

    task = monitor._task
    assert task is not None
    assert not task.done()

    await monitor.stop()

    assert task.done()
