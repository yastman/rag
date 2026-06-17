from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from telegram_bot.services.funnel_lead_scoring import persist_and_sync_funnel_lead_score


@pytest.mark.asyncio
async def test_persist_and_sync_persists_score():
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

    config = SimpleNamespace(
        kommo_lead_score_field_id=701,
        kommo_lead_band_field_id=702,
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
        kommo_client=None,
        config=config,
    )

    assert result["persisted"] is True
    assert result["score_band"] == "hot"
    lead_scoring_store.upsert_score.assert_called_once()


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
        config=SimpleNamespace(),
    )

    assert result == {"persisted": False}
