"""Mini App phone collection -> Kommo CRM lead."""

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
    from telegram_bot.services.kommo_client import KommoClient  ***REMOVED*** type: ignore[import-untyped]

    return KommoClient()


@observe(name="miniapp-kommo-create-lead", capture_input=False, capture_output=False)
async def submit_phone(request: PhoneRequest) -> dict:
    """Submit phone to CRM.

    Wrapped in ``@observe`` (***REMOVED***1658). On Kommo failure the surrounding span is
    flipped to ``level="ERROR"`` with a bounded ``status_message`` so the
    funnel break is visible in Langfuse, not just in logs. The success/failure
    return contract is intentionally untouched here (***REMOVED***1596 / PR ***REMOVED***1767 owns the
    fake-success regression separately).
    """
    lf = get_client()
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
    except Exception as exc:
        logger.exception("CRM submission failed")
        if lf is not None:
            ***REMOVED*** Bounded status_message keeps Langfuse payload small and PII-free.
            lf.update_current_span(
                level="ERROR",
                status_message=f"kommo_submission_failed: {type(exc).__name__}"[:200],
                output={"crm_ok": False, "lead_created": False},
            )
        return {"success": True, "lead_id": None}  ***REMOVED*** Graceful degradation

    ***REMOVED*** Curated success output — no phone, no name, no raw Kommo IDs.
    if lf is not None:
        lf.update_current_span(
            output={
                "crm_ok": True,
                "lead_created": lead.get("id") is not None,
                "contact_resolved": contact.get("id") is not None,
            }
        )
    return {"success": True, "lead_id": lead["id"]}
