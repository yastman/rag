"""Bookmarks capability startup tests (#3241, #3440).

The core demo must start with PostgreSQL stopped: ``setup_postgres`` then
records an honest DEGRADED signal, constructs no favourites service, and the
UI capability predicate (:func:`bookmarks_ready`) reads as not ready. With a
validated PostgreSQL the capability is enabled and CRUD services exist.

#3440 makes the optional capability setup transactional: every failure after
``create_pool`` (schema bootstrap, any service constructor) closes the pool
and leaves all bot capability fields unset, and a failing pool close during
that cleanup is reported without hiding the primary failure.
"""

from __future__ import annotations

import logging
import sys
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from telegram_bot.capabilities import bookmarks_ready
from telegram_bot.startup_status import StartupReport, StartupSeverity


def _bot_stub() -> MagicMock:
    bot = MagicMock()
    bot.config.realestate_database_url = "postgresql://postgres:pw@localhost:5432/realestate"
    bot._pg_pool = None
    bot._favorites_service = None
    bot._user_service = None
    bot._search_event_store = None
    # Kept as a no-op guard: whichever way the schema stage is wired (bot
    # wrapper or the canonical postgres_bootstrap function), the unit tests
    # stay hermetic. Fault injection for the schema stage uses pool.execute.
    bot._ensure_realestate_schema = AsyncMock()
    return bot


def _pool_stub() -> MagicMock:
    pool = MagicMock()
    pool.execute = AsyncMock()
    pool.close = AsyncMock()
    return pool


def _asyncpg_stub(pool: MagicMock) -> MagicMock:
    fake_asyncpg = MagicMock()
    test_conn = MagicMock()
    test_conn.close = AsyncMock()
    fake_asyncpg.connect = AsyncMock(return_value=test_conn)
    fake_asyncpg.create_pool = AsyncMock(return_value=pool)
    return fake_asyncpg


def _assert_capability_fully_reset(bot: MagicMock, report: Any) -> None:
    """Every capability field must be unset and exactly one degraded signal emitted (#3440)."""
    assert bot._pg_pool is None
    assert bot._user_service is None
    assert bot._favorites_service is None
    assert bot._search_event_store is None
    assert bookmarks_ready(bot) is False
    signals = [s for s in report.signals if s.source == "postgres_runtime"]
    assert len(signals) == 1, f"expected exactly one degraded signal, got: {report.signals}"
    assert signals[0].severity is StartupSeverity.DEGRADED
    assert "Bookmarks capability disabled" in signals[0].summary


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
    pool = _pool_stub()
    fake_asyncpg = _asyncpg_stub(pool)

    with (
        patch.dict(sys.modules, {"asyncpg": fake_asyncpg}),
        caplog.at_level(logging.INFO, logger="telegram_bot.lifecycle.lifecycle"),
    ):
        await setup_postgres(bot, {"postgres": True}, report)

    # Success is one atomic commit: pool, every service, and the capability
    # flag land together only after schema bootstrap ran on the pool (#3440).
    assert bot._pg_pool is pool
    assert bot._user_service is not None
    assert bot._favorites_service is not None
    assert bot._search_event_store is not None
    assert bookmarks_ready(bot) is True
    assert pool.execute.await_count >= 10, (
        "schema bootstrap must run against the pool before the commit step"
    )
    assert pool.close.await_count == 0, "a committed pool must not be closed"
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


async def test_schema_bootstrap_failure_closes_pool_and_resets_all_fields() -> None:
    """A schema failure after create_pool closes the pool and leaves every field unset (#3440)."""
    from telegram_bot.lifecycle.lifecycle import setup_postgres

    bot = _bot_stub()
    report = StartupReport()
    pool = _pool_stub()
    pool.execute = AsyncMock(side_effect=RuntimeError("schema init failed"))
    fake_asyncpg = _asyncpg_stub(pool)

    with patch.dict(sys.modules, {"asyncpg": fake_asyncpg}):
        await setup_postgres(bot, {"postgres": True}, report)

    pool.close.assert_awaited_once()
    _assert_capability_fully_reset(bot, report)


@pytest.mark.parametrize(
    ("service_module", "service_attr"),
    [
        ("telegram_bot.services.user_service", "UserService"),
        ("telegram_bot.services.favorites_service", "FavoritesService"),
        ("telegram_bot.services.observability.search_event_store", "SearchEventStore"),
    ],
)
async def test_service_constructor_failure_closes_pool_and_resets_all_fields(
    service_module: str, service_attr: str
) -> None:
    """Each post-pool constructor failure rolls the whole capability back (#3440)."""
    from telegram_bot.lifecycle.lifecycle import setup_postgres

    bot = _bot_stub()
    report = StartupReport()
    pool = _pool_stub()
    fake_asyncpg = _asyncpg_stub(pool)

    with (
        patch.dict(sys.modules, {"asyncpg": fake_asyncpg}),
        patch(
            f"{service_module}.{service_attr}",
            side_effect=RuntimeError(f"{service_attr} boom"),
        ),
    ):
        await setup_postgres(bot, {"postgres": True}, report)

    pool.close.assert_awaited_once()
    _assert_capability_fully_reset(bot, report)


async def test_pool_close_failure_is_reported_without_hiding_primary_failure(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A failing pool close during cleanup is logged and the primary failure still surfaces (#3440)."""
    from telegram_bot.lifecycle.lifecycle import setup_postgres

    bot = _bot_stub()
    report = StartupReport()
    pool = _pool_stub()
    pool.execute = AsyncMock(side_effect=RuntimeError("schema init failed"))
    pool.close = AsyncMock(side_effect=RuntimeError("close failed"))
    fake_asyncpg = _asyncpg_stub(pool)

    with (
        patch.dict(sys.modules, {"asyncpg": fake_asyncpg}),
        caplog.at_level(logging.WARNING, logger="telegram_bot.lifecycle.lifecycle"),
    ):
        await setup_postgres(bot, {"postgres": True}, report)

    pool.close.assert_awaited_once()
    _assert_capability_fully_reset(bot, report)
    messages = [r.getMessage() for r in caplog.records]
    assert any("PostgreSQL pool init failed" in m for m in messages), (
        f"primary failure must still be reported, got: {messages}"
    )
    assert any("close failed" in m for m in messages), (
        f"cleanup failure must be reported too, got: {messages}"
    )


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
