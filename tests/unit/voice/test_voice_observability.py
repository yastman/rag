"""Tests for voice observability helpers."""

from __future__ import annotations

import inspect
from unittest.mock import patch

from src.voice.observability import (
    build_voice_trace_metadata,
    trace_voice_session,
    update_voice_trace,
    voice_session_id,
)


def test_voice_session_id_handles_missing_call_id() -> None:
    assert voice_session_id(None) == "voice-unknown"
    assert voice_session_id("  123 ") == "voice-123"


def test_build_voice_trace_metadata_omits_optional_fields_when_empty() -> None:
    assert build_voice_trace_metadata(call_id="c1", status="answered") == {
        "call_id": "c1",
        "status": "answered",
    }


def test_update_voice_trace_sets_trace_context() -> None:
    with patch("src.voice.observability.update_lifecycle_trace") as update_trace:
        update_voice_trace(call_id="call-42", status="completed", duration_sec=9)

    update_trace.assert_called_once_with(
        family="voice",
        span_name="voice-session",
        session_id="voice-call-42",
        user_id="voice-agent",
        tags=["voice", "call-lifecycle"],
        metadata={"call_id": "call-42", "status": "completed", "duration_sec": 9},
        trace_id=None,
    )


def test_trace_voice_session_is_not_wrapped_in_second_observation_layer() -> None:
    assert not hasattr(trace_voice_session, "__wrapped__")
    assert inspect.iscoroutinefunction(trace_voice_session)
