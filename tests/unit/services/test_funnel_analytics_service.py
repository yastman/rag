"""Tests for FunnelAnalyticsService (#390)."""

from __future__ import annotations

import datetime as dt
from unittest.mock import AsyncMock, MagicMock

import pytest

from telegram_bot.services.funnel_analytics_service import FunnelAnalyticsService


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
            _make_row(stage_name="inquiry", entered_count=100, converted_count=40),
            _make_row(stage_name="viewing", entered_count=40, converted_count=10),
        ]
    )
    pool.execute = AsyncMock()
    pool.executemany = AsyncMock()
    return pool


@pytest.mark.asyncio
async def test_daily_snapshot_computes_conversion_and_dropoff(fake_pool):
    svc = FunnelAnalyticsService(pool=fake_pool)
    snapshots = await svc.build_daily_snapshot(metric_date=dt.date(2026, 2, 18))

    assert len(snapshots) == 2
    first = snapshots[0]
    assert first["stage_name"] == "inquiry"
    assert first["entered_count"] == 100
    assert first["converted_count"] == 40
    assert first["dropoff_count"] == 60
    assert 0 <= first["conversion_rate"] <= 1


@pytest.mark.asyncio
async def test_daily_snapshot_empty_returns_empty_list(fake_pool):
    fake_pool.fetch = AsyncMock(return_value=[])
    svc = FunnelAnalyticsService(pool=fake_pool)
    snapshots = await svc.build_daily_snapshot(metric_date=dt.date(2026, 2, 18))

    assert snapshots == []


@pytest.mark.asyncio
async def test_daily_snapshot_zero_entered_gives_zero_rate(fake_pool):
    fake_pool.fetch = AsyncMock(
        return_value=[_make_row(stage_name="demo", entered_count=0, converted_count=0)]
    )
    svc = FunnelAnalyticsService(pool=fake_pool)
    snapshots = await svc.build_daily_snapshot(metric_date=dt.date(2026, 2, 18))

    assert len(snapshots) == 1
    assert snapshots[0]["conversion_rate"] == 0.0
    assert snapshots[0]["dropoff_count"] == 0


@pytest.mark.asyncio
async def test_persist_snapshots_calls_executemany(fake_pool):
    svc = FunnelAnalyticsService(pool=fake_pool)
    snapshots = [
        {
            "metric_date": dt.date(2026, 2, 18),
            "stage_name": "inquiry",
            "entered_count": 100,
            "converted_count": 40,
            "dropoff_count": 60,
            "conversion_rate": 0.4,
        }
    ]
    await svc.persist_snapshots(snapshots=snapshots)

    fake_pool.executemany.assert_called_once()
    sql = fake_pool.executemany.call_args[0][0]
    assert "funnel_metrics_daily" in sql


@pytest.mark.asyncio
async def test_get_latest_summary_delegates_to_store(fake_pool):
    fake_pool.fetch = AsyncMock(
        return_value=[
            _make_row(
                stage_name="inquiry",
                entered_count=100,
                converted_count=40,
                dropoff_count=60,
                conversion_rate=0.4,
                metric_date=dt.date(2026, 2, 18),
            )
        ]
    )
    svc = FunnelAnalyticsService(pool=fake_pool)
    summary = await svc.get_latest_summary()

    assert len(summary) >= 1
    fake_pool.fetch.assert_called_once()
