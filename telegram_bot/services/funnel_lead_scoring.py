"""Persist lead score from funnel answers and run side effects."""

from __future__ import annotations

import json
import logging
from typing import Any

from telegram_bot.services.lead_score_sync import sync_pending_lead_scores
from telegram_bot.services.lead_scoring import classify_lead, compute_lead_score
from telegram_bot.services.lead_scoring_models import LeadScoreRecord


logger = logging.getLogger(__name__)


def _build_reason_codes(
    *, property_type: str | None, budget: str | None, timeline: str | None
) -> list[str]:
    codes: list[str] = []
    if timeline:
        codes.append(f"timeline_{timeline}")
    if budget:
        codes.append("budget_defined")
    if property_type and property_type != "looking":
        codes.append(f"property_type_{property_type}")
    return codes


async def persist_and_sync_funnel_lead_score(
    *,
    telegram_user_id: int,
    session_id: str,
    property_type: str | None,
    budget: str | None,
    timeline: str | None,
    user_service: Any,
    pg_pool: Any,
    lead_scoring_store: Any,
    kommo_client: Any,
    hot_lead_notifier: Any,
    config: Any,
) -> dict[str, Any]:
    """Compute score from funnel data, persist it, sync it, and notify managers."""
    if user_service is None or pg_pool is None or lead_scoring_store is None:
        return {"persisted": False}

    user = await user_service.get_or_create(telegram_id=telegram_user_id)
    user_id = getattr(user, "id", None)
    if user_id is None:
        return {"persisted": False}

    score_value = compute_lead_score(property_type=property_type, budget=budget, timeline=timeline)
    score_band = classify_lead(score_value)
    reason_codes = _build_reason_codes(
        property_type=property_type, budget=budget, timeline=timeline
    )
    preferences = {
        "property_type": property_type,
        "budget": budget,
        "timeline": timeline,
    }

    row = await pg_pool.fetchrow(
        """
        SELECT id, kommo_lead_id
        FROM leads
        WHERE user_id = $1
        ORDER BY updated_at DESC
        LIMIT 1
        """,
        user_id,
    )
    if row is None:
        row = await pg_pool.fetchrow(
            """
            INSERT INTO leads (user_id, stage, score, preferences)
            VALUES ($1, $2, $3, $4::jsonb)
            RETURNING id, kommo_lead_id
            """,
            user_id,
            score_band,
            score_value,
            json.dumps(preferences),
        )
    else:
        row = await pg_pool.fetchrow(
            """
            UPDATE leads
            SET stage = $2,
                score = $3,
                preferences = COALESCE(preferences, '{}'::jsonb) || $4::jsonb,
                updated_at = now()
            WHERE id = $1
            RETURNING id, kommo_lead_id
            """,
            int(row["id"]),
            score_band,
            score_value,
            json.dumps(preferences),
        )

    lead_id = int(row["id"])
    kommo_lead_id = row["kommo_lead_id"]

    await lead_scoring_store.upsert_score(
        LeadScoreRecord(
            lead_id=lead_id,
            user_id=int(user_id),
            session_id=session_id,
            score_value=score_value,
            score_band=score_band,
            reason_codes=reason_codes,
            kommo_lead_id=int(kommo_lead_id) if kommo_lead_id is not None else None,
        )
    )

    sync_result = await sync_pending_lead_scores(
        scoring_store=lead_scoring_store,
        kommo_client=kommo_client,
        score_field_id=int(getattr(config, "kommo_lead_score_field_id", 0) or 0),
        band_field_id=int(getattr(config, "kommo_lead_band_field_id", 0) or 0),
        limit=20,
    )

    notified = False
    threshold = int(getattr(config, "manager_hot_lead_threshold", 60) or 60)
    if hot_lead_notifier is not None and score_value >= threshold:
        try:
            notified = await hot_lead_notifier.notify_if_hot(
                {"lead_id": lead_id, "score": score_value, "session_id": session_id}
            )
        except Exception:
            logger.exception("Failed to notify managers for hot lead %s", lead_id)

    return {
        "persisted": True,
        "lead_id": lead_id,
        "score_value": score_value,
        "score_band": score_band,
        "notified": notified,
        **sync_result,
    }
