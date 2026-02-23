from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from telegram_bot.services.lead_score_sync import sync_pending_lead_scores


@pytest.mark.asyncio
async def test_sync_pending_lead_scores_returns_zero_when_dependencies_missing() -> None:
    result = await sync_pending_lead_scores(
        scoring_store=None,
        kommo_client=None,
        score_field_id=1,
        band_field_id=2,
    )

    assert result == {"synced": 0, "failed": 0, "skipped": 0}


@pytest.mark.asyncio
async def test_sync_pending_lead_scores_skips_invalid_field_ids() -> None:
    scoring_store = AsyncMock()
    kommo_client = AsyncMock()

    result = await sync_pending_lead_scores(
        scoring_store=scoring_store,
        kommo_client=kommo_client,
        score_field_id=0,
        band_field_id=2,
    )

    assert result == {"synced": 0, "failed": 0, "skipped": 0}
    scoring_store.list_pending_sync.assert_not_called()


@pytest.mark.asyncio
async def test_sync_pending_lead_scores_marks_synced_and_skipped() -> None:
    scoring_store = AsyncMock()
    kommo_client = AsyncMock()
    scoring_store.list_pending_sync.return_value = [
        SimpleNamespace(
            lead_id=11,
            session_id="s1",
            score_value=87,
            score_band="hot",
            kommo_lead_id=9011,
        ),
        SimpleNamespace(
            lead_id=12,
            session_id="s2",
            score_value=12,
            score_band="cold",
            kommo_lead_id=None,
        ),
    ]

    result = await sync_pending_lead_scores(
        scoring_store=scoring_store,
        kommo_client=kommo_client,
        score_field_id=1001,
        band_field_id=1002,
        limit=5,
    )

    assert result == {"synced": 1, "failed": 0, "skipped": 1}
    scoring_store.list_pending_sync.assert_awaited_once_with(limit=5)
    kommo_client.update_lead_score.assert_awaited_once()
    call = kommo_client.update_lead_score.await_args.kwargs
    assert call["lead_id"] == 9011
    assert call["idempotency_key"] == "lead-score:11:s1:87:hot"
    assert "custom_fields_values" in call["payload"]
    scoring_store.mark_synced.assert_awaited_once_with(lead_id=11)
    scoring_store.mark_failed.assert_not_called()


@pytest.mark.asyncio
async def test_sync_pending_lead_scores_marks_failed_on_kommo_error() -> None:
    scoring_store = AsyncMock()
    kommo_client = AsyncMock()
    scoring_store.list_pending_sync.return_value = [
        SimpleNamespace(
            lead_id=42,
            session_id="s3",
            score_value=50,
            score_band="warm",
            kommo_lead_id=9042,
        )
    ]
    kommo_client.update_lead_score.side_effect = RuntimeError("kommo down")

    result = await sync_pending_lead_scores(
        scoring_store=scoring_store,
        kommo_client=kommo_client,
        score_field_id=1001,
        band_field_id=1002,
    )

    assert result == {"synced": 0, "failed": 1, "skipped": 0}
    scoring_store.mark_failed.assert_awaited_once_with(lead_id=42, error="kommo_error")
    scoring_store.mark_synced.assert_not_called()
