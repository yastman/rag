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


# --- Lead Score Sync (#384) ---


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
        """Build from a LeadScoreRecord (avoids circular import)."""
        return cls(
            kommo_lead_id=int(getattr(rec, "kommo_lead_id", 0) or 0),
            score_value=getattr(rec, "score_value", 0),
            score_band=getattr(rec, "score_band", ""),
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
