"""Voice tracing helpers for Langfuse lifecycle updates."""

from typing import Any

from src.observability import (
    make_lifecycle_session_id,
    observe,
    try_update_lifecycle_trace_async,
    update_lifecycle_trace,
)


VOICE_TRACE_TAGS = ["voice", "call-lifecycle"]


def voice_session_id(call_id: str | None) -> str:
    """Build stable voice session id from call id."""
    return make_lifecycle_session_id("voice", call_id or "")


def build_voice_trace_metadata(
    *, call_id: str, status: str, duration_sec: int | None = None, error: str | None = None
) -> dict[str, Any]:
    """Build lifecycle metadata payload for trace updates."""
    metadata: dict[str, Any] = {"call_id": call_id, "status": status}
    if duration_sec is not None:
        metadata["duration_sec"] = duration_sec
    if error:
        metadata["error"] = error
    return metadata


@observe(name="voice-session", capture_input=False, capture_output=False)
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
    metadata = build_voice_trace_metadata(
        call_id=call_id, status=status, duration_sec=duration_sec, error=error
    )
    update_lifecycle_trace(
        family="voice",
        span_name="voice-session",
        session_id=session_id or voice_session_id(call_id),
        user_id="voice-agent",
        tags=VOICE_TRACE_TAGS,
        metadata=metadata,
        trace_id=langfuse_trace_id,
    )


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
    metadata = build_voice_trace_metadata(
        call_id=call_id, status=status, duration_sec=duration_sec, error=error
    )
    await try_update_lifecycle_trace_async(
        family="voice",
        span_name="voice-session",
        session_id=session_id or voice_session_id(call_id),
        user_id="voice-agent",
        tags=VOICE_TRACE_TAGS,
        metadata=metadata,
        trace_id=langfuse_trace_id,
    )
