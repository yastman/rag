"""Append-only store for user feedback events (asyncpg) — #3422.

One redacted record per ``request_id``: the writer's signature is an explicit
allowlist (user/session/request linkage plus the enumerated action and the
fixed reason code), so a token, phone number, or raw user prompt cannot enter
the record. The feedback keyboard's ``trace_id`` is the pipeline
``request_id`` (``rag_result_store["request_id"]``, see
``telegram_bot.pipeline.supervisor``), which links every record to the
originating request; ``session_id`` reuses the production
``make_session_id("chat", chat_id)`` format.
"""

from __future__ import annotations

import logging
from typing import Any


logger = logging.getLogger(__name__)


class FeedbackEventStore:
    """Tracks per-request user feedback (like/dislike + optional reason).

    Mirrors the :class:`~telegram_bot.services.observability.search_event_store.SearchEventStore`
    append-only asyncpg pattern. The ``UNIQUE (request_id)`` contract makes a
    repeated callback idempotent — the insert refines the same single record
    (an optional reason updates it) instead of adding a second row.
    """

    def __init__(self, *, pool: Any) -> None:
        self._pool = pool

    async def append(
        self,
        *,
        user_id: int,
        session_id: str,
        request_id: str,
        action: str,
        reason: str | None = None,
    ) -> None:
        """Insert or refine the single feedback record for ``request_id``.

        ``action`` is ``"like"`` or ``"dislike"``; ``reason`` is one of the
        fixed ``_REASON_CODES`` values (or ``None``). There is no free-text
        payload parameter — banned keys cannot reach the table.
        """
        await self._pool.execute(
            """
            INSERT INTO feedback_events
                (user_id, session_id, request_id, action, reason)
            VALUES ($1, $2, $3, $4, $5)
            ON CONFLICT (request_id) DO UPDATE
                SET action = EXCLUDED.action,
                    reason = EXCLUDED.reason,
                    updated_at = NOW()
            """,
            user_id,
            session_id,
            request_id,
            action,
            reason,
        )


__all__ = ("FeedbackEventStore",)
