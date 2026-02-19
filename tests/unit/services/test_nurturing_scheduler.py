"""Tests for NurturingScheduler (#390)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from telegram_bot.services.nurturing_scheduler import NurturingScheduler


@pytest.fixture
def fake_services():
    config = MagicMock()
    config.nurturing_interval_minutes = 60
    config.funnel_rollup_cron = "15 * * * *"
    config.nurturing_dispatch_enabled = False
    return {
        "nurturing_service": AsyncMock(),
        "analytics_service": AsyncMock(),
        "lease_store": AsyncMock(),
        "config": config,
    }


@pytest.mark.asyncio
async def test_scheduler_configures_single_instance_coalesced_jobs(fake_services):
    scheduler = NurturingScheduler(**fake_services)
    await scheduler.start()

    assert scheduler.has_job("nurturing-batch")
    assert scheduler.has_job("funnel-analytics-rollup")

    await scheduler.stop()


@pytest.mark.asyncio
async def test_scheduler_has_no_jobs_before_start(fake_services):
    scheduler = NurturingScheduler(**fake_services)

    assert not scheduler.has_job("nurturing-batch")
    assert not scheduler.has_job("funnel-analytics-rollup")


@pytest.mark.asyncio
async def test_scheduler_stop_is_idempotent(fake_services):
    scheduler = NurturingScheduler(**fake_services)
    await scheduler.start()
    await scheduler.stop()
    # Second stop should not raise
    await scheduler.stop()


@pytest.mark.asyncio
async def test_scheduler_uses_funnel_rollup_cron_from_config(fake_services):
    fake_services["config"].funnel_rollup_cron = "7 * * * *"
    scheduler = NurturingScheduler(**fake_services)
    await scheduler.start()

    job = scheduler._scheduler.get_job("funnel-analytics-rollup")
    assert job is not None
    assert "minute='7'" in str(job.trigger)

    await scheduler.stop()
