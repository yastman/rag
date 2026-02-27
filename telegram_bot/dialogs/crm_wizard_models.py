"""Pydantic models for CRM wizard dialog data (#697).

These models validate and structure data collected during aiogram-dialog
wizard flows before conversion to Kommo API payloads.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class LeadCreateData(BaseModel):
    """Data collected by CreateLeadSG wizard."""

    name: str = Field(..., min_length=1, max_length=255)
    budget: int | None = Field(None, ge=0)
    pipeline_id: int | None = None


class ContactCreateData(BaseModel):
    """Data collected by CreateContactSG wizard."""

    first_name: str = Field(..., min_length=1, max_length=100)
    last_name: str | None = Field(None, max_length=100)
    phone: str | None = Field(None, max_length=50)
    email: str | None = Field(None, max_length=255)


class TaskCreateData(BaseModel):
    """Data collected by CreateTaskSG wizard."""

    text: str = Field(..., min_length=1, max_length=1000)
    entity_id: int = Field(..., gt=0)
    entity_type: str = Field(default="leads", pattern="^(leads|contacts)$")
    complete_till: int = Field(..., gt=0)  # Unix timestamp


class NoteCreateData(BaseModel):
    """Data collected by CreateNoteSG wizard."""

    entity_type: str = Field(..., pattern="^(leads|contacts)$")
    entity_id: int = Field(..., gt=0)
    text: str = Field(..., min_length=1, max_length=2000)
