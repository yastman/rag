"""Recording database boundary proof; live SQL validity belongs to #3415."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from telegram_bot.lifecycle.postgres_bootstrap import (
    ensure_postgres_database_exists,
    ensure_realestate_schema,
    extract_database_name,
)


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("postgresql://user:secret@localhost:5432/realestate?sslmode=require", "realestate"),
        ("postgres://localhost/%72eal_estate/ignored", "real_estate"),
        ("postgresql://localhost/_tenant42", "_tenant42"),
        ("postgresql://localhost", None),
        ("postgresql://localhost/", None),
        ("", None),
    ],
)
def test_extract_database_name(url, expected) -> None:
    assert extract_database_name(url) == expected


def test_malformed_database_url_raises() -> None:
    with pytest.raises(ValueError):
        extract_database_name("postgresql://[invalid/database")


@pytest.mark.parametrize(
    "encoded_name", ["db%22%3BDROP%20DATABASE%20postgres", "db%2Fother", "with-dash", "9db"]
)
async def test_unsafe_url_database_name_never_connects(encoded_name) -> None:
    driver = SimpleNamespace(connect=AsyncMock())
    name = extract_database_name(f"postgresql://localhost/{encoded_name}")
    assert name is not None
    assert (
        await ensure_postgres_database_exists(driver, "postgresql://localhost/admin", name) is False
    )
    driver.connect.assert_not_awaited()


class RecordingConnection:
    def __init__(self, exists=False, execute_error=None):
        self.exists = exists
        self.execute_error = execute_error
        self.queries = []
        self.statements = []
        self.closed = 0

    async def fetchval(self, sql, name):
        self.queries.append((sql, name))
        return self.exists

    async def execute(self, sql):
        if self.execute_error:
            raise self.execute_error
        self.statements.append(" ".join(sql.split()))
        self.exists = True

    async def close(self):
        self.closed += 1


@pytest.mark.parametrize("already_exists", [False, True])
async def test_database_bootstrap_is_idempotent_and_closes_connection(already_exists) -> None:
    conn = RecordingConnection(exists=already_exists)
    driver = SimpleNamespace(connect=AsyncMock(return_value=conn))
    for _ in range(2):
        assert (
            await ensure_postgres_database_exists(driver, "postgresql://host/target", "tenant")
            is True
        )
    assert conn.queries == [("SELECT 1 FROM pg_database WHERE datname = $1", "tenant")] * 2
    assert conn.statements == ([] if already_exists else ['CREATE DATABASE "tenant"'])
    assert conn.closed == 2
    for call in driver.connect.await_args_list:
        assert call.args == ("postgresql://host/target",)
        assert call.kwargs == {"timeout": 5, "database": "postgres"}


@pytest.mark.parametrize("duplicate", [False, True])
async def test_database_create_failure_closes_connection_and_only_duplicate_succeeds(
    duplicate,
) -> None:
    class DuplicateDatabaseError(Exception):
        pass

    conn = RecordingConnection(
        execute_error=DuplicateDatabaseError() if duplicate else RuntimeError()
    )
    driver = SimpleNamespace(
        connect=AsyncMock(return_value=conn), DuplicateDatabaseError=DuplicateDatabaseError
    )
    assert (
        await ensure_postgres_database_exists(driver, "postgresql://host/admin", "tenant")
        is duplicate
    )
    assert conn.closed == 1


async def test_database_connection_failure_returns_false() -> None:
    driver = SimpleNamespace(connect=AsyncMock(side_effect=OSError("unavailable")))
    assert (
        await ensure_postgres_database_exists(driver, "postgresql://host/admin", "tenant") is False
    )


async def test_schema_failure_propagates_to_startup_owner() -> None:
    pool = RecordingConnection(execute_error=RuntimeError("DDL denied"))
    with pytest.raises(RuntimeError, match="DDL denied"):
        await ensure_realestate_schema(pool)


async def test_schema_bootstrap_executes_idempotent_application_ddl() -> None:
    pool = RecordingConnection()
    await ensure_realestate_schema(pool)
    first_run = pool.statements.copy()
    tables = {sql.split()[5] for sql in first_run if sql.startswith("CREATE TABLE IF NOT EXISTS ")}
    assert tables == {
        "users",
        "leads",
        "user_favorites",
        "search_events",
        "feedback_events",
        "lead_scores",
    }
    indexes = {sql.split()[5] for sql in first_run if sql.startswith("CREATE INDEX IF NOT EXISTS ")}
    assert indexes == {
        "idx_users_telegram_id",
        "idx_leads_user_id",
        "idx_leads_stage",
        "idx_user_favorites_telegram_id",
        "idx_user_favorites_created_at",
        "idx_search_events_user",
        "idx_feedback_events_user",
    }
    assert all(
        sql.startswith(("CREATE TABLE IF NOT EXISTS ", "CREATE INDEX IF NOT EXISTS "))
        for sql in first_run
    )
    await ensure_realestate_schema(pool)
    assert pool.statements == first_run * 2
    await ensure_realestate_schema(None)
