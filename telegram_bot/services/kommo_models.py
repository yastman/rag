"""Pydantic v2 models for Kommo CRM API."""

from __future__ import annotations

from pydantic import BaseModel, Field


# --- Request Models ---


class DealDraft(BaseModel):
    """Structured deal data extracted from chat history by LLM."""

    client_name: str | None = None
    phone: str | None = None
    email: str | None = None
    budget: int | None = None
    property_type: str | None = None
    location: str | None = None
    notes: str | None = None
    source: str = "telegram_bot"


class ContactCreate(BaseModel):
    """Data for creating/upserting a Kommo contact."""

    first_name: str = ""
    last_name: str = ""
    phone: str | None = None
    email: str | None = None
    telegram_user_id: int | None = None
    responsible_user_id: int | None = None

    def to_kommo_payload(self) -> dict:
        """Convert to Kommo API request body."""
        payload: dict = {}
        if self.first_name:
            payload["first_name"] = self.first_name
        if self.last_name:
            payload["last_name"] = self.last_name
        if self.responsible_user_id:
            payload["responsible_user_id"] = self.responsible_user_id

        custom_fields: list[dict] = []
        if self.phone:
            custom_fields.append(
                {"field_code": "PHONE", "values": [{"value": self.phone, "enum_code": "MOB"}]}
            )
        if self.email:
            custom_fields.append(
                {"field_code": "EMAIL", "values": [{"value": self.email, "enum_code": "WORK"}]}
            )
        if custom_fields:
            payload["custom_fields_values"] = custom_fields

        return payload


class LeadCreate(BaseModel):
    """Data for creating a Kommo lead."""

    name: str
    price: int | None = None
    pipeline_id: int | None = None
    status_id: int | None = None
    responsible_user_id: int | None = None
    session_id: str | None = None
    session_field_id: int | None = None
    tags: list[str] = Field(default_factory=list)

    def to_kommo_payload(self) -> dict:
        """Convert to Kommo API request body."""
        payload: dict = {"name": self.name}
        if self.price is not None:
            payload["price"] = self.price
        if self.pipeline_id is not None:
            payload["pipeline_id"] = self.pipeline_id
        if self.status_id is not None:
            payload["status_id"] = self.status_id
        if self.responsible_user_id is not None:
            payload["responsible_user_id"] = self.responsible_user_id

        custom_fields: list[dict] = []
        if self.session_id and self.session_field_id:
            custom_fields.append(
                {"field_id": self.session_field_id, "values": [{"value": self.session_id}]}
            )
        if custom_fields:
            payload["custom_fields_values"] = custom_fields

        if self.tags:
            payload["_embedded"] = {
                "tags": [{"name": t} for t in self.tags],
            }
        return payload


class TaskCreate(BaseModel):
    """Data for creating a Kommo task."""

    text: str
    entity_id: int
    entity_type: str = "leads"
    task_type_id: int = 1  # 1 = Follow-up
    complete_till: int = 0  # Unix timestamp
    responsible_user_id: int | None = None

    def to_kommo_payload(self) -> dict:
        """Convert to Kommo API request body."""
        payload: dict = {
            "text": self.text,
            "entity_id": self.entity_id,
            "entity_type": self.entity_type,
            "task_type_id": self.task_type_id,
            "complete_till": self.complete_till,
        }
        if self.responsible_user_id is not None:
            payload["responsible_user_id"] = self.responsible_user_id
        return payload


# --- Response Models ---


class LeadResponse(BaseModel):
    """Kommo lead from API response."""

    id: int
    name: str = ""
    price: int = 0


class ContactResponse(BaseModel):
    """Kommo contact from API response."""

    id: int
    name: str = ""


class TaskResponse(BaseModel):
    """Kommo task from API response."""

    id: int
    text: str = ""


class NoteResponse(BaseModel):
    """Kommo note from API response."""

    id: int
