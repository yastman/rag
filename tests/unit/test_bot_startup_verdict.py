"""Tests for bot startup verdict (OK/DEGRADED) and polling-lock diagnostics.

Card: card_d00421b975e3 — Авто-проверка чистого старта
Phase: P20 — Live operational validation

Tests:
1. start_bot emits "Startup verdict: OK" when all deps healthy
2. start_bot emits "Startup verdict: DEGRADED" + WARNING log when Postgres offline
3. PollingLockBusy.acquire raises with owner + pttl_ms in exception message
"""

from __future__ import annotations

import logging
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from telegram_bot.startup_status import StartupReport, StartupSeverity, StartupSignal


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_bot_stub() -> MagicMock:
    """Minimal bot stub satisfying start_bot's duck-typed expectations."""
    bot = MagicMock()
    bot.dp = MagicMock()
    bot.dp.start_polling = AsyncMock()
    bot._polling_lock_task = None
    bot._cache = MagicMock()
    bot._cache.redis = None  # skip polling-lock and handoff sections
    bot._hybrid = MagicMock()
    bot._redis_monitor = MagicMock()
    bot._redis_monitor.start = AsyncMock()
    return bot


def _ok_report() -> StartupReport:
    return StartupReport()  # no signals → OK


# ---------------------------------------------------------------------------
# Test 1: Startup verdict OK
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_start_bot_verdict_ok(caplog: pytest.LogCaptureFixture) -> None:
    """start_bot logs 'Startup verdict: OK' when all setup helpers succeed."""
    from telegram_bot.lifecycle.lifecycle import start_bot

    bot = _make_bot_stub()
    ok_report = _ok_report()

    with (
        patch(
            "telegram_bot.lifecycle.lifecycle.setup_preflight",
            new_callable=AsyncMock,
            return_value=({}, ok_report),
        ),
        patch("telegram_bot.lifecycle.lifecycle.setup_cache", new_callable=AsyncMock),
        patch("telegram_bot.lifecycle.lifecycle.setup_postgres", new_callable=AsyncMock),
        patch("telegram_bot.lifecycle.lifecycle.setup_bot_identity", new_callable=AsyncMock),
        patch("telegram_bot.lifecycle.lifecycle.setup_handoff_services"),
        patch("telegram_bot.lifecycle.lifecycle.setup_workflow_data"),
        patch("telegram_bot.lifecycle.lifecycle.setup_dialogs"),
        patch("telegram_bot.lifecycle.lifecycle.setup_bot_commands", new_callable=AsyncMock),
        patch("telegram_bot.lifecycle.lifecycle.setup_polling_lock", new_callable=AsyncMock),
        patch("telegram_bot.lifecycle.lifecycle.warmup_bge_pool", new_callable=AsyncMock),
        caplog.at_level(logging.INFO, logger="telegram_bot.lifecycle.lifecycle"),
    ):
        await start_bot(bot)

    rendered = ok_report.render()
    assert "Startup verdict: OK" in rendered, f"render() output: {rendered!r}"


# ---------------------------------------------------------------------------
# Test 2: Startup verdict DEGRADED — Postgres offline
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_start_bot_verdict_degraded_postgres_offline(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """start_bot logs WARNING with 'Startup verdict: DEGRADED' when Postgres is offline.

    Simulates the Postgres soft-dep offline path: setup_postgres adds a
    DEGRADED signal to the shared startup_report.
    """
    from telegram_bot.lifecycle.lifecycle import start_bot

    bot = _make_bot_stub()

    async def _mock_postgres(
        bot: object, preflight_result: object, startup_report: StartupReport
    ) -> None:
        # Simulate what setup_postgres does when Postgres is unreachable
        startup_report.add(
            StartupSignal(
                source="postgres_runtime",
                severity=StartupSeverity.DEGRADED,
                summary="PostgreSQL pool unavailable, user features disabled",
                remediation="restore PostgreSQL connectivity",
            )
        )

    with (
        patch(
            "telegram_bot.lifecycle.lifecycle.setup_preflight",
            new_callable=AsyncMock,
            return_value=({"postgres": False}, StartupReport()),
        ),
        patch("telegram_bot.lifecycle.lifecycle.setup_cache", new_callable=AsyncMock),
        patch("telegram_bot.lifecycle.lifecycle.setup_postgres", side_effect=_mock_postgres),
        patch("telegram_bot.lifecycle.lifecycle.setup_bot_identity", new_callable=AsyncMock),
        patch("telegram_bot.lifecycle.lifecycle.setup_handoff_services"),
        patch("telegram_bot.lifecycle.lifecycle.setup_workflow_data"),
        patch("telegram_bot.lifecycle.lifecycle.setup_dialogs"),
        patch("telegram_bot.lifecycle.lifecycle.setup_bot_commands", new_callable=AsyncMock),
        patch("telegram_bot.lifecycle.lifecycle.setup_polling_lock", new_callable=AsyncMock),
        patch("telegram_bot.lifecycle.lifecycle.warmup_bge_pool", new_callable=AsyncMock),
        caplog.at_level(logging.WARNING, logger="telegram_bot.lifecycle.lifecycle"),
    ):
        await start_bot(bot)

    # Check that WARNING was logged (not silent failure)
    warning_records = [
        r for r in caplog.records if r.levelno == logging.WARNING and "DEGRADED" in r.message
    ]
    assert warning_records, (
        f"Expected a WARNING log containing 'DEGRADED'. "
        f"Captured records: {[(r.levelname, r.message) for r in caplog.records]}"
    )

    # Verify the verdict text itself is DEGRADED
    assert "Startup verdict: DEGRADED" in warning_records[0].message, (
        f"Expected 'Startup verdict: DEGRADED' in WARNING message, got: {warning_records[0].message!r}"
    )


# ---------------------------------------------------------------------------
# Test 3: PollingLockBusy — diagnostic message carries owner + pttl_ms
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_polling_lock_busy_acquire_carries_owner_and_pttl_ms() -> None:
    """RedisPollingLock.acquire raises PollingLockBusy with owner + pttl_ms in message.

    Checks the diagnostic message content — the operator-facing fields that
    make the failure self-diagnosing without extra tooling.
    """
    from src.runtime.integrations.polling_lock import PollingLockBusy, RedisPollingLock

    mock_lock = MagicMock()
    mock_lock.acquire = AsyncMock(return_value=False)  # lock is busy

    redis = MagicMock()
    redis.lock = MagicMock(return_value=mock_lock)
    redis.get = AsyncMock(return_value=b"prod-host-1:9876")
    redis.pttl = AsyncMock(return_value=55000)

    lock = RedisPollingLock(redis=redis, key="telegram-bot:polling", ttl_sec=90)

    with pytest.raises(PollingLockBusy) as exc_info:
        await lock.acquire(owner="test-host:1234")

    msg = str(exc_info.value)
    assert "owner=" in msg, f"'owner=' missing from PollingLockBusy message: {msg!r}"
    assert "pttl" in msg, f"'pttl' missing from PollingLockBusy message: {msg!r}"
    assert "prod-host-1:9876" in msg, f"owner value missing from message: {msg!r}"
    assert "55000" in msg, f"pttl_ms value missing from message: {msg!r}"
