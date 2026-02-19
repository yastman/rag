"""Postgres store for lead scoring persistence and sync queue (#384).

Pool callers should configure command_timeout=30 to prevent runaway queries.
"""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING, Any

from telegram_bot.observability import observe
from telegram_bot.services.lead_scoring_models import LeadScoreRecord


if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


class LeadScoringStore:
    """Upsert scores and manage the pending-sync queue."""

    def __init__(self, *, pool: Any) -> None:
        self._pool = pool

    @observe(name="lead-score-upsert")
    async def upsert_score(self, rec: LeadScoreRecord) -> None:
        """Insert or update a lead score (resets sync_status to pending)."""
        await self._pool.execute(
            """
            INSERT INTO lead_scores
                (lead_id, user_id, session_id, score_value, score_band,
                 reason_codes, kommo_lead_id)
            VALUES ($1, $2, $3, $4, $5, $6::jsonb, $7)
            ON CONFLICT (lead_id) DO UPDATE SET
                score_value = EXCLUDED.score_value,
                score_band = EXCLUDED.score_band,
                reason_codes = EXCLUDED.reason_codes,
                kommo_lead_id = EXCLUDED.kommo_lead_id,
                sync_status = 'pending',
                updated_at = now();
            """,
            rec.lead_id,
            rec.user_id,
            rec.session_id,
            rec.score_value,
            rec.score_band,
            json.dumps(rec.reason_codes),
            rec.kommo_lead_id,
        )

    async def list_pending_sync(self, *, limit: int) -> list[LeadScoreRecord]:
        """Return up to *limit* scores awaiting Kommo sync."""
        rows = await self._pool.fetch(
            """
            SELECT lead_id, user_id, session_id, score_value, score_band,
                   reason_codes, kommo_lead_id
            FROM lead_scores
            WHERE sync_status = 'pending'
            ORDER BY updated_at ASC
            LIMIT $1
            """,
            limit,
        )
        results: list[LeadScoreRecord] = []
        for r in rows:
            raw_codes = r["reason_codes"]
            if isinstance(raw_codes, str):
                raw_codes = json.loads(raw_codes)
            results.append(
                LeadScoreRecord(
                    lead_id=r["lead_id"],
                    user_id=r["user_id"],
                    session_id=r["session_id"],
                    score_value=r["score_value"],
                    score_band=r["score_band"],
                    reason_codes=raw_codes,
                    kommo_lead_id=r["kommo_lead_id"],
                )
            )
        return results

    async def mark_synced(self, *, lead_id: int) -> None:
        """Mark a score as successfully synced to Kommo."""
        await self._pool.execute(
            """
            UPDATE lead_scores
            SET sync_status = 'synced', last_synced_at = now(), updated_at = now()
            WHERE lead_id = $1;
            """,
            lead_id,
        )

    async def mark_failed(self, *, lead_id: int, error: str) -> None:
        """Mark a score sync as failed."""
        await self._pool.execute(
            """
            UPDATE lead_scores
            SET sync_status = 'failed',
                sync_attempts = sync_attempts + 1,
                sync_error = $2,
                updated_at = now()
            WHERE lead_id = $1;
            """,
            lead_id,
            error,
        )
