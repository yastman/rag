"""Tests for voice observability helpers."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from src.voice.observability import build_voice_trace_metadata, update_voice_trace, voice_session_id


def test_voice_session_id_handles_missing_call_id() -> None:
    assert voice_session_id(None) == "voice-unknown"
    assert voice_session_id("  123 ") == "voice-123"


def test_build_voice_trace_metadata_omits_optional_fields_when_empty() -> None:
    assert build_voice_trace_metadata(call_id="c1", status="answered") == {
        "call_id": "c1",
        "status": "answered",
    }


def test_update_voice_trace_sets_trace_context() -> None:
    mock_lf = MagicMock()
    mock_context = MagicMock()
    mock_context.__enter__ = MagicMock(return_value=None)
    mock_context.__exit__ = MagicMock(return_value=None)

    with (
        patch("src.voice.observability.get_client", return_value=mock_lf),
        patch(
            "src.voice.observability.propagate_attributes", return_value=mock_context
        ) as mock_prop,
    ):
        update_voice_trace(call_id="call-42", status="completed", duration_sec=9)

    mock_prop.assert_called_once()
    mock_lf.update_current_trace.assert_called_once()
    assert mock_lf.update_current_trace.call_args.kwargs["session_id"] == "voice-call-42"
