"""Pydantic v2 models for Kommo CRM API (#413).

Models match Kommo API v4 payloads.
Ref: https://www.kommo.com/developers/content/api/
"""

from __future__ import annotations

from pydantic import BaseModel


# --- Request models (Create/Update) ---


class LeadCreate(BaseModel):
    """POST /api/v4/leads payload."""

    name: str
    budget: int | None = None
    pipeline_id: int | None = None
    status_id: int | None = None
    custom_fields_values: list[dict] | None = None


class LeadUpdate(BaseModel):
    """PATCH /api/v4/leads/{id} payload."""

    name: str | None = None
    budget: int | None = None
    status_id: int | None = None
    custom_fields_values: list[dict] | None = None


class ContactCreate(BaseModel):
    """POST /api/v4/contacts payload."""

    first_name: str
    last_name: str | None = None
    phone: str | None = None
    email: str | None = None
    custom_fields_values: list[dict] | None = None


class TaskCreate(BaseModel):
    """POST /api/v4/tasks payload."""

    text: str
    entity_id: int
    entity_type: str = "leads"
    complete_till: int  # Unix timestamp
    task_type_id: int | None = None


# --- Response models ---


class Lead(BaseModel):
    """Lead from Kommo API response."""

    id: int
    name: str
    budget: int | None = None
    status_id: int | None = None
    pipeline_id: int | None = None
    created_at: int | None = None
    updated_at: int | None = None


class Contact(BaseModel):
    """Contact from Kommo API response."""

    id: int
    first_name: str | None = None
    last_name: str | None = None
    created_at: int | None = None


class Note(BaseModel):
    """Note from Kommo API response."""

    id: int
    text: str | None = None
    created_at: int | None = None


class Task(BaseModel):
    """Task from Kommo API response."""

    id: int
    text: str | None = None
    complete_till: int | None = None
    entity_id: int | None = None


class Pipeline(BaseModel):
    """Pipeline from Kommo API response."""

    id: int
    name: str
    is_main: bool = False
