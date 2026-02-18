"""Tests for NurturingService (#390)."""

from __future__ import annotations

import datetime as dt
from unittest.mock import AsyncMock, MagicMock

import pytest

from telegram_bot.services.nurturing_service import NurturingService


def _make_row(**kwargs):
    """Create a dict-like mock mimicking asyncpg Record."""
    row = MagicMock()
    row.__getitem__ = lambda _self, k: kwargs[k]
    row.keys = lambda: kwargs.keys()
    return row


@pytest.fixture
def fake_pool():
    pool = AsyncMock()
    pool.fetch = AsyncMock(
        return_value=[
            _make_row(
                id=1,
                lead_id=10,
                score_band="warm",
                sync_status="synced",
                kommo_lead_id=5001,
                user_id=99,
                preferences={"budget": "100k"},
            ),
            _make_row(
                id=2,
                lead_id=20,
                score_band="cold",
                sync_status="synced",
                kommo_lead_id=5002,
                user_id=100,
                preferences={},
            ),
        ]
    )
    pool.execute = AsyncMock()
    pool.executemany = AsyncMock()
    pool.fetchrow = AsyncMock(return_value={"count": 3})
    return pool


@pytest.mark.asyncio
async def test_select_candidates_uses_warm_and_cold_synced_scores(fake_pool):
    svc = NurturingService(pool=fake_pool)
    candidates = await svc.select_candidates(limit=25)

    assert len(candidates) == 2
    assert all(c.score_band in {"warm", "cold"} for c in candidates)
    assert all(c.sync_status == "synced" for c in candidates)

    sql = fake_pool.fetch.call_args[0][0]
    assert "score_band IN ('warm', 'cold')" in sql
    assert "sync_status = 'synced'" in sql


@pytest.mark.asyncio
async def test_enqueue_updates_uses_executemany(fake_pool):
    svc = NurturingService(pool=fake_pool)
    candidates = await svc.select_candidates(limit=25)

    scheduled_for = dt.datetime(2026, 2, 18, 12, 0, tzinfo=dt.UTC)
    await svc.enqueue_updates(candidates=candidates, scheduled_for=scheduled_for)

    fake_pool.executemany.assert_called_once()
    sql = fake_pool.executemany.call_args[0][0]
    assert "nurturing_jobs" in sql
    assert "ON CONFLICT" in sql

    records = fake_pool.executemany.call_args[0][1]
    assert len(records) == 2


@pytest.mark.asyncio
async def test_run_once_selects_and_enqueues(fake_pool):
    svc = NurturingService(pool=fake_pool)
    count = await svc.run_once(limit=25)

    assert count == 2
    fake_pool.fetch.assert_called_once()
    fake_pool.executemany.assert_called_once()
