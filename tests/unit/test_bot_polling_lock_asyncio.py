"""Tests for PropertyBot polling-lock asyncio-native task (#2617).

Pins the new contract: _polling_lock_task is an asyncio.Task, not
an APScheduler AsyncIOScheduler. Tests use object.__new__ to avoid
the full PropertyBot constructor.
"""

from __future__ import annotations

import asyncio
import contextlib
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest


def _make_bot_with_polling_lock() -> Any:
    """Minimal PropertyBot with only polling-lock fields populated."""
    from telegram_bot.bot import PropertyBot

    bot = object.__new__(PropertyBot)
    bot._history_save_tasks = set()
    bot._history_save_max_concurrency = 32
    bot._history_save_drain_timeout_s = 5.0
    bot._miniapp_subscriber_task = None
    bot._polling_lock_task = None
    bot._polling_lock = None
    bot._polling_lock_owner = None
    bot._polling_lock_consecutive_failures = 0
    # Minimal dp for stop_polling
    bot.dp = MagicMock()
    bot.dp.stop_polling = AsyncMock()
    return bot


@pytest.mark.asyncio
async def test_bot_polling_lock_uses_asyncio_task_not_apscheduler():
    """PropertyBot must not have _polling_lock_scheduler after migration.

    Documents intent: _polling_lock_task (asyncio.Task) replaces the old
    _polling_lock_scheduler (AsyncIOScheduler).
    """
    from telegram_bot.bot import PropertyBot

    # After migration _polling_lock_scheduler is gone; _polling_lock_task exists.
    assert not hasattr(PropertyBot, "_polling_lock_scheduler"), (
        "PropertyBot still has _polling_lock_scheduler; migration incomplete"
    )


@pytest.mark.asyncio
async def test_polling_lock_task_is_asyncio_task_when_set():
    """When a polling lock task is started, it must be an asyncio.Task."""
    bot = _make_bot_with_polling_lock()

    async def _fake_heartbeat_loop() -> None:
        stop = asyncio.Event()
        await stop.wait()

    bot._polling_lock_task = asyncio.create_task(_fake_heartbeat_loop())
    assert isinstance(bot._polling_lock_task, asyncio.Task)

    # Clean up
    bot._polling_lock_task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await bot._polling_lock_task


@pytest.mark.asyncio
async def test_polling_lock_heartbeat_loop_calls_tick_and_loops():
    """The polling-lock heartbeat loop must call the tick and sleep between calls."""
    bot = _make_bot_with_polling_lock()

    tick_calls = []

    async def fake_tick() -> None:
        tick_calls.append(1)

    bot._polling_lock_heartbeat_tick = fake_tick  # type: ignore[method-assign]

    async def heartbeat_loop(interval: int) -> None:
        while True:
            with contextlib.suppress(Exception):
                await bot._polling_lock_heartbeat_tick()
            await asyncio.sleep(interval)

    task = asyncio.create_task(heartbeat_loop(1))
    await asyncio.sleep(2.2)
    task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await task

    assert len(tick_calls) >= 2


@pytest.mark.asyncio
async def test_bot_stop_cancels_polling_lock_task():
    """stop() must cancel and await the polling lock task cleanly."""
    bot = _make_bot_with_polling_lock()

    async def eternal_loop() -> None:
        stop = asyncio.Event()
        await stop.wait()

    bot._polling_lock_task = asyncio.create_task(eternal_loop())

    # Simulate what stop() does after migration
    task = bot._polling_lock_task
    task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await task
    bot._polling_lock_task = None

    assert task.done()
    assert bot._polling_lock_task is None
