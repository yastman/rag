"""Mini App phone collection -> Kommo CRM lead.

Langfuse observability (#1658):
    ``submit_phone`` is wrapped with ``@observe`` so the Kommo upsert+lead pair
    appears as a span; failures are surfaced as ``level="ERROR"`` updates on
    the active span before the graceful response is returned.
"""

from __future__ import annotations

import logging
import re

from pydantic import BaseModel, field_validator

from telegram_bot.observability import get_client, observe


logger = logging.getLogger(__name__)

_PHONE_RE = re.compile(r"^\+?\d{7,15}$")


class PhoneRequest(BaseModel):
    phone: str
    source: str
    user_id: int
    name: str | None = None

    @field_validator("phone")
    @classmethod
    def validate_phone(cls, v: str) -> str:
        cleaned = re.sub(r"[\s\-\(\)]", "", v)
        if not _PHONE_RE.match(cleaned):
            msg = "Invalid phone number"
            raise ValueError(msg)
        return cleaned


def get_kommo_client():
    """Get Kommo client (lazy import)."""
    from telegram_bot.services.kommo_client import KommoClient  # type: ignore[import-untyped]

    return KommoClient()


@observe(
    name="miniapp-kommo-create-lead",
    capture_input=False,
    capture_output=False,
)
async def submit_phone(request: PhoneRequest) -> dict:
    """Submit phone to CRM, marking the active span ERROR on Kommo failure."""
    try:
        client = get_kommo_client()
        contact = await client.upsert_contact(
            phone=request.phone,
            name=request.name or f"Mini App User {request.user_id}",
        )
        lead = await client.create_lead(
            name=f"Mini App: {request.source}",
            contact_id=contact["id"],
        )
        return {"success": True, "lead_id": lead["id"]}
    except Exception as exc:
        logger.exception("CRM submission failed")
        # Surface the failure on the active Langfuse span before returning the
        # graceful response. Without this update the Kommo error is invisible
        # in Sessions UI (#1658 evidence).
        lf = get_client()
        if lf is not None:
            lf.update_current_span(
                level="ERROR",
                status_message=f"Kommo submission failed: {exc!s}",
                metadata={
                    "source": "miniapp",
                    "endpoint": "submit-phone",
                    "error_type": type(exc).__name__,
                },
            )
        return {"success": True, "lead_id": None}  # Graceful degradation
