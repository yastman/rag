"""Tests for voice schemas and transcript store."""

from src.voice.schemas import CallRequest, CallResponse, CallStatus, TranscriptEntry


def test_call_request_schema():
    req = CallRequest(phone="+380501234567", lead_data={"name": "Test"}, callback_chat_id=123)
    assert req.phone == "+380501234567"
    assert req.lead_data == {"name": "Test"}


def test_call_status_enum():
    assert CallStatus.INITIATED.value == "initiated"
    assert CallStatus.COMPLETED.value == "completed"
    assert CallStatus.NO_ANSWER.value == "no_answer"


def test_transcript_entry():
    entry = TranscriptEntry(role="user", text="Привет", timestamp_ms=1000)
    assert entry.role == "user"
    assert entry.text == "Привет"


def test_call_response():
    resp = CallResponse(call_id="abc-123", status=CallStatus.INITIATED)
    assert resp.status == CallStatus.INITIATED


def test_transcript_store_init():
    from src.voice.transcript_store import TranscriptStore

    store = TranscriptStore(database_url="postgresql://test:test@localhost/test")
    assert store._database_url == "postgresql://test:test@localhost/test"
    assert store._pool is None
