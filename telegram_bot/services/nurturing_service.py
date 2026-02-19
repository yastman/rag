"""Nurturing service: candidate selection + batch enqueue (#390).

Consumes #384 lead_scores (score_band, sync_status) for targeting.
Uses executemany for bulk insert performance.
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from typing import Any

from telegram_bot.observability import observe


logger = logging.getLogger(__name__)


class _Candidate:
    """Lightweight candidate DTO from lead_scores + leads join."""

    __slots__ = (
        "id",
        "kommo_lead_id",
        "lead_id",
        "preferences",
        "score_band",
        "sync_status",
        "user_id",
    )

    def __init__(self, row: Any) -> None:
        self.id: int = row["id"]
        self.lead_id: int = row["lead_id"]
        self.score_band: str = row["score_band"]
        self.sync_status: str = row["sync_status"]
        self.kommo_lead_id: int | None = row["kommo_lead_id"]
        self.user_id: int = row["user_id"]
        self.preferences: dict[str, Any] = row["preferences"] or {}


class NurturingService:
    """Select warm/cold leads and enqueue nurturing jobs."""

    def __init__(self, *, pool: Any) -> None:
        self._pool = pool

    async def _assert_384_contract(self) -> None:
        """Fail fast if lead_scores table is missing #384 columns."""
        row = await self._pool.fetchrow(
            """
            SELECT 1
            FROM information_schema.columns
            WHERE table_name = 'lead_scores'
              AND column_name IN ('score_band', 'sync_status', 'kommo_lead_id')
            GROUP BY table_name
            HAVING COUNT(*) = 3
            """
        )
        if row is None:
            raise RuntimeError("lead_scores contract from #384 is missing")

    async def select_candidates(self, *, limit: int) -> list[_Candidate]:
        """Fetch warm/cold synced leads eligible for nurturing."""
        await self._assert_384_contract()
        rows = await self._pool.fetch(
            """
            SELECT ls.id, ls.lead_id, ls.score_band, ls.sync_status, ls.kommo_lead_id,
                   l.user_id, l.preferences
            FROM lead_scores ls
            JOIN leads l ON l.id = ls.lead_id
            WHERE ls.score_band IN ('warm', 'cold')
              AND ls.sync_status = 'synced'
            ORDER BY ls.updated_at DESC
            LIMIT $1
            """,
            limit,
        )
        return [_Candidate(r) for r in rows]

    async def enqueue_updates(
        self,
        *,
        candidates: list[_Candidate],
        scheduled_for: datetime,
    ) -> None:
        """Bulk-insert nurturing jobs using executemany (asyncpg optimised)."""
        records = [
            (
                c.id,
                scheduled_for,
                json.dumps({"user_id": c.user_id, "preferences": c.preferences}),
            )
            for c in candidates
        ]
        await self._pool.executemany(
            """
            INSERT INTO nurturing_jobs (lead_score_id, scheduled_for, payload)
            VALUES ($1, $2, $3::jsonb)
            ON CONFLICT (lead_score_id, scheduled_for) DO NOTHING
            """,
            records,
        )

    @observe(name="nurturing-batch-run")
    async def run_once(self, *, limit: int = 100) -> int:
        """Select candidates, enqueue, return count."""
        candidates = await self.select_candidates(limit=limit)
        if not candidates:
            return 0
        scheduled_for = datetime.now(UTC)
        await self.enqueue_updates(candidates=candidates, scheduled_for=scheduled_for)
        logger.info("Nurturing batch enqueued: %d candidates", len(candidates))
        return len(candidates)
