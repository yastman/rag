"""Funnel analytics service: daily snapshot computation and persistence (#390)."""

from __future__ import annotations

import datetime as dt
import logging
from typing import Any

from telegram_bot.observability import observe
from telegram_bot.services.funnel_analytics_store import FunnelAnalyticsStore


logger = logging.getLogger(__name__)


class FunnelAnalyticsService:
    """Compute and persist funnel conversion/dropoff metrics."""

    def __init__(self, *, pool: Any) -> None:
        self._store = FunnelAnalyticsStore(pool=pool)
        self._pool = pool

    @observe(name="funnel-rollup")
    async def build_daily_snapshot(self, *, metric_date: dt.date) -> list[dict[str, Any]]:
        """Compute conversion/dropoff for each stage on the given date."""
        rows = await self._store.fetch_stage_counts(metric_date)
        snapshots: list[dict[str, Any]] = []
        for r in rows:
            entered = int(r["entered_count"] or 0)
            converted = int(r["converted_count"] or 0)
            dropoff = max(entered - converted, 0)
            rate = (converted / entered) if entered else 0.0
            snapshots.append(
                {
                    "metric_date": metric_date,
                    "stage_name": r["stage_name"],
                    "entered_count": entered,
                    "converted_count": converted,
                    "dropoff_count": dropoff,
                    "conversion_rate": round(rate, 4),
                }
            )
        return snapshots

    @observe(name="funnel-store-upsert")
    async def persist_snapshots(self, *, snapshots: list[dict[str, Any]]) -> None:
        """Upsert daily snapshot rows via executemany."""
        records = [
            (
                s["metric_date"],
                s["stage_name"],
                s["entered_count"],
                s["converted_count"],
                s["dropoff_count"],
                s["conversion_rate"],
            )
            for s in snapshots
        ]
        await self._pool.executemany(
            """
            INSERT INTO funnel_metrics_daily
                (metric_date, stage_name, entered_count, converted_count,
                 dropoff_count, conversion_rate)
            VALUES ($1, $2, $3, $4, $5, $6)
            ON CONFLICT (metric_date, stage_name) DO UPDATE SET
                entered_count = EXCLUDED.entered_count,
                converted_count = EXCLUDED.converted_count,
                dropoff_count = EXCLUDED.dropoff_count,
                conversion_rate = EXCLUDED.conversion_rate
            """,
            records,
        )

    async def get_latest_summary(self) -> list[Any]:
        """Return latest daily snapshot for display / tool output."""
        return await self._store.fetch_latest_summary()
