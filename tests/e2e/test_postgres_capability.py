"""Live PostgreSQL capability E2E (#3415, audit A11).

Proves the bookmarks capability against REAL PostgreSQL through the
production path: the lifecycle ``setup_postgres`` transactional setup
(#3440) runs the production schema bootstrap inside a run-owned, per-worker
schema (``rag_e2e_<run>_<worker>``, the #3414 harness seam) of the harness's
disposable ``realestate`` database, and the Dispatcher/lifecycle-owned
services (users, favourites, search events) perform every action. Public
service reads prove the rows; raw SQL appears only to verify schema
namespacing and teardown — never to perform actions.

A bare connection to the maintenance database ``postgres`` proves nothing
(the replaced ``tests/integration/test_docker_services.py`` scenario): the
capability is enabled only when PostgreSQL is configured, connected, and
schema-ready. The disabled/unavailable paths keep the documented observable
UI: :func:`telegram_bot.capabilities.bookmarks_ready` gates the bookmarks
entry point, whose handler answers with the honest capability copy.

Focused run (per the issue):

    E2E_CORE_STRICT=1 uv run --no-sync pytest -q tests/e2e/test_postgres_capability.py

Required mode (``E2E_CORE_STRICT``/``E2E_HARNESS_REQUIRED``) has ZERO
service-related skips: missing PostgreSQL fails, never skips. The canonical
hermetic entry is ``make e2e-harness`` with
``E2E_HARNESS_PATHS=tests/e2e/test_postgres_capability.py``.
"""

from __future__ import annotations

import json
import re
from collections.abc import AsyncIterator
from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any

import pytest

from telegram_bot.capabilities import bookmarks_ready, set_bookmarks_ready
from telegram_bot.startup_status import StartupReport, StartupSeverity
from tests.e2e_core.live_harness import (
    RunNamespace,
    TeardownRegistry,
    _postgres_dsn_from_env,
    guard_service_skip,
    provide_postgres_schema,
)


pytestmark = [pytest.mark.e2e, pytest.mark.requires_services]


def _schema_pinned_dsn(dsn: str, schema: str) -> str:
    """Append ``search_path`` so unqualified service queries hit the run-owned schema.

    asyncpg forwards unknown DSN query parameters as server settings
    (``connect_utils._parse_connect_dsn_and_args``), so the production bot
    DSN can be pointed at a namespaced schema without touching production
    code — the #3415 constraint of no schema/repository refactor.
    """
    separator = "&" if "?" in dsn else "?"
    return f"{dsn}{separator}search_path={schema}"


def _deterministic_telegram_id(run_id: str, worker: str, salt: int) -> int:
    """Stable per-run user id so a re-run against the same schema is idempotent."""
    return (int(run_id[:8], 16) + salt) % (2**31 - 1)


def _bot_stub(realestate_database_url: str) -> SimpleNamespace:
    """Minimal bot surface exactly as ``lifecycle.setup_postgres`` consumes it.

    The two bootstrap attributes mirror the PropertyBot thin wrappers
    (``bot.py``) so the auto-create fallback stays on production code.
    """
    from telegram_bot.lifecycle import postgres_bootstrap

    return SimpleNamespace(
        config=SimpleNamespace(realestate_database_url=realestate_database_url),
        _pg_pool=None,
        _favorites_service=None,
        _user_service=None,
        _search_event_store=None,
        _extract_database_name=postgres_bootstrap.extract_database_name,
        _ensure_postgres_database_exists=postgres_bootstrap.ensure_postgres_database_exists,
    )


class _RecordingMessage:
    """Minimal Message surface for the bookmarks entry-point handler."""

    def __init__(self, user_id: int) -> None:
        self.from_user = SimpleNamespace(id=user_id)
        self.sent: list[str] = []

    async def answer(self, text: str, *args: Any, **kwargs: Any) -> None:
        self.sent.append(text)


@dataclass
class _LiveCapability:
    """Wired production capability plus harness ownership handles."""

    namespace: RunNamespace
    bot: Any
    report: StartupReport
    lease: Any  # PostgresLease
    server_version: str


def _telegram_id(capability: _LiveCapability, salt: int) -> int:
    return _deterministic_telegram_id(
        capability.namespace.run_id, capability.namespace.worker, salt
    )


def _jsonb(value: Any) -> Any:
    """asyncpg returns JSONB as str without a registered codec (see _parse_jsonb)."""
    if isinstance(value, str):
        return json.loads(value)
    return value


async def _connect(dsn: str) -> Any:
    import asyncpg

    return await asyncpg.connect(dsn, timeout=10)


async def _server_version(dsn: str) -> str:
    connection = await _connect(dsn)
    try:
        return str(await connection.fetchval("SELECT version()"))
    finally:
        await connection.close()


async def _tables_in_schema(lease: Any) -> set[str]:
    connection = await _connect(lease.dsn)
    try:
        rows = await connection.fetch(
            "SELECT table_name FROM information_schema.tables WHERE table_schema = $1",
            lease.schema,
        )
    finally:
        await connection.close()
    return {row["table_name"] for row in rows}


async def _owned_rows_for(lease: Any, table: str, column: str, value: int) -> int:
    """Count rows physically stored in the run-owned schema (namespacing proof)."""
    connection = await _connect(lease.dsn)
    try:
        count = await connection.fetchval(
            f'SELECT COUNT(*) FROM "{lease.schema}"."{table}" WHERE {column} = $1',
            value,
        )
    finally:
        await connection.close()
    return int(count)


@pytest.fixture
async def live_capability() -> AsyncIterator[_LiveCapability]:
    """One run-owned schema with the production capability setup applied.

    Provisioning doubles as the availability probe: unreachable PostgreSQL
    skips in optional mode and FAILS in required mode (``guard_service_skip``)
    — a required capability can never go green through a skip. Teardown
    closes the bot pool (mirroring ``lifecycle.stop_bot``), then drops ONLY
    the run-owned schema and proves it is gone.
    """
    namespace = RunNamespace.resolve()
    registry = TeardownRegistry(run_id=namespace.run_id)
    try:
        lease = await provide_postgres_schema(None, namespace)
    except Exception as exc:
        guard_service_skip(
            f"PostgreSQL unavailable for the capability lane: {type(exc).__name__}: {exc}"
        )
    registry.register_postgres(lease)

    from telegram_bot.lifecycle.lifecycle import setup_postgres

    bot = _bot_stub(_schema_pinned_dsn(lease.dsn, lease.schema))
    report = StartupReport()
    await setup_postgres(bot, {"postgres": True}, report)

    yield _LiveCapability(
        namespace=namespace,
        bot=bot,
        report=report,
        lease=lease,
        server_version=await _server_version(lease.dsn),
    )

    set_bookmarks_ready(bot, service=None)
    pool = bot._pg_pool
    if pool is not None:
        await pool.close()
    teardown_report = await registry.teardown_and_verify()
    assert teardown_report["schemas"] == 1


# ---------------------------------------------------------------------------
# Enabled path: configured + connected + schema-ready
# ---------------------------------------------------------------------------


async def test_capability_enabled_on_real_postgres_with_schema_ready(
    live_capability: _LiveCapability,
) -> None:
    """setup_postgres publishes the full capability only against real PostgreSQL."""
    cap = live_capability
    assert bookmarks_ready(cap.bot) is True
    assert cap.bot._pg_pool is not None
    assert cap.bot._user_service is not None
    assert cap.bot._favorites_service is not None
    assert cap.bot._search_event_store is not None
    assert [s for s in cap.report.signals if s.source == "postgres_runtime"] == []

    # Migrated unique health assertion from tests/integration/test_docker_services.py.
    assert "PostgreSQL" in cap.server_version

    # Production schema bootstrap landed every live schema family in the
    # RUN-OWNED schema, not the shared default search path.
    tables = await _tables_in_schema(cap.lease)
    assert {"users", "leads", "user_favorites", "search_events", "lead_scores"} <= tables


# ---------------------------------------------------------------------------
# Users: get_or_create / update / public reads
# ---------------------------------------------------------------------------


async def test_user_created_updated_and_read_through_service(
    live_capability: _LiveCapability,
) -> None:
    """UserService round trip: create, read, update — no duplicate row."""
    cap = live_capability
    users = cap.bot._user_service
    telegram_id = _telegram_id(cap, salt=1)

    created = await users.get_or_create(
        telegram_id=telegram_id, first_name="E2E", language_code="en"
    )
    assert created is not None
    assert created.telegram_id == telegram_id
    assert created.locale == "en"  # detect_locale(language_code)
    assert created.first_name == "E2E"

    # Public reads prove the row in the run-owned schema.
    assert await users.get_locale(telegram_id=telegram_id) == "en"
    assert await users.get_role(telegram_id=telegram_id) == "client"

    await users.set_locale(telegram_id=telegram_id, locale="uk")
    reread = await users.get_or_create(telegram_id=telegram_id)
    assert reread is not None
    assert reread.id == created.id  # existing-row path
    assert reread.locale == "uk"

    assert await _owned_rows_for(cap.lease, "users", "telegram_id", telegram_id) == 1


# ---------------------------------------------------------------------------
# Bookmarks: add / list / remove through FavoritesService
# ---------------------------------------------------------------------------


async def test_bookmark_add_list_remove_through_service(
    live_capability: _LiveCapability,
) -> None:
    """FavoritesService round trip with JSONB payloads and unique-contract idempotency."""
    cap = live_capability
    telegram_id = _telegram_id(cap, salt=2)
    # The dispatcher-created user precedes bookmark actions in the real flow.
    await cap.bot._user_service.get_or_create(telegram_id=telegram_id, language_code="ru")
    favorites = cap.bot._favorites_service

    first = await favorites.add(
        telegram_id, "prop-sunny-beach", {"city": "Sunny Beach", "price_eur": 110000}
    )
    assert first is not None
    assert first["property_id"] == "prop-sunny-beach"
    assert _jsonb(first["property_data"])["price_eur"] == 110000
    assert first["created_at"] is not None

    await favorites.add(telegram_id, "prop-garden", {"city": "Sotirovo"})

    duplicate = await favorites.add(telegram_id, "prop-sunny-beach", {"city": "Sunny Beach"})
    assert duplicate is None  # UNIQUE (telegram_id, property_id): no duplicate row

    listed = await favorites.list(telegram_id)
    assert [fav.property_id for fav in listed] == ["prop-garden", "prop-sunny-beach"]
    assert listed[0].property_data == {"city": "Sotirovo"}
    assert listed[1].property_data["price_eur"] == 110000

    assert await favorites.count(telegram_id) == 2
    assert await favorites.is_favorited(telegram_id, "prop-sunny-beach") is True

    assert await favorites.remove(telegram_id, "prop-sunny-beach") is True
    assert await favorites.remove(telegram_id, "prop-sunny-beach") is False

    assert await favorites.count(telegram_id) == 1
    assert [fav.property_id for fav in await favorites.list(telegram_id)] == ["prop-garden"]
    assert await _owned_rows_for(cap.lease, "user_favorites", "telegram_id", telegram_id) == 1


async def test_bookmarks_entry_point_reads_through_real_service(
    live_capability: _LiveCapability,
) -> None:
    """The bookmarks UI entry point answers from a real repository read."""
    cap = live_capability
    telegram_id = _telegram_id(cap, salt=5)
    await cap.bot._user_service.get_or_create(telegram_id=telegram_id, language_code="en")

    from telegram_bot.handlers.favorites import _handle_bookmarks

    message = _RecordingMessage(user_id=telegram_id)
    await _handle_bookmarks(cap.bot, message)  # type: ignore[arg-type]

    assert len(message.sent) == 1
    assert "пока нет закладок" in message.sent[0]


# ---------------------------------------------------------------------------
# Search events: append / read through SearchEventStore
# ---------------------------------------------------------------------------


async def test_search_events_append_and_read_through_service(
    live_capability: _LiveCapability,
) -> None:
    """SearchEventStore round trip: append-only events, newest-first public read."""
    cap = live_capability
    telegram_id = _telegram_id(cap, salt=3)
    session_id = f"sess-{cap.namespace.run_id}-{cap.namespace.worker}"
    await cap.bot._user_service.get_or_create(telegram_id=telegram_id, language_code="ru")
    store = cap.bot._search_event_store

    await store.append(
        telegram_id,
        session_id,
        "двушка до 100 тысяч у моря",
        filters={"rooms": 2, "price_eur": {"lte": 100000}},
        results_count=5,
    )
    await store.append(telegram_id, session_id, "студия Солнечный берег", results_count=1)

    events = await store.get_user_events(telegram_id)
    assert len(events) == 2
    assert events[0]["query"] == "студия Солнечный берег"  # newest first
    assert events[0]["event_type"] == "apartment_search"
    assert events[0]["results_count"] == 1
    assert events[1]["query"] == "двушка до 100 тысяч у моря"
    assert _jsonb(events[1]["filters"]) == {"rooms": 2, "price_eur": {"lte": 100000}}
    assert await _owned_rows_for(cap.lease, "search_events", "user_id", telegram_id) == 2


# ---------------------------------------------------------------------------
# Idempotent re-runs
# ---------------------------------------------------------------------------


async def test_rerun_against_existing_schema_is_idempotent(
    live_capability: _LiveCapability,
) -> None:
    """Re-running the scenario with the same deterministic ids duplicates nothing."""
    cap = live_capability
    users = cap.bot._user_service
    favorites = cap.bot._favorites_service
    telegram_id = _telegram_id(cap, salt=4)

    first = await users.get_or_create(telegram_id=telegram_id, first_name="E2E")
    second = await users.get_or_create(telegram_id=telegram_id, first_name="E2E")
    assert first is not None and second is not None
    assert second.id == first.id

    added = await favorites.add(telegram_id, "prop-rerun", {"city": "Nessebar"})
    assert added is not None
    assert await favorites.add(telegram_id, "prop-rerun", {"city": "Nessebar"}) is None
    assert await favorites.count(telegram_id) == 1

    assert await _owned_rows_for(cap.lease, "users", "telegram_id", telegram_id) == 1
    assert await _owned_rows_for(cap.lease, "user_favorites", "telegram_id", telegram_id) == 1


# ---------------------------------------------------------------------------
# Disabled / unavailable paths: documented observable behavior
# ---------------------------------------------------------------------------


async def test_preflight_down_disables_capability_with_documented_ui() -> None:
    """Preflight-down startup: capability off, degraded signal, honest UI copy."""
    from telegram_bot.lifecycle.lifecycle import setup_postgres

    bot = _bot_stub(_postgres_dsn_from_env())  # never connected on this path
    report = StartupReport()
    await setup_postgres(bot, {"postgres": False}, report)

    assert bookmarks_ready(bot) is False
    assert bot._pg_pool is None
    assert bot._user_service is None
    assert bot._search_event_store is None

    signals = [s for s in report.signals if s.source == "postgres_runtime"]
    assert len(signals) == 1
    assert signals[0].severity is StartupSeverity.DEGRADED
    assert "Bookmarks capability disabled" in signals[0].summary
    assert "--profile postgres" in (signals[0].remediation or "")

    from telegram_bot.handlers.favorites import _handle_bookmarks

    message = _RecordingMessage(user_id=42)
    await _handle_bookmarks(bot, message)  # type: ignore[arg-type]
    assert len(message.sent) == 1
    assert "Закладки недоступны" in message.sent[0]
    assert "PostgreSQL" in message.sent[0]
    # The old misleading wording is gone.
    assert "временно" not in message.sent[0]


async def test_unreachable_postgres_degrades_capability_safely() -> None:
    """A refused connection rolls the whole capability back with one degraded signal."""
    from telegram_bot.lifecycle.lifecycle import setup_postgres

    dead_dsn = re.sub(r":\d+/", ":1/", _postgres_dsn_from_env(), count=1)  # closed port
    bot = _bot_stub(dead_dsn)
    report = StartupReport()
    await setup_postgres(bot, {"postgres": True}, report)

    assert bookmarks_ready(bot) is False
    assert bot._pg_pool is None
    assert bot._user_service is None
    assert bot._favorites_service is None
    assert bot._search_event_store is None

    signals = [s for s in report.signals if s.source == "postgres_runtime"]
    assert len(signals) == 1
    assert signals[0].severity is StartupSeverity.DEGRADED
    assert "Bookmarks capability disabled" in signals[0].summary
