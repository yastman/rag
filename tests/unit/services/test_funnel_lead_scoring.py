from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from telegram_bot.services.funnel_lead_scoring import persist_and_sync_funnel_lead_score


@pytest.mark.asyncio
async def test_persist_and_sync_calls_hot_lead_notifier_for_hot_score():
    user_service = AsyncMock()
    user_service.get_or_create = AsyncMock(return_value=SimpleNamespace(id=7))

    pg_pool = AsyncMock()
    pg_pool.fetchrow = AsyncMock(
        side_effect=[
            None,
            {"id": 11, "kommo_lead_id": 5001},
        ]
    )

    lead_scoring_store = AsyncMock()
    lead_scoring_store.upsert_score = AsyncMock()
    lead_scoring_store.list_pending_sync = AsyncMock(
        return_value=[
            SimpleNamespace(
                lead_id=11,
                user_id=7,
                session_id="chat-1",
                score_value=70,
                score_band="hot",
                reason_codes=["timeline_asap"],
                kommo_lead_id=5001,
            )
        ]
    )
    lead_scoring_store.mark_synced = AsyncMock()
    lead_scoring_store.mark_failed = AsyncMock()

    kommo_client = AsyncMock()
    kommo_client.update_lead_score = AsyncMock(return_value={"id": 5001})

    hot_lead_notifier = AsyncMock()
    hot_lead_notifier.notify_if_hot = AsyncMock(return_value=True)

    config = SimpleNamespace(
        kommo_lead_score_field_id=701,
        kommo_lead_band_field_id=702,
        manager_hot_lead_threshold=60,
    )

    result = await persist_and_sync_funnel_lead_score(
        telegram_user_id=12345,
        session_id="chat-1",
        property_type="apartment",
        budget="mid",
        timeline="asap",
        user_service=user_service,
        pg_pool=pg_pool,
        lead_scoring_store=lead_scoring_store,
        kommo_client=kommo_client,
        hot_lead_notifier=hot_lead_notifier,
        config=config,
    )

    assert result["persisted"] is True
    assert result["score_band"] == "hot"
    lead_scoring_store.upsert_score.assert_called_once()
    kommo_client.update_lead_score.assert_called_once()
    hot_lead_notifier.notify_if_hot.assert_called_once()


@pytest.mark.asyncio
async def test_persist_and_sync_skips_if_runtime_services_missing():
    result = await persist_and_sync_funnel_lead_score(
        telegram_user_id=1,
        session_id="chat-1",
        property_type="apartment",
        budget="mid",
        timeline="asap",
        user_service=None,
        pg_pool=None,
        lead_scoring_store=None,
        kommo_client=None,
        hot_lead_notifier=None,
        config=SimpleNamespace(),
    )

    assert result == {"persisted": False}
