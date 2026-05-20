"""Hot lead notification service (#388).

Sends Telegram messages to manager users when a hot lead is detected.
Deduplicates via Redis SET NX to avoid spamming on repeated events.
"""

from __future__ import annotations

import logging
from typing import Any

from telegram_bot.observability import get_client, observe


logger = logging.getLogger(__name__)


def _update_current_span(lf: Any, **kwargs: Any) -> None:
    """Update the current Langfuse span when tracing is available."""
    if lf is not None:
        lf.update_current_span(**kwargs)


class HotLeadNotifier:
    """Fan-out hot-lead alerts to configured manager Telegram IDs."""

    def __init__(
        self, *, bot: Any, cache: Any, manager_ids: list[int], dedupe_ttl_sec: int
    ) -> None:
        self._bot = bot
        self._cache = cache
        self._manager_ids = manager_ids
        self._dedupe_ttl_sec = dedupe_ttl_sec

    @observe(name="job-hot-lead-notify", capture_input=False, capture_output=False)
    async def notify_if_hot(self, payload: dict[str, Any]) -> bool:
        """Send notification to managers if lead is new (not deduped).

        Returns True if notification was sent, False if deduped or invalid.

        Wrapped in ``@observe`` (#1663) so each notification attempt emits a
        named Langfuse span. Curated ``update_current_span`` calls record only
        ``{lead_id, score, threshold}`` as input and ``{notified}`` as output;
        full payload dicts (which may carry phone/email/session_id metadata)
        are intentionally NOT captured.
        """
        lf = get_client()
        lead_id = payload.get("lead_id")
        session_id = payload.get("session_id")
        raw_score = payload.get("score", 0)
        try:
            score = int(raw_score)
        except (TypeError, ValueError):
            logger.warning("Invalid hot lead score %r; defaulting to 0", raw_score)
            score = 0

        _update_current_span(
            lf,
            input={
                "lead_id": lead_id,
                "score": score,
                "threshold": payload.get("threshold"),
            },
        )

        try:
            if not lead_id or not session_id:
                _update_current_span(lf, output={"notified": False})
                return False

            redis = getattr(self._cache, "redis", None)
            if redis is not None:
                key = f"hot-lead:{session_id}:{lead_id}"
                fresh = await redis.set(key, "1", ex=self._dedupe_ttl_sec, nx=True)
                if not fresh:
                    _update_current_span(lf, output={"notified": False})
                    return False

            text = f"Hot lead detected: lead_id={lead_id}, score={score}, session_id={session_id}"
            for manager_id in self._manager_ids:
                await self._bot.send_message(chat_id=manager_id, text=text)
            _update_current_span(lf, output={"notified": True})
            return True
        except Exception as exc:
            _update_current_span(lf, level="ERROR", status_message=str(exc)[:200])
            raise
