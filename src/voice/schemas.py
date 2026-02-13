"""Voice service schemas."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field


class CallStatus(StrEnum):
    INITIATED = "initiated"
    RINGING = "ringing"
    ANSWERED = "answered"
    COMPLETED = "completed"
    FAILED = "failed"
    NO_ANSWER = "no_answer"


class CallRequest(BaseModel):
    phone: str
    lead_data: dict = Field(default_factory=dict)
    callback_chat_id: int | None = None


class CallResponse(BaseModel):
    call_id: str
    status: CallStatus


class TranscriptEntry(BaseModel):
    role: str  # "user" | "bot"
    text: str
    timestamp_ms: int
