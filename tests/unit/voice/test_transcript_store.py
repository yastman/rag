"""Tests for voice schemas and transcript store."""

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

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
async def test_create_call_uses_provided_call_id():
    from src.voice.transcript_store import TranscriptStore

    provided_call_id = "11111111-1111-1111-1111-111111111111"
    store = TranscriptStore(database_url="postgresql://test:test@localhost/test")

    conn = AsyncMock()

    class _AcquireCtx:
        async def __aenter__(self):
            return conn

        async def __aexit__(self, exc_type, exc, tb):
            return False

    pool = MagicMock()
    pool.acquire.return_value = _AcquireCtx()
    store._pool = pool

    returned_id = await store.create_call(
        phone="+380501234567",
        lead_data={"name": "Test"},
        callback_chat_id=123,
        call_id=provided_call_id,
    )

    assert returned_id == provided_call_id
    execute_args = conn.execute.call_args[0]
    assert execute_args[1] == uuid.UUID(provided_call_id)
