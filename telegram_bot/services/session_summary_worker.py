"""Session summary worker: detect idle sessions, generate summary, write to Kommo (#445).

Polls Redis for ``session:last_active:{user_id}`` keys older than ``idle_timeout_min``.
Generates summary via LLM, writes to Kommo as note (if available).

Worker lifecycle uses APScheduler interval job for periodic polling.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Awaitable, Callable
from typing import Any

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from telegram_bot.observability import get_client, observe


logger = logging.getLogger(__name__)

_SUMMARY_PROMPT = (
    "Summarize this customer conversation in 3-5 bullet points. "
    "Focus on: customer needs, property preferences, budget, next steps. "
    "Write in Russian."
)


HistorySource = Callable[[str], Awaitable[list[dict[str, str]]]]


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
        max_sessions_per_cycle: int = 50,
        history_source: HistorySource | None = None,
    ) -> None:
        self._redis = redis
        self._llm = llm
        self._kommo = kommo_client
        self._idle_timeout_min = idle_timeout_min
        self._poll_interval_sec = poll_interval_sec
        self._summary_model = summary_model
        self._max_sessions_per_cycle = max(1, max_sessions_per_cycle)
        self._history_source = history_source
        self._scheduler: AsyncIOScheduler | None = None

    async def start(self) -> None:
        """Start the background polling using APScheduler.

        Logs a warning when ``history_source`` is not wired (#1599) — the
        worker would otherwise start, scan idle sessions, and silently delete
        keys without ever generating a summary, which looked like the feature
        was running while it was actually a no-op.
        """
        self._scheduler = AsyncIOScheduler(
            job_defaults={"coalesce": True, "max_instances": 1, "misfire_grace_time": 300}
        )
        self._scheduler.add_job(
            self._check_idle_sessions,
            "interval",
            seconds=self._poll_interval_sec,
            id="session-summary-worker",
            replace_existing=True,
        )
        self._scheduler.start()
        if self._history_source is None:
            logger.warning(
                "SessionSummaryWorker started without history_source — idle "
                "sessions will be detected but summaries will NOT be generated "
                "until a real history retriever is wired. See issue #1599."
            )
            lf = get_client()
            if lf is not None:
                lf.score_current_trace(
                    name="session_summary_history_source_missing",
                    value=1,
                    data_type="BOOLEAN",
                )
        logger.info(
            "SessionSummaryWorker started (poll=%ds, idle=%dmin, history_source=%s)",
            self._poll_interval_sec,
            self._idle_timeout_min,
            "wired" if self._history_source is not None else "missing",
        )

    async def stop(self) -> None:
        """Shut down the scheduler."""
        if self._scheduler is not None:
            self._scheduler.shutdown(wait=False)
            self._scheduler = None
        logger.info("SessionSummaryWorker stopped")

    @observe(name="session-summary-check")
    async def _check_idle_sessions(self) -> int:
        """Scan Redis for idle sessions and process them.

        Streams SCAN pages and processes idle keys incrementally, capped by
        ``max_sessions_per_cycle`` (#1608). Excess work is deferred to the
        next worker tick so a large idle-user batch cannot trigger an
        unbounded burst of Redis reads, history fetches, LLM calls, and
        Kommo writes in a single cycle.

        Returns:
            Number of sessions summarized this cycle.
        """
        try:
            return await self._check_idle_sessions_inner()
        except Exception:
            logger.exception("SessionSummaryWorker cycle failed")
            raise

    async def _check_idle_sessions_inner(self) -> int:
        """Inner idle session check logic."""
        now = time.time()
        threshold = self._idle_timeout_min * 60
        count = 0
        scanned = 0
        deferred = 0
        cap = self._max_sessions_per_cycle
        cursor: int = 0
        cap_hit = False

        while not cap_hit:
            cursor, batch = await self._redis.scan(
                cursor=cursor, match="session:last_active:*", count=100
            )
            for key in batch:
                if scanned >= cap:
                    cap_hit = True
                    deferred += 1
                    continue

                raw = await self._redis.get(key)
                if raw is None:
                    continue

                last_active = float(raw)
                if now - last_active < threshold:
                    continue

                # Reserve a processing slot only after we know the key is idle —
                # active sessions do not count toward the per-cycle cap.
                scanned += 1

                user_id = (
                    key.decode().split(":")[-1] if isinstance(key, bytes) else key.split(":")[-1]
                )

                history = await self._get_conversation_history(user_id)
                if len(history) < 2:
                    await self._redis.delete(key)
                    continue

                summary = await self._generate_summary(history)
                if summary:
                    await self._write_summary(user_id, summary)
                    count += 1

                await self._redis.delete(key)

            if cursor == 0:
                break

        if cap_hit:
            logger.info(
                "SessionSummaryWorker reached per-cycle cap %d; deferring %d+ key(s) "
                "to next tick (poll=%ds).",
                cap,
                deferred,
                self._poll_interval_sec,
            )

        lf = get_client()
        if lf is not None:
            if count > 0:
                lf.score_current_trace(
                    name="session_summary_generated", value=1, data_type="BOOLEAN"
                )
                lf.score_current_trace(name="session_summary_count", value=float(count))
            if cap_hit:
                lf.score_current_trace(name="session_summary_cap_hit", value=1, data_type="BOOLEAN")

        return count

    async def _get_conversation_history(self, user_id: str) -> list[dict[str, str]]:
        """Fetch conversation history for ``user_id``.

        Delegates to the constructor-injected ``history_source`` callable when
        wired. Returns ``[]`` when no source is configured (worker is a no-op
        in that mode — see #1599 for the contract). Subclasses may still
        override this method directly for tests.
        """
        if self._history_source is not None:
            try:
                return await self._history_source(user_id)
            except Exception:
                logger.exception(
                    "history_source raised for user_id=%s; treating as empty history",
                    user_id,
                )
                return []
        return []

    @observe(name="session-summary-llm", capture_input=False, capture_output=False)
    async def _generate_summary(self, history: list[dict[str, str]]) -> str:
        """Generate a summary of the conversation via LLM.

        Wrapped in ``@observe`` (#1662) so the auto-traced generation produced
        by ``langfuse.openai`` becomes a child of a named ``session-summary-llm``
        span instead of a flat child of the outer ``session-summary-check``
        span. Curated ``update_current_span`` payloads avoid leaking full
        conversation history or full summary text into Langfuse.

        On LLM failure the span is recorded at ``level="ERROR"`` with a
        truncated ``status_message`` and the exception is re-raised; the outer
        ``_run_loop`` already swallows worker-cycle errors (#1662 plan step 4).
        Placeholder fallback for empty history is owned by ``#1599``/``#1608``
        and is intentionally not modified here.
        """
        lf = get_client()
        if lf is not None:
            lf.update_current_span(
                input={
                    "history_turns": len(history),
                    "model": self._summary_model,
                }
            )

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
            summary = response.choices[0].message.content or ""
            if lf is not None:
                lf.update_current_span(
                    output={
                        "summary_len": len(summary),
                        "summary_preview": summary[:120],
                    }
                )
            return summary
        except Exception as exc:
            logger.exception("Summary generation failed for session")
            if lf is not None:
                lf.update_current_span(
                    level="ERROR",
                    status_message=str(exc)[:200],
                )
            raise

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
