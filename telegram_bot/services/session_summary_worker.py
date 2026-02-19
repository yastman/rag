"""Session summary worker: detect idle sessions, generate summary, write to Kommo (#445).

Polls Redis for ``session:last_active:{user_id}`` keys older than ``idle_timeout_min``.
Generates summary via LLM, writes to Kommo as note (if available).

Worker lifecycle pattern matches ``RedisHealthMonitor``:
  start() -> asyncio.create_task(_run_loop()) -> stop() via asyncio.Event
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import time
from typing import Any

from telegram_bot.observability import get_client, observe


logger = logging.getLogger(__name__)

_SUMMARY_PROMPT = (
    "Summarize this customer conversation in 3-5 bullet points. "
    "Focus on: customer needs, property preferences, budget, next steps. "
    "Write in Russian."
)


class SessionSummaryWorker:
    """Background worker that detects idle sessions and generates LLM summaries."""

    def __init__(
        self,
        *,
        redis: Any,
        llm: Any,
        kommo_client: Any | None = None,
        idle_timeout_min: int = 30,
        poll_interval_sec: int = 300,
        summary_model: str = "claude-haiku-4-5",
    ) -> None:
        self._redis = redis
        self._llm = llm
        self._kommo = kommo_client
        self._idle_timeout_min = idle_timeout_min
        self._poll_interval_sec = poll_interval_sec
        self._summary_model = summary_model
        self._stop_event = asyncio.Event()
        self._task: asyncio.Task[None] | None = None

    async def start(self) -> None:
        """Start the background polling loop."""
        self._stop_event.clear()
        self._task = asyncio.create_task(self._run_loop(), name="session-summary-worker")
        logger.info(
            "SessionSummaryWorker started (poll=%ds, idle=%dmin)",
            self._poll_interval_sec,
            self._idle_timeout_min,
        )

    async def stop(self) -> None:
        """Signal the worker to stop and wait for it to finish."""
        self._stop_event.set()
        if self._task is not None:
            try:
                await asyncio.wait_for(self._task, timeout=5.0)
            except TimeoutError:
                self._task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await self._task
        logger.info("SessionSummaryWorker stopped")

    async def _run_loop(self) -> None:
        """Infinite poll loop until stop_event is set."""
        while not self._stop_event.is_set():
            try:
                await self._check_idle_sessions()
            except Exception:
                logger.exception("SessionSummaryWorker cycle failed")
            try:
                await asyncio.wait_for(
                    self._stop_event.wait(),
                    timeout=self._poll_interval_sec,
                )
                break  # stop_event was set
            except TimeoutError:
                pass  # normal: poll interval elapsed

    @observe(name="session-summary-check")
    async def _check_idle_sessions(self) -> int:
        """Scan Redis for idle sessions and process them.

        Returns:
            Number of sessions summarized.
        """
        now = time.time()
        threshold = self._idle_timeout_min * 60
        count = 0
        cursor: int = 0
        keys_to_process: list = []

        while True:
            cursor, batch = await self._redis.scan(
                cursor=cursor, match="session:last_active:*", count=100
            )
            keys_to_process.extend(batch)
            if cursor == 0:
                break

        if not keys_to_process:
            return 0

        for key in keys_to_process:
            raw = await self._redis.get(key)
            if raw is None:
                continue

            last_active = float(raw)
            if now - last_active < threshold:
                continue

            user_id = key.decode().split(":")[-1] if isinstance(key, bytes) else key.split(":")[-1]

            history = await self._get_conversation_history(user_id)
            if len(history) < 2:
                await self._redis.delete(key)
                continue

            summary = await self._generate_summary(history)
            if summary:
                await self._write_summary(user_id, summary)
                count += 1

            await self._redis.delete(key)

        lf = get_client()
        if count > 0:
            lf.score_current_trace(name="session_summary_generated", value=1, data_type="BOOLEAN")
            lf.score_current_trace(name="session_summary_count", value=float(count))

        return count

    async def _get_conversation_history(self, user_id: str) -> list[dict[str, str]]:
        """Fetch conversation history for a user.

        Placeholder: returns empty list until checkpointer integration is added.
        Override in tests or subclass for real history retrieval.
        """
        return []

    async def _generate_summary(self, history: list[dict[str, str]]) -> str:
        """Generate a summary of the conversation via LLM."""
        messages_text = "\n".join(f"{m['role']}: {m['content']}" for m in history)
        try:
            response = await self._llm.chat.completions.create(
                model=self._summary_model,
                messages=[
                    {"role": "system", "content": _SUMMARY_PROMPT},
                    {"role": "user", "content": messages_text},
                ],
                max_tokens=300,
                name="session-summary",
            )
            return response.choices[0].message.content or ""
        except Exception:
            logger.exception("Summary generation failed for session")
            return ""

    async def _write_summary(self, user_id: str, summary: str) -> None:
        """Log the summary and write to Kommo if available."""
        logger.info("Session summary for user %s: %s", user_id, summary[:100])
        if self._kommo:
            # TODO: resolve lead_id from user_id via lead scoring store (#445)
            lead_id: int | None = None
            if lead_id:
                try:
                    await self._kommo.add_note(
                        entity_type="leads",
                        entity_id=lead_id,
                        text=f"[Auto-summary]\n{summary}",
                    )
                except Exception:
                    logger.warning("Failed to write summary to Kommo", exc_info=True)
            else:
                logger.debug("Skipping Kommo note for user %s: lead_id not yet resolved", user_id)
