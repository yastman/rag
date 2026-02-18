"""Pydantic models for lead scoring persistence (#384)."""

from __future__ import annotations

from pydantic import BaseModel, Field


class LeadScoreRecord(BaseModel):
    """A scored lead ready for persistence and CRM sync."""

    lead_id: int
    user_id: int
    session_id: str
    score_value: int = Field(ge=0, le=100)
    score_band: str
    reason_codes: list[str] = Field(default_factory=list)
    kommo_lead_id: int | None = None
