"""Postgres store for funnel analytics queries (#390)."""

from __future__ import annotations

import datetime as dt
from typing import Any


class FunnelAnalyticsStore:
    """Read funnel event counts and persist daily metric snapshots."""

    def __init__(self, *, pool: Any) -> None:
        self._pool = pool

    async def fetch_stage_counts(self, metric_date: dt.date) -> list[Any]:
        """Aggregate entered/converted counts per stage for a given date."""
        return await self._pool.fetch(
            """
            SELECT stage_name,
                   COUNT(*) FILTER (WHERE event_type = 'entered') AS entered_count,
                   COUNT(*) FILTER (WHERE event_type = 'converted') AS converted_count
            FROM funnel_events
            WHERE DATE(created_at) = $1
            GROUP BY stage_name
            """,
            metric_date,
        )

    async def fetch_latest_summary(self) -> list[Any]:
        """Return the most recent daily snapshot rows."""
        return await self._pool.fetch(
            """
            SELECT stage_name, entered_count, converted_count, dropoff_count,
                   conversion_rate, metric_date
            FROM funnel_metrics_daily
            WHERE metric_date = (SELECT MAX(metric_date) FROM funnel_metrics_daily)
            ORDER BY stage_name
            """
        )
