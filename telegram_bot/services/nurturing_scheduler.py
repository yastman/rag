"""APScheduler-based nurturing + funnel analytics scheduler (#390).

Uses APScheduler v3 AsyncIOScheduler with:
- coalesce=True: collapse missed runs into one
- max_instances=1: prevent concurrent duplicate runs
- misfire_grace_time=300: 5-min grace window for late execution

TODO(#390): Migrate to APScheduler v4 when stable (currently alpha 4.0.0a6).
  v4 changes: AsyncScheduler, AnyIO, add_schedule(IntervalTrigger),
  CoalescePolicy.latest, misfire_grace_time=timedelta(minutes=5).
  See research notes in docs/plans/2026-02-18-nurturing-funnel-390-plan.md.
"""

from __future__ import annotations

import logging
from typing import Any

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from telegram_bot.observability import observe


logger = logging.getLogger(__name__)


class NurturingScheduler:
    """Manage scheduled nurturing batches and funnel analytics rollups."""

    def __init__(
        self,
        *,
        nurturing_service: Any,
        analytics_service: Any,
        lease_store: Any,
        config: Any,
    ) -> None:
        self._scheduler = AsyncIOScheduler(
            job_defaults={
                "coalesce": True,
                "max_instances": 1,
                "misfire_grace_time": 300,
            }
        )
        self._nurturing = nurturing_service
        self._analytics = analytics_service
        self._lease_store = lease_store
        self._config = config
        self._started = False

    async def start(self) -> None:
        """Register jobs and start the scheduler."""
        self._scheduler.add_job(
            self.run_nurturing_batch,
            "interval",
            minutes=self._config.nurturing_interval_minutes,
            id="nurturing-batch",
            replace_existing=True,
        )
        self._scheduler.add_job(
            self.run_funnel_rollup,
            trigger=CronTrigger.from_crontab(self._config.funnel_rollup_cron),
            id="funnel-analytics-rollup",
            replace_existing=True,
        )
        if getattr(self._config, "nurturing_dispatch_enabled", False):
            self._scheduler.add_job(
                self.run_nurturing_dispatch,
                trigger=CronTrigger.from_crontab(
                    getattr(self._config, "nurturing_dispatch_cron", "0 10 * * *")
                ),
                id="nurturing-dispatch",
                replace_existing=True,
            )
        self._scheduler.start()
        self._started = True
        logger.info("NurturingScheduler started")

    async def stop(self) -> None:
        """Shutdown the scheduler if running."""
        if self._started:
            self._scheduler.shutdown(wait=False)
            self._started = False
            logger.info("NurturingScheduler stopped")

    def has_job(self, job_id: str) -> bool:
        """Check if a job is registered."""
        return self._scheduler.get_job(job_id) is not None

    @observe(name="nurturing-scheduler-tick")
    async def run_nurturing_batch(self) -> None:
        """Execute a single nurturing batch (called by scheduler)."""
        try:
            count = await self._nurturing.run_once(limit=100)
            logger.info("Nurturing batch completed: %d candidates", count)
        except Exception:
            logger.exception("Nurturing batch failed")

    async def run_nurturing_dispatch(self) -> None:
        """Dispatch pending nurturing messages (called by scheduler)."""
        try:
            batch = getattr(self._config, "nurturing_dispatch_batch", 20)
            count = await self._nurturing.dispatch_pending(batch_size=batch)
            logger.info("Nurturing dispatch completed: %d messages sent", count)
        except Exception:
            logger.exception("Nurturing dispatch failed")

    async def run_funnel_rollup(self) -> None:
        """Compute and persist daily funnel metrics (called by scheduler)."""
        import datetime as dt

        try:
            today = dt.date.today()
            snapshots = await self._analytics.build_daily_snapshot(metric_date=today)
            if snapshots:
                await self._analytics.persist_snapshots(snapshots=snapshots)
            logger.info("Funnel rollup completed: %d stages", len(snapshots))
        except Exception:
            logger.exception("Funnel rollup failed")
