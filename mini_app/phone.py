"""Mini App phone collection -> Kommo CRM lead."""

from __future__ import annotations

import logging

from pydantic import BaseModel, field_validator

from telegram_bot.observability import get_client, observe
from telegram_bot.phone_utils import normalize_phone


logger = logging.getLogger(__name__)


class PhoneRequest(BaseModel):
    phone: str
    source: str
    user_id: int
    name: str | None = None

    @field_validator("phone")
    @classmethod
    def validate_phone(cls, v: str) -> str:
        """Normalize to E.164 via the shared phonenumbers-based helper.

        Closes #1614 — the previous local digit-count regex accepted
        impossible numbers (e.g. eleven repeated ones) and never produced
        E.164 output, so the same Mini App contact could be stored in a
        different format than the bot-side phone collection.
        """
        normalized = normalize_phone(v)
        if normalized is None:
            msg = "Invalid phone number"
            raise ValueError(msg)
        return normalized


def get_kommo_client():
    """Get Kommo client (lazy import)."""
    from telegram_bot.services.kommo_client import KommoClient  # type: ignore[import-untyped]

    return KommoClient()


@observe(name="miniapp-kommo-create-lead", capture_input=False, capture_output=False)
async def submit_phone(request: PhoneRequest) -> dict:
    """Submit phone to CRM.

    Returns
    -------
    dict
        ``{"success": True, "lead_id": <int>}`` on success.
        ``{"success": False, "lead_id": None, "error": "crm_submission_failed"}``
        on any CRM failure. Returning ``success: True`` for a swallowed
        exception (#1596) made it impossible for clients to distinguish a
        real captured lead from a dropped one. The error code is stable so
        the frontend can show a retry/contact-support state without parsing
        free-form text. The ``@observe`` wrapper records success/failure
        metadata without capturing PII.
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
            # Bounded status_message keeps Langfuse payload small and PII-free.
            lf.update_current_span(
                level="ERROR",
                status_message=f"kommo_submission_failed: {type(exc).__name__}"[:200],
                output={"crm_ok": False, "lead_created": False},
            )
        return {
            "success": False,
            "lead_id": None,
            "error": "crm_submission_failed",
        }

    # Curated success output — no phone, no name, no raw Kommo IDs.
    if lf is not None:
        lf.update_current_span(
            output={
                "crm_ok": True,
                "lead_created": lead.get("id") is not None,
                "contact_resolved": contact.get("id") is not None,
            }
        )
    return {"success": True, "lead_id": lead["id"]}
