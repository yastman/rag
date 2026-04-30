"""Edge-case tests for lead_score_sync (#1090)."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from telegram_bot.services.lead_score_sync import sync_pending_lead_scores


@pytest.mark.asyncio
async def test_sync_pending_lead_scores_continues_after_failed_record() -> None:
    """sync_pending_lead_scores continues after one failed record and syncs a later record."""
    scoring_store = AsyncMock()
    kommo_client = AsyncMock()
    scoring_store.list_pending_sync.return_value = [
        SimpleNamespace(
            lead_id=1,
            session_id="s1",
            score_value=10,
            score_band="cold",
            kommo_lead_id=9001,
        ),
        SimpleNamespace(
            lead_id=2,
            session_id="s2",
            score_value=95,
            score_band="hot",
            kommo_lead_id=9002,
        ),
    ]
    # First call fails, second succeeds
    kommo_client.update_lead_score.side_effect = [
        RuntimeError("kommo down"),
        None,
    ]

    result = await sync_pending_lead_scores(
        scoring_store=scoring_store,
        kommo_client=kommo_client,
        score_field_id=1001,
        band_field_id=1002,
    )

    assert result == {"synced": 1, "failed": 1, "skipped": 0}
    assert kommo_client.update_lead_score.await_count == 2
    # Verify second record was synced
    second_call = kommo_client.update_lead_score.await_args_list[1].kwargs
    assert second_call["lead_id"] == 9002
    assert second_call["idempotency_key"] == "lead-score:2:s2:95:hot"
    scoring_store.mark_synced.assert_awaited_once_with(lead_id=2)
    scoring_store.mark_failed.assert_awaited_once_with(lead_id=1, error="kommo_error")
