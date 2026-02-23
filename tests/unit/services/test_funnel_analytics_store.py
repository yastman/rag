from __future__ import annotations

import datetime as dt
from unittest.mock import AsyncMock

import pytest

from telegram_bot.services.funnel_analytics_store import FunnelAnalyticsStore


@pytest.mark.asyncio
async def test_fetch_stage_counts_queries_metric_date() -> None:
    pool = AsyncMock()
    rows = [{"stage_name": "inquiry", "entered_count": 10, "converted_count": 4}]
    pool.fetch.return_value = rows

    store = FunnelAnalyticsStore(pool=pool)
    result = await store.fetch_stage_counts(dt.date(2026, 2, 19))

    assert result == rows
    pool.fetch.assert_awaited_once()
    query, metric_date = pool.fetch.await_args.args
    assert "FROM funnel_events" in query
    assert metric_date == dt.date(2026, 2, 19)


@pytest.mark.asyncio
async def test_fetch_latest_summary_queries_daily_table() -> None:
    pool = AsyncMock()
    rows = [{"stage_name": "inquiry", "metric_date": dt.date(2026, 2, 19)}]
    pool.fetch.return_value = rows

    store = FunnelAnalyticsStore(pool=pool)
    result = await store.fetch_latest_summary()

    assert result == rows
    pool.fetch.assert_awaited_once()
    (query,) = pool.fetch.await_args.args
    assert "FROM funnel_metrics_daily" in query
    assert "MAX(metric_date)" in query
