"""Pydantic v2 models for Kommo CRM API (#413).

Models match Kommo API v4 payloads.
Kommo API uses "price" for deal value; Python code uses "budget" for readability.
Ref: https://www.kommo.com/developers/content/api/
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


# --- Request models (Create/Update) ---


class LeadCreate(BaseModel):
    """POST /api/v4/leads payload."""

    model_config = ConfigDict(populate_by_name=True)

    name: str
    budget: int | None = Field(None, serialization_alias="price", validation_alias="price")
    pipeline_id: int | None = None
    status_id: int | None = None
    responsible_user_id: int | None = None
    custom_fields_values: list[dict] | None = None


class LeadUpdate(BaseModel):
    """PATCH /api/v4/leads/{id} payload."""

    model_config = ConfigDict(populate_by_name=True)

    name: str | None = None
    budget: int | None = Field(None, serialization_alias="price", validation_alias="price")
    status_id: int | None = None
    custom_fields_values: list[dict] | None = None


class ContactCreate(BaseModel):
    """POST /api/v4/contacts payload."""

    first_name: str
    last_name: str | None = None
    phone: str | None = None
    email: str | None = None
    custom_fields_values: list[dict] | None = None


class ContactUpdate(BaseModel):
    """PATCH /api/v4/contacts/{id} payload."""

    first_name: str | None = None
    last_name: str | None = None
    custom_fields_values: list[dict] | None = None

    @staticmethod
    def build_contact_fields(
        phone: str | None = None,
        email: str | None = None,
    ) -> list[dict]:
        """Build custom_fields_values for phone/email updates."""
        fields = []
        if phone is not None:
            fields.append(
                {"field_code": "PHONE", "values": [{"value": phone, "enum_code": "WORK"}]}
            )
        if email is not None:
            fields.append(
                {"field_code": "EMAIL", "values": [{"value": email, "enum_code": "WORK"}]}
            )
        return fields


class TaskCreate(BaseModel):
    """POST /api/v4/tasks payload."""

    text: str
    entity_id: int
    entity_type: str = "leads"
    complete_till: int  # Unix timestamp
    task_type_id: int | None = None


class TaskUpdate(BaseModel):
    """PATCH /api/v4/tasks/{id} payload (#697)."""

    text: str | None = None
    complete_till: int | None = None  # Unix timestamp
    responsible_user_id: int | None = None


# --- Response models ---


class Lead(BaseModel):
    """Lead from Kommo API response.

    Note: POST /leads returns minimal response (id only).
    Full fields available via GET /leads/{id}.
    Kommo API field "price" maps to "budget" in Python.
    """

    model_config = ConfigDict(populate_by_name=True)

    id: int
    name: str | None = None
    budget: int | None = Field(None, validation_alias="price")
    status_id: int | None = None
    pipeline_id: int | None = None
    responsible_user_id: int | None = None
    loss_reason_id: int | None = None
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
    entity_type: str | None = None
    responsible_user_id: int | None = None
    is_completed: bool | None = None
    ***REMOVED*** may return `result` as dict or empty list depending on task state.
    result: dict[str, Any] | list[Any] | None = None
    created_at: int | None = None
    updated_at: int | None = None


class Pipeline(BaseModel):
    """Pipeline from Kommo API response."""

    id: int
    name: str
    is_main: bool = False


# --- Lead Score Sync (compatibility with existing tools/tests) ---


class LeadScoreSyncPayload(BaseModel):
    """Payload for syncing a lead score to Kommo custom fields."""

    kommo_lead_id: int
    score_value: int
    score_band: str
    score_field_id: int
    band_field_id: int

    @classmethod
    def from_record(
        cls,
        rec: object,
        *,
        score_field_id: int,
        band_field_id: int,
    ) -> LeadScoreSyncPayload:
        """Build from a LeadScoreRecord while avoiding circular imports."""
        return cls(
            kommo_lead_id=int(getattr(rec, "kommo_lead_id", 0) or 0),
            score_value=int(getattr(rec, "score_value", 0)),
            score_band=str(getattr(rec, "score_band", "")),
            score_field_id=score_field_id,
            band_field_id=band_field_id,
        )

    def to_kommo_payload(self) -> dict:
        """Convert to Kommo API PATCH body for custom fields."""
        return {
            "custom_fields_values": [
                {"field_id": self.score_field_id, "values": [{"value": self.score_value}]},
                {"field_id": self.band_field_id, "values": [{"value": self.score_band}]},
            ]
        }
