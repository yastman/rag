"""Tests for LeadScoringStore (#384)."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from telegram_bot.services.lead_scoring_models import LeadScoreRecord
from telegram_bot.services.lead_scoring_store import LeadScoringStore


@pytest.fixture
def fake_pool():
    """Minimal asyncpg pool mock."""
    pool = AsyncMock()
    pool.execute = AsyncMock()

    # Return rows that look like asyncpg Records
    def _make_row(**kwargs):
        row = MagicMock()
        row.__getitem__ = lambda _self, k: kwargs[k]
        row.keys = lambda: kwargs.keys()
        # Allow dict(row) to work
        row.__iter__ = lambda _self: iter(kwargs.keys())
        # Make dict() constructor work via mapping protocol
        items = list(kwargs.items())
        row.items = lambda: items
        row.values = lambda: list(kwargs.values())
        return row

    pending_row = _make_row(
        lead_id=11,
        user_id=99,
        session_id="chat-1",
        score_value=74,
        score_band="hot",
        reason_codes=json.dumps(["timeline_asap"]),
        kommo_lead_id=5001,
    )
    pool.fetch = AsyncMock(return_value=[pending_row])
    return pool


@pytest.mark.asyncio
async def test_upsert_score_calls_execute(fake_pool):
    store = LeadScoringStore(pool=fake_pool)

    rec = LeadScoreRecord(
        lead_id=11,
        user_id=99,
        session_id="chat-1",
        score_value=74,
        score_band="hot",
        reason_codes=["timeline_asap"],
        kommo_lead_id=5001,
    )
    await store.upsert_score(rec)

    fake_pool.execute.assert_called_once()
    call_args = fake_pool.execute.call_args
    sql = call_args[0][0]
    assert "INSERT INTO lead_scores" in sql
    assert "ON CONFLICT" in sql


@pytest.mark.asyncio
async def test_list_pending_sync_returns_records(fake_pool):
    store = LeadScoringStore(pool=fake_pool)

    rows = await store.list_pending_sync(limit=10)

    assert len(rows) == 1
    assert rows[0].lead_id == 11
    assert rows[0].score_value == 74
    fake_pool.fetch.assert_called_once()
    sql = fake_pool.fetch.call_args[0][0]
    assert "sync_status = 'pending'" in sql


@pytest.mark.asyncio
async def test_mark_synced_updates_status(fake_pool):
    store = LeadScoringStore(pool=fake_pool)

    await store.mark_synced(lead_id=11)

    fake_pool.execute.assert_called_once()
    sql = fake_pool.execute.call_args[0][0]
    assert "sync_status" in sql
    assert "'synced'" in sql


@pytest.mark.asyncio
async def test_mark_failed_updates_status(fake_pool):
    store = LeadScoringStore(pool=fake_pool)

    await store.mark_failed(lead_id=11, error="timeout")

    fake_pool.execute.assert_called_once()
    sql = fake_pool.execute.call_args[0][0]
    assert "'failed'" in sql
