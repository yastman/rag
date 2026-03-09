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
    """Select warm/cold leads, enqueue nurturing jobs, and dispatch messages."""

    def __init__(
        self,
        *,
        pool: Any,
        bot: Any | None = None,
        qdrant: Any | None = None,
        llm: Any | None = None,
        model: str = "claude-haiku-4-5",
    ) -> None:
        self._pool = pool
        self._bot = bot
        self._qdrant = qdrant
        self._llm = llm
        self._model = model

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

    async def dispatch_pending(self, *, batch_size: int = 20) -> int:
        """Pick up pending nurturing jobs and send messages via bot.

        Returns:
            Number of messages successfully sent.
        """
        if self._bot is None:
            logger.warning("NurturingDispatch: bot not configured, skipping")
            return 0

        rows = await self._pool.fetch(
            """
            SELECT id, user_id, payload, status
            FROM nurturing_jobs
            WHERE status = 'pending'
              AND scheduled_for <= now()
            ORDER BY scheduled_for ASC
            LIMIT $1
            """,
            batch_size,
        )
        if not rows:
            return 0

        sent = 0
        for row in rows:
            user_id = row["user_id"]
            payload = (
                json.loads(row["payload"]) if isinstance(row["payload"], str) else row["payload"]
            )
            try:
                message = await self._generate_nurturing_message(payload.get("preferences", {}))
                await self._bot.send_message(chat_id=user_id, text=message)
                await self._pool.execute(
                    "UPDATE nurturing_jobs SET status = 'sent' WHERE id = $1", row["id"]
                )
                sent += 1
            except Exception:
                logger.exception("Failed to dispatch nurturing job %d", row["id"])
                await self._pool.execute(
                    "UPDATE nurturing_jobs SET status = 'failed' WHERE id = $1", row["id"]
                )
        logger.info("NurturingDispatch: sent %d/%d", sent, len(rows))
        return sent

    @observe(name="nurturing-llm-generate", capture_input=False, capture_output=False)
    async def _generate_nurturing_message(self, preferences: dict[str, Any]) -> str:
        """Generate personalized nurturing message via LLM or template fallback."""
        prefs_text = ", ".join(f"{k}: {v}" for k, v in preferences.items()) or "general interest"
        if self._llm is None:
            return (
                f"Здравствуйте! У нас есть новые предложения по вашим предпочтениям: {prefs_text}"
            )
        try:
            response = await self._llm.chat.completions.create(
                model=self._model,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "Generate a short, friendly real estate nurturing message in Russian "
                            "based on client preferences."
                        ),
                    },
                    {"role": "user", "content": f"Client preferences: {prefs_text}"},
                ],
                max_tokens=200,
                name="nurturing-message",
            )
            return response.choices[0].message.content or f"Новые предложения: {prefs_text}"
        except Exception:
            logger.warning("LLM nurturing message failed, using template", exc_info=True)
            return (
                f"Здравствуйте! У нас есть новые предложения по вашим предпочтениям: {prefs_text}"
            )
