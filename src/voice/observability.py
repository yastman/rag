"""Voice tracing helpers for Langfuse lifecycle updates."""

from __future__ import annotations

import logging
from contextlib import suppress
from typing import Any

from telegram_bot.observability import get_client, observe, propagate_attributes


logger = logging.getLogger(__name__)

VOICE_TRACE_TAGS = ["voice", "call-lifecycle"]


def voice_session_id(call_id: str | None) -> str:
    """Build stable voice session id from call id."""
    raw = (call_id or "").strip()
    if not raw:
        return "voice-unknown"
    return f"voice-{raw}"


def build_voice_trace_metadata(
    *,
    call_id: str,
    status: str,
    duration_sec: int | None = None,
    error: str | None = None,
) -> dict[str, Any]:
    """Build lifecycle metadata payload for trace updates."""
    metadata: dict[str, Any] = {
        "call_id": call_id,
        "status": status,
    }
    if duration_sec is not None:
        metadata["duration_sec"] = duration_sec
    if error:
        metadata["error"] = error
    return metadata


def update_voice_trace(
    *,
    call_id: str,
    status: str,
    duration_sec: int | None = None,
    error: str | None = None,
    session_id: str | None = None,
    langfuse_trace_id: str | None = None,
) -> None:
    """Write lifecycle status onto active trace context."""
    resolved_session_id = session_id or voice_session_id(call_id)
    metadata = build_voice_trace_metadata(
        call_id=call_id,
        status=status,
        duration_sec=duration_sec,
        error=error,
    )
    trace_kwargs: dict[str, Any] = {
        "session_id": resolved_session_id,
        "user_id": "voice-agent",
        "tags": VOICE_TRACE_TAGS,
    }
    if langfuse_trace_id:
        trace_kwargs["trace_id"] = langfuse_trace_id

    with propagate_attributes(**trace_kwargs):
        lf = get_client()
        lf.update_current_trace(
            session_id=resolved_session_id,
            user_id="voice-agent",
            tags=VOICE_TRACE_TAGS,
            metadata=metadata,
        )


@observe(name="voice-session", capture_input=False, capture_output=False)
async def trace_voice_session(
    *,
    call_id: str,
    status: str,
    duration_sec: int | None = None,
    error: str | None = None,
    session_id: str | None = None,
    langfuse_trace_id: str | None = None,
) -> None:
    """Async wrapper used by voice runtime for lifecycle traces."""
    with suppress(Exception):
        update_voice_trace(
            call_id=call_id,
            status=status,
            duration_sec=duration_sec,
            error=error,
            session_id=session_id,
            langfuse_trace_id=langfuse_trace_id,
        )
