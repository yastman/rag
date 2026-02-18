"""Tests for #384 dependency contract enforcement in NurturingService (#390)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from telegram_bot.services.nurturing_service import NurturingService


def _make_row(**kwargs):
    row = MagicMock()
    row.__getitem__ = lambda _self, k: kwargs[k]
    row.keys = lambda: kwargs.keys()
    return row


@pytest.fixture
def fake_pool_without_384_columns():
    """Pool where information_schema query returns None (columns missing)."""
    pool = AsyncMock()
    pool.fetchrow = AsyncMock(return_value=None)
    pool.fetch = AsyncMock(return_value=[])
    pool.executemany = AsyncMock()
    return pool


@pytest.fixture
def fake_pool_with_384_columns():
    """Pool where information_schema query confirms columns exist."""
    pool = AsyncMock()
    pool.fetchrow = AsyncMock(return_value={"count": 3})
    pool.fetch = AsyncMock(
        return_value=[
            _make_row(
                id=1,
                lead_id=10,
                score_band="warm",
                sync_status="synced",
                kommo_lead_id=5001,
                user_id=99,
                preferences={},
            )
        ]
    )
    pool.executemany = AsyncMock()
    return pool


@pytest.mark.asyncio
async def test_nurturing_service_fails_fast_when_384_columns_missing(
    fake_pool_without_384_columns,
):
    svc = NurturingService(pool=fake_pool_without_384_columns)

    with pytest.raises(RuntimeError, match="lead_scores contract from #384 is missing"):
        await svc.select_candidates(limit=10)


@pytest.mark.asyncio
async def test_nurturing_service_succeeds_when_384_columns_present(
    fake_pool_with_384_columns,
):
    svc = NurturingService(pool=fake_pool_with_384_columns)
    candidates = await svc.select_candidates(limit=10)

    assert len(candidates) == 1
    assert candidates[0].score_band == "warm"
