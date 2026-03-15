"""Tests for voice service schemas."""

from __future__ import annotations

from src.voice.schemas import CallRequest, CallResponse, CallStatus, TranscriptEntry


def test_call_request_defaults_lead_data_to_empty_dict() -> None:
    request = CallRequest(phone="+359123456")

    assert request.lead_data == {}
    assert request.callback_chat_id is None


def test_call_response_preserves_status_enum() -> None:
    response = CallResponse(call_id="call-1", status=CallStatus.ANSWERED)

    assert response.status is CallStatus.ANSWERED


def test_transcript_entry_keeps_timestamp() -> None:
    entry = TranscriptEntry(role="user", text="hello", timestamp_ms=123)

    assert entry.timestamp_ms == 123
