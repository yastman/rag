"""Runtime helpers for syncing pending lead scores to Kommo CRM."""

from __future__ import annotations

import logging
from typing import Any

from telegram_bot.services.kommo_models import LeadScoreSyncPayload


logger = logging.getLogger(__name__)


async def sync_pending_lead_scores(
    *,
    scoring_store: Any,
    kommo_client: Any,
    score_field_id: int,
    band_field_id: int,
    limit: int = 20,
) -> dict[str, int]:
    """Sync pending lead scores to Kommo and return counters."""
    if scoring_store is None or kommo_client is None:
        return {"synced": 0, "failed": 0, "skipped": 0}
    if score_field_id <= 0 or band_field_id <= 0:
        return {"synced": 0, "failed": 0, "skipped": 0}

    pending = await scoring_store.list_pending_sync(limit=limit)
    synced = 0
    failed = 0
    skipped = 0

    for rec in pending:
        if rec.kommo_lead_id is None:
            skipped += 1
            continue
        key = f"lead-score:{rec.lead_id}:{rec.session_id}:{rec.score_value}:{rec.score_band}"
        payload = LeadScoreSyncPayload.from_record(
            rec,
            score_field_id=score_field_id,
            band_field_id=band_field_id,
        ).to_kommo_payload()
        try:
            await kommo_client.update_lead_score(
                lead_id=rec.kommo_lead_id,
                payload=payload,
                idempotency_key=key,
            )
            await scoring_store.mark_synced(lead_id=rec.lead_id)
            synced += 1
        except Exception:
            logger.exception("CRM score sync failed for lead %s", rec.lead_id)
            await scoring_store.mark_failed(lead_id=rec.lead_id, error="kommo_error")
            failed += 1

    return {"synced": synced, "failed": failed, "skipped": skipped}
