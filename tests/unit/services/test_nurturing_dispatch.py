"""Tests for NurturingService.dispatch_pending + NurturingScheduler dispatch job (#445)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from telegram_bot.services.nurturing_scheduler import NurturingScheduler
from telegram_bot.services.nurturing_service import NurturingService


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def nurturing_svc():
    pool = AsyncMock()
    bot = AsyncMock()
    qdrant = AsyncMock()
    llm = MagicMock()
    return NurturingService(pool=pool, bot=bot, qdrant=qdrant, llm=llm)


@pytest.fixture
def fake_services_dispatch():
    config = MagicMock()
    config.nurturing_interval_minutes = 60
    config.funnel_rollup_cron = "15 * * * *"
    config.nurturing_dispatch_enabled = True
    config.nurturing_dispatch_cron = "0 10 * * *"
    config.nurturing_dispatch_batch = 20
    return {
        "nurturing_service": AsyncMock(),
        "analytics_service": AsyncMock(),
        "lease_store": AsyncMock(),
        "config": config,
    }


# ---------------------------------------------------------------------------
# dispatch_pending tests
# ---------------------------------------------------------------------------


async def test_dispatch_no_pending(nurturing_svc):
    """dispatch_pending returns 0 when there are no pending jobs."""
    nurturing_svc._pool.fetch = AsyncMock(return_value=[])
    count = await nurturing_svc.dispatch_pending(batch_size=20)
    assert count == 0


async def test_dispatch_sends_message(nurturing_svc):
    """dispatch_pending sends Telegram message and marks job as sent."""
    nurturing_svc._pool.fetch = AsyncMock(
        return_value=[
            {
                "id": 1,
                "user_id": 42,
                "payload": '{"preferences": {"rooms": 2}}',
                "status": "pending",
            }
        ]
    )
    nurturing_svc._pool.execute = AsyncMock()
    nurturing_svc._generate_nurturing_message = AsyncMock(return_value="New 2-room apartments!")

    count = await nurturing_svc.dispatch_pending(batch_size=20)

    assert count == 1
    nurturing_svc._bot.send_message.assert_called_once_with(
        chat_id=42, text="New 2-room apartments!"
    )
    nurturing_svc._pool.execute.assert_called_once()
    sql = nurturing_svc._pool.execute.call_args[0][0]
    assert "sent" in sql


async def test_dispatch_handles_failure(nurturing_svc):
    """dispatch_pending marks job as failed when send_message raises."""
    nurturing_svc._pool.fetch = AsyncMock(
        return_value=[
            {
                "id": 5,
                "user_id": 99,
                "payload": '{"preferences": {}}',
                "status": "pending",
            }
        ]
    )
    nurturing_svc._pool.execute = AsyncMock()
    nurturing_svc._generate_nurturing_message = AsyncMock(return_value="Hello!")
    nurturing_svc._bot.send_message = AsyncMock(side_effect=RuntimeError("telegram error"))

    count = await nurturing_svc.dispatch_pending(batch_size=20)

    assert count == 0
    nurturing_svc._pool.execute.assert_called_once()
    sql = nurturing_svc._pool.execute.call_args[0][0]
    assert "failed" in sql


async def test_dispatch_without_bot(nurturing_svc):
    """dispatch_pending returns 0 immediately when bot is not configured."""
    nurturing_svc._bot = None
    nurturing_svc._pool.fetch = AsyncMock()

    count = await nurturing_svc.dispatch_pending(batch_size=20)

    assert count == 0
    nurturing_svc._pool.fetch.assert_not_called()


async def test_dispatch_multiple_jobs(nurturing_svc):
    """dispatch_pending handles multiple jobs in a single batch."""
    nurturing_svc._pool.fetch = AsyncMock(
        return_value=[
            {
                "id": 1,
                "user_id": 10,
                "payload": '{"preferences": {"rooms": 1}}',
                "status": "pending",
            },
            {
                "id": 2,
                "user_id": 20,
                "payload": '{"preferences": {"rooms": 3}}',
                "status": "pending",
            },
            {"id": 3, "user_id": 30, "payload": '{"preferences": {}}', "status": "pending"},
        ]
    )
    nurturing_svc._pool.execute = AsyncMock()
    nurturing_svc._generate_nurturing_message = AsyncMock(return_value="New listings!")

    count = await nurturing_svc.dispatch_pending(batch_size=20)

    assert count == 3
    assert nurturing_svc._bot.send_message.call_count == 3
    assert nurturing_svc._pool.execute.call_count == 3


# ---------------------------------------------------------------------------
# NurturingScheduler dispatch job tests
# ---------------------------------------------------------------------------


async def test_scheduler_registers_dispatch_job_when_enabled(fake_services_dispatch):
    """Scheduler registers nurturing-dispatch job when dispatch is enabled."""
    scheduler = NurturingScheduler(**fake_services_dispatch)
    await scheduler.start()

    assert scheduler.has_job("nurturing-dispatch")

    await scheduler.stop()


async def test_scheduler_no_dispatch_job_when_disabled(fake_services_dispatch):
    """Scheduler does not register nurturing-dispatch job when dispatch is disabled."""
    fake_services_dispatch["config"].nurturing_dispatch_enabled = False
    scheduler = NurturingScheduler(**fake_services_dispatch)
    await scheduler.start()

    assert not scheduler.has_job("nurturing-dispatch")

    await scheduler.stop()


async def test_run_nurturing_dispatch_calls_dispatch_pending(fake_services_dispatch):
    """run_nurturing_dispatch calls NurturingService.dispatch_pending with correct batch size."""
    nurturing_mock = fake_services_dispatch["nurturing_service"]
    nurturing_mock.dispatch_pending = AsyncMock(return_value=5)
    config = fake_services_dispatch["config"]
    config.nurturing_dispatch_batch = 15

    scheduler = NurturingScheduler(**fake_services_dispatch)
    await scheduler.start()
    await scheduler.run_nurturing_dispatch()

    nurturing_mock.dispatch_pending.assert_called_once_with(batch_size=15)

    await scheduler.stop()
