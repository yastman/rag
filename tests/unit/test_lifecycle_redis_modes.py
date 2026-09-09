"""Lifecycle mode wiring tests (#3362, decision #3354).

Polling ownership per mode:
- ``disabled``: no lock claim, no client needed.
- ``single_instance``: exactly one process, NO distributed-lock claim.
- ``multi_instance``: a live Redis backend + acquired lock are required
  before polling; acquisition failure propagates (main exits 2).

Also covers the startup capability report signal added by ``start_bot``.
"""

from __future__ import annotations

import asyncio
import logging
from contextlib import ExitStack
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.runtime.integrations.polling_lock import PollingLockBusy
from src.runtime.integrations.redis_mode import RedisMode
from telegram_bot.lifecycle.lifecycle import setup_polling_lock, start_bot
from telegram_bot.startup_status import StartupReport, StartupSeverity


class _FakeBackendLock:
    def __init__(self, acquire_result: bool) -> None:
        self._acquire_result = acquire_result
        self.acquire_calls: list[str] = []
        self.released = False

    async def acquire(self, token: str) -> bool:
        self.acquire_calls.append(token)
        return self._acquire_result

    async def extend(self, additional_time: int, replace_ttl: bool) -> bool:
        return True

    async def release(self) -> int:
        self.released = True
        return 1


class _FakeRedis:
    def __init__(self, acquire_result: bool = True) -> None:
        self.backend_lock = _FakeBackendLock(acquire_result)

    def lock(self, key: str, timeout: int, blocking: bool, thread_local: bool) -> _FakeBackendLock:
        return self.backend_lock


def _bot(mode: RedisMode, redis_backend: object | None) -> MagicMock:
    bot = MagicMock()
    bot.config.redis_mode = mode
    bot._cache = MagicMock()
    bot._cache.redis = redis_backend
    bot._polling_lock = None
    bot._polling_lock_task = None
    bot._polling_lock_consecutive_failures = 0
    bot._polling_lock_owner = None
    return bot


class TestSetupPollingLock:
    async def test_disabled_mode_makes_no_claim(self, caplog) -> None:
        bot = _bot(RedisMode.DISABLED, redis_backend=None)
        with caplog.at_level(logging.INFO, logger="telegram_bot.lifecycle.lifecycle"):
            await setup_polling_lock(bot)

        assert bot._polling_lock is None
        assert bot._polling_lock_task is None
        assert "disabled" in caplog.text.lower()

    async def test_single_instance_makes_no_distributed_lock_claim(self, caplog) -> None:
        # #3354: single_instance polling ownership is "exactly one process;
        # no distributed-lock claim" — even with a live Redis backend present.
        redis = _FakeRedis()
        bot = _bot(RedisMode.SINGLE_INSTANCE, redis_backend=redis)
        with caplog.at_level(logging.INFO, logger="telegram_bot.lifecycle.lifecycle"):
            await setup_polling_lock(bot)

        assert bot._polling_lock is None
        assert bot._polling_lock_task is None
        assert len(redis.backend_lock.acquire_calls) == 0
        assert "single_instance" in caplog.text.lower()
        assert "lock" in caplog.text.lower()

    async def test_multi_instance_requires_live_backend(self) -> None:
        bot = _bot(RedisMode.MULTI_INSTANCE, redis_backend=None)
        with pytest.raises(RuntimeError, match="multi_instance"):
            await setup_polling_lock(bot)
        assert bot._polling_lock is None

    async def test_multi_instance_acquires_lock_and_starts_heartbeat(self) -> None:
        redis = _FakeRedis(acquire_result=True)
        bot = _bot(RedisMode.MULTI_INSTANCE, redis_backend=redis)

        await setup_polling_lock(bot)

        assert bot._polling_lock is not None
        assert len(redis.backend_lock.acquire_calls) == 1
        assert bot._polling_lock_owner is not None
        assert bot._polling_lock_task is not None
        assert not bot._polling_lock_task.done()

        # Teardown the heartbeat task for the test runner.
        bot._polling_lock_task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await bot._polling_lock_task

    async def test_multi_instance_lock_busy_propagates(self) -> None:
        redis = _FakeRedis(acquire_result=False)
        bot = _bot(RedisMode.MULTI_INSTANCE, redis_backend=redis)

        with pytest.raises(PollingLockBusy):
            await setup_polling_lock(bot)
        assert bot._polling_lock_task is None


class TestStartBotCapabilitySignal:
    """startup report exposes selected mode and capability state (#3354)."""

    _ASYNC_HELPERS = (
        "setup_cache",
        "setup_postgres",
        "setup_bot_identity",
        "setup_bot_commands",
        "setup_polling_lock",
        "warmup_bge_pool",
    )
    _SYNC_HELPERS = (
        "setup_handoff_services",
        "setup_workflow_data",
        "setup_dialogs",
    )

    def _patched_start(self, report: StartupReport, bot: MagicMock) -> ExitStack:
        stack = ExitStack()
        stack.enter_context(
            patch(
                "telegram_bot.lifecycle.lifecycle.setup_preflight",
                new_callable=AsyncMock,
                return_value=({}, report),
            )
        )
        for name in self._ASYNC_HELPERS:
            stack.enter_context(
                patch(
                    f"telegram_bot.lifecycle.lifecycle.{name}",
                    new_callable=AsyncMock,
                )
            )
        for name in self._SYNC_HELPERS:
            stack.enter_context(patch(f"telegram_bot.lifecycle.lifecycle.{name}"))
        bot.dp.start_polling = AsyncMock()
        bot._polling_lock_task = None
        bot._redis_monitor = None
        bot._hybrid = MagicMock()
        return stack

    async def test_disabled_mode_reports_capability_disabled(self) -> None:
        report = StartupReport()
        bot = _bot(RedisMode.DISABLED, redis_backend=None)

        with self._patched_start(report, bot):
            await start_bot(bot)

        signals = [s for s in report.signals if s.source == "redis_capabilities"]
        assert signals, "start_bot must add a redis_capabilities signal"
        assert "disabled" in signals[0].summary
        assert signals[0].severity is StartupSeverity.OK

    async def test_single_instance_without_connection_reports_degraded(self) -> None:
        report = StartupReport()
        bot = _bot(RedisMode.SINGLE_INSTANCE, redis_backend=None)

        with self._patched_start(report, bot):
            await start_bot(bot)

        signals = [s for s in report.signals if s.source == "redis_capabilities"]
        assert signals, "start_bot must add a redis_capabilities signal"
        assert signals[0].severity is StartupSeverity.DEGRADED
        assert "single_instance" in signals[0].summary

    async def test_connected_single_instance_reports_enabled(self) -> None:
        report = StartupReport()
        bot = _bot(RedisMode.SINGLE_INSTANCE, redis_backend=object())

        with self._patched_start(report, bot):
            await start_bot(bot)

        signals = [s for s in report.signals if s.source == "redis_capabilities"]
        assert signals
        assert signals[0].severity is StartupSeverity.OK
