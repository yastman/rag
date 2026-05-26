"""PostgreSQL bootstrap helpers extracted from ``telegram_bot/bot.py`` (#1265).

PR-7 of Slice 1: pulls the postgres bootstrap helpers
(``_extract_database_name``, ``_ensure_postgres_database_exists``,
``_ensure_realestate_schema``) out of the ``PropertyBot`` god-object so
``bot.py`` shrinks toward a thin facade. The functions become
module-level callables that take their dependencies (admin URL, pool)
as arguments instead of reading ``self``. The class methods on
``PropertyBot`` stay as thin wrappers that bind ``self.config`` /
``self._pg_pool`` and delegate here, so existing tests at
``tests/unit/test_bot_handlers.py`` (which call
``bot._ensure_realestate_schema()``) keep working.

Module-level imports are kept light (stdlib + ``logging`` + ``re`` +
``urllib.parse``) so this file is cheap to import in unit tests that
exercise the bootstrap helpers in isolation. ``asyncpg`` is taken as a
parameter rather than imported at the top so the bot's existing
"asyncpg-import-failure must not crash unit tests" contract still
holds — see the wrapper in ``bot.py`` for the lazy import dance.

Tracked under #1265. Pinned by
``tests/contract/test_bot_postgres_bootstrap_extraction_contract.py``.
"""

from __future__ import annotations

import contextlib
import logging
import re
from typing import Any
from urllib.parse import unquote, urlparse


logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Schema DDL — bumped here so future schema changes are version-controlled
# alongside the bootstrap function rather than buried in bot.py.
# ---------------------------------------------------------------------------

REALESTATE_SCHEMA_STATEMENTS: tuple[str, ...] = (
    """
    CREATE TABLE IF NOT EXISTS users (
        id SERIAL PRIMARY KEY,
        telegram_id BIGINT UNIQUE NOT NULL,
        locale VARCHAR(5) DEFAULT 'ru',
        role VARCHAR(20) DEFAULT 'client',
        first_name VARCHAR(100),
        telegram_language_code VARCHAR(10),
        notifications_enabled BOOLEAN DEFAULT true,
        created_at TIMESTAMPTZ DEFAULT NOW(),
        updated_at TIMESTAMPTZ DEFAULT NOW()
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS leads (
        id SERIAL PRIMARY KEY,
        user_id INTEGER REFERENCES users(id),
        stage VARCHAR(30) DEFAULT 'new',
        score INTEGER DEFAULT 0,
        preferences JSONB DEFAULT '{}',
        kommo_lead_id BIGINT,
        created_at TIMESTAMPTZ DEFAULT NOW(),
        updated_at TIMESTAMPTZ DEFAULT NOW()
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS funnel_events (
        id SERIAL PRIMARY KEY,
        user_id INTEGER REFERENCES users(id),
        event_type VARCHAR(50) NOT NULL,
        metadata JSONB DEFAULT '{}',
        created_at TIMESTAMPTZ DEFAULT NOW()
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS lead_scores (
        id BIGSERIAL PRIMARY KEY,
        lead_id BIGINT NOT NULL REFERENCES leads(id) ON DELETE CASCADE,
        user_id BIGINT NOT NULL,
        session_id TEXT NOT NULL,
        score_value INTEGER NOT NULL CHECK (score_value BETWEEN 0 AND 100),
        score_band TEXT NOT NULL CHECK (score_band IN ('hot', 'warm', 'cold')),
        reason_codes JSONB NOT NULL DEFAULT '[]'::jsonb,
        kommo_lead_id BIGINT,
        sync_status TEXT NOT NULL DEFAULT 'pending'
            CHECK (sync_status IN ('pending', 'synced', 'failed')),
        sync_attempts INTEGER NOT NULL DEFAULT 0,
        last_synced_at TIMESTAMPTZ,
        sync_error TEXT,
        created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        UNIQUE (lead_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS lead_score_sync_audit (
        id BIGSERIAL PRIMARY KEY,
        lead_score_id BIGINT NOT NULL REFERENCES lead_scores(id) ON DELETE CASCADE,
        idempotency_key TEXT NOT NULL,
        sync_status TEXT NOT NULL,
        http_status INTEGER,
        response_excerpt TEXT,
        created_at TIMESTAMPTZ NOT NULL DEFAULT now()
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS nurturing_jobs (
        id BIGSERIAL PRIMARY KEY,
        lead_score_id BIGINT NOT NULL REFERENCES lead_scores(id) ON DELETE CASCADE,
        scheduled_for TIMESTAMPTZ NOT NULL,
        status TEXT NOT NULL DEFAULT 'pending'
            CHECK (status IN ('pending', 'running', 'sent', 'failed', 'skipped')),
        channel TEXT NOT NULL DEFAULT 'telegram',
        payload JSONB NOT NULL DEFAULT '{}'::jsonb,
        attempt_count INTEGER NOT NULL DEFAULT 0,
        last_error TEXT,
        sent_at TIMESTAMPTZ,
        created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        UNIQUE (lead_score_id, scheduled_for)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS funnel_metrics_daily (
        id BIGSERIAL PRIMARY KEY,
        metric_date DATE NOT NULL,
        stage_name TEXT NOT NULL,
        entered_count INTEGER NOT NULL DEFAULT 0,
        converted_count INTEGER NOT NULL DEFAULT 0,
        dropoff_count INTEGER NOT NULL DEFAULT 0,
        conversion_rate NUMERIC(6,4) NOT NULL DEFAULT 0,
        prev_stage_count INTEGER NOT NULL DEFAULT 0,
        step_conversion_rate NUMERIC(6,4) NOT NULL DEFAULT 0,
        created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        UNIQUE (metric_date, stage_name)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS scheduler_leases (
        lease_name TEXT PRIMARY KEY,
        owner_id TEXT NOT NULL,
        lease_until TIMESTAMPTZ NOT NULL,
        updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS user_favorites (
        id BIGSERIAL PRIMARY KEY,
        telegram_id BIGINT NOT NULL,
        property_id TEXT NOT NULL,
        property_data JSONB NOT NULL DEFAULT '{}'::jsonb,
        created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        UNIQUE (telegram_id, property_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS search_events (
        id BIGSERIAL PRIMARY KEY,
        user_id BIGINT NOT NULL,
        session_id TEXT NOT NULL,
        event_type TEXT NOT NULL DEFAULT 'apartment_search',
        query TEXT NOT NULL,
        filters JSONB,
        results_count INT NOT NULL DEFAULT 0,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )
    """,
    "ALTER TABLE funnel_events ADD COLUMN IF NOT EXISTS stage_name TEXT",
    "CREATE INDEX IF NOT EXISTS idx_users_telegram_id ON users(telegram_id)",
    "CREATE INDEX IF NOT EXISTS idx_leads_user_id ON leads(user_id)",
    "CREATE INDEX IF NOT EXISTS idx_leads_stage ON leads(stage)",
    "CREATE INDEX IF NOT EXISTS idx_funnel_events_user_id ON funnel_events(user_id)",
    "CREATE INDEX IF NOT EXISTS idx_funnel_events_created ON funnel_events(created_at DESC)",
    "CREATE INDEX IF NOT EXISTS idx_funnel_events_created_stage ON funnel_events (created_at DESC, stage_name)",
    "CREATE INDEX IF NOT EXISTS idx_lead_scores_pending_sync ON lead_scores (sync_status, updated_at DESC)",
    "CREATE INDEX IF NOT EXISTS idx_lead_scores_band_sync ON lead_scores (score_band, sync_status, updated_at DESC)",
    "CREATE INDEX IF NOT EXISTS idx_nurturing_jobs_pending ON nurturing_jobs (status, scheduled_for ASC)",
    "CREATE INDEX IF NOT EXISTS idx_user_favorites_telegram_id ON user_favorites (telegram_id)",
    "CREATE INDEX IF NOT EXISTS idx_user_favorites_created_at ON user_favorites (created_at DESC)",
    "CREATE INDEX IF NOT EXISTS idx_search_events_user ON search_events (user_id, created_at DESC)",
)


_SAFE_DB_NAME_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")


def extract_database_name(database_url: str) -> str | None:
    """Extract the database name from a PostgreSQL URL.

    Returns ``None`` when the URL has no ``/dbname`` segment, mirroring
    the original behaviour relied on by ``PropertyBot.start()``.
    """
    parsed = urlparse(database_url)
    raw_path = (parsed.path or "").lstrip("/")
    if not raw_path:
        return None
    return unquote(raw_path.split("/", 1)[0]) or None


async def ensure_postgres_database_exists(
    asyncpg_module: Any,
    admin_database_url: str,
    database_name: str,
) -> bool:
    """Idempotently ensure ``database_name`` exists on the cluster.

    Connects to the maintenance ``postgres`` database (PostgreSQL forbids
    ``CREATE DATABASE`` against the target itself), checks ``pg_database``,
    and creates the database when missing.

    Returns ``True`` when the database exists (created or pre-existing),
    ``False`` on any failure or rejected identifier.

    Args:
        asyncpg_module: The ``asyncpg`` module — passed in so unit tests
            and cold environments can avoid the import altogether.
        admin_database_url: A connection URL with admin privileges for
            the cluster. ``database`` is overridden to ``postgres``.
        database_name: The target database to ensure. Must match
            ``[A-Za-z_][A-Za-z0-9_]*`` — anything else is rejected with a
            warning so we never feed user-controlled identifiers into
            ``CREATE DATABASE`` even though the surrounding code already
            constrains them upstream.
    """
    if not _SAFE_DB_NAME_RE.fullmatch(database_name):
        logger.error("Unsafe PostgreSQL database name: %r", database_name)
        return False

    admin_conn: Any = None
    try:
        admin_conn = await asyncpg_module.connect(
            admin_database_url,
            timeout=5,
            database="postgres",
        )
        exists = await admin_conn.fetchval(
            "SELECT 1 FROM pg_database WHERE datname = $1",
            database_name,
        )
        if exists:
            return True

        escaped_name = database_name.replace('"', '""')
        await admin_conn.execute(f'CREATE DATABASE "{escaped_name}"')
        logger.info("Created PostgreSQL database: %s", database_name)
        return True
    except Exception as exc:
        duplicate_error = getattr(asyncpg_module, "DuplicateDatabaseError", None)
        if duplicate_error is not None and isinstance(exc, duplicate_error):
            logger.info(
                "PostgreSQL database already exists after concurrent create: %s", database_name
            )
            return True
        logger.warning(
            "Failed to ensure PostgreSQL database exists: %s",
            database_name,
            exc_info=True,
        )
        return False
    finally:
        if admin_conn is not None:
            with contextlib.suppress(Exception):
                await admin_conn.close()


async def ensure_realestate_schema(pg_pool: Any) -> None:
    """Apply :data:`REALESTATE_SCHEMA_STATEMENTS` against ``pg_pool``.

    No-op when ``pg_pool`` is ``None`` (matches the previous bot-side
    behaviour that silently skipped schema bootstrap when the pool had
    not been initialised).
    """
    if pg_pool is None:
        return
    for stmt in REALESTATE_SCHEMA_STATEMENTS:
        await pg_pool.execute(stmt)


__all__ = [
    "REALESTATE_SCHEMA_STATEMENTS",
    "ensure_postgres_database_exists",
    "ensure_realestate_schema",
    "extract_database_name",
]
