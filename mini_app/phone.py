"""Mini App phone collection -> Kommo CRM lead."""

from __future__ import annotations

import logging
import re

from pydantic import BaseModel, field_validator


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


async def submit_phone(request: PhoneRequest) -> dict:
    """Submit phone to CRM.

    Returns
    -------
    dict
        ``{"success": True, "lead_id": <int>}`` on success.
        ``{"success": False, "lead_id": None, "error": "crm_submission_failed"}``
        on any CRM failure. Returning ``success: True`` for a swallowed
        exception (***REMOVED***1596) made it impossible for clients to distinguish a
        real captured lead from a dropped one. The error code is stable so
        the frontend can show a retry/contact-support state without parsing
        free-form text.
    """
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
    except Exception:
        logger.exception("CRM submission failed")
        return {
            "success": False,
            "lead_id": None,
            "error": "crm_submission_failed",
        }
