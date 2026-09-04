"""Bookmarks capability startup tests (#3241).

The core demo must start with PostgreSQL stopped: ``setup_postgres`` then
records an honest DEGRADED signal, constructs no favourites service, and the
UI capability predicate (:func:`bookmarks_ready`) reads as not ready. With a
validated PostgreSQL the capability is enabled and CRUD services exist.
"""

from __future__ import annotations

import logging
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from telegram_bot.startup_status import StartupReport, StartupSeverity
from telegram_bot.services.favorites_service import bookmarks_ready


def _bot_stub() -> MagicMock:
    bot = MagicMock()
    bot.config.realestate_database_url = "postgresql://postgres:pw@localhost:5432/realestate"
    bot._pg_pool = None
    bot._favorites_service = None
    bot._user_service = None
    bot._search_event_store = None
    bot._ensure_realestate_schema = AsyncMock()
    return bot


async def test_setup_postgres_disabled_when_preflight_marks_postgres_down(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """No-Postgres startup: degraded capability signal, no favourites service."""
    from telegram_bot.lifecycle.lifecycle import setup_postgres

    bot = _bot_stub()
    report = StartupReport()

    with caplog.at_level(logging.INFO, logger="telegram_bot.lifecycle.lifecycle"):
        await setup_postgres(bot, {"postgres": False}, report)

    assert bot._favorites_service is None
    assert bookmarks_ready(bot) is False

    signals = [s for s in report.signals if s.source == "postgres_runtime"]
    assert signals, f"expected a postgres_runtime signal, got: {report.signals}"
    assert signals[0].severity is StartupSeverity.DEGRADED
    assert "Bookmarks capability disabled" in signals[0].summary
    assert "--profile postgres" in (signals[0].remediation or "")

    assert any("Bookmarks capability: disabled" in r.message for r in caplog.records)


async def test_setup_postgres_enables_capability_after_validated_connection(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Validated PostgreSQL constructs the service and enables the capability."""
    from telegram_bot.lifecycle.lifecycle import setup_postgres

    bot = _bot_stub()
    report = StartupReport()

    fake_asyncpg = MagicMock()
    test_conn = MagicMock()
    test_conn.close = AsyncMock()
    fake_asyncpg.connect = AsyncMock(return_value=test_conn)
    pool = MagicMock()
    fake_asyncpg.create_pool = AsyncMock(return_value=pool)

    with (
        patch.dict(sys.modules, {"asyncpg": fake_asyncpg}),
        caplog.at_level(logging.INFO, logger="telegram_bot.lifecycle.lifecycle"),
    ):
        await setup_postgres(bot, {"postgres": True}, report)

    assert bot._pg_pool is pool
    assert bot._favorites_service is not None
    assert bookmarks_ready(bot) is True
    assert not [s for s in report.signals if s.source == "postgres_runtime"], (
        f"healthy PostgreSQL must not add degraded signals, got: {report.signals}"
    )
    assert any("Bookmarks capability: enabled" in r.message for r in caplog.records)


async def test_setup_postgres_failure_reports_disabled_capability() -> None:
    """A failed pool init degrades to the disabled-capability signal."""
    from telegram_bot.lifecycle.lifecycle import setup_postgres

    bot = _bot_stub()
    report = StartupReport()

    fake_asyncpg = MagicMock()
    fake_asyncpg.connect = AsyncMock(side_effect=OSError("connection refused"))

    with patch.dict(sys.modules, {"asyncpg": fake_asyncpg}):
        await setup_postgres(bot, {"postgres": True}, report)

    assert bot._favorites_service is None
    assert bookmarks_ready(bot) is False
    signals = [s for s in report.signals if s.source == "postgres_runtime"]
    assert signals and signals[0].severity is StartupSeverity.DEGRADED
    assert "Bookmarks capability disabled" in signals[0].summary


async def test_handle_bookmarks_replies_with_honest_capability_copy() -> None:
    """Without the service the bookmarks entry point explains why it is off (#3241)."""
    from telegram_bot.handlers.favorites import _handle_bookmarks

    bot = _bot_stub()  # _favorites_service is None
    message = MagicMock()
    message.from_user = MagicMock(id=42)
    message.answer = AsyncMock()

    await _handle_bookmarks(bot, message, state=None)

    message.answer.assert_awaited_once()
    text = message.answer.await_args.args[0]
    assert "Закладки недоступны" in text
    assert "PostgreSQL" in text
    # The old misleading wording is gone.
    assert "временно" not in text
