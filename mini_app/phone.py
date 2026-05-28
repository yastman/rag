"""Mini App phone collection -> Kommo CRM lead."""

from __future__ import annotations

import logging
from typing import Any

from pydantic import BaseModel, field_validator

from src.observability import get_client, observe
from src.phone_utils import normalize_phone


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
    """Get Kommo client (lazy import).

    Deprecated since #2212: kept for backward compat with callers that
    haven't migrated to dependency injection. New callers must construct
    a :class:`KommoClient` via ``mini_app.api._build_kommo_client(...)``
    in the FastAPI ``lifespan`` and pass it explicitly to
    :func:`submit_phone`.
    """
    from src.services.kommo_client import KommoClient  # type: ignore[import-untyped]

    return KommoClient()


@observe(name="miniapp-kommo-create-lead", capture_input=False, capture_output=False)
async def submit_phone(request: PhoneRequest, *, client: Any | None = None) -> dict:
    """Submit phone to CRM.

    Args:
        request: Validated phone request from the Mini App.
        client: Pre-built ``KommoClient`` instance, injected by the
            FastAPI lifespan. ``None`` means Kommo is not configured —
            in which case we return a structured ``kommo_unconfigured``
            failure (HTTP 503 surface) instead of constructing a client
            inline. The previous implementation called ``KommoClient()``
            without args, which raised ``TypeError`` because the SDK
            requires keyword-only ``subdomain`` and ``token_store`` —
            every Mini App phone submission emitted a Langfuse error
            span and the user saw a generic failure (#2212).

    Returns:
        ``{"success": True, "lead_id": <int>}`` on success.
        ``{"success": False, "lead_id": None, "error": "kommo_unconfigured"}``
        when ``client`` is ``None`` (Mini App boot did not wire Kommo).
        ``{"success": False, "lead_id": None, "error":
        "kommo_submission_failed"}`` on any CRM-side exception.
    """
    lf = get_client()

    if client is None:
        # Misconfigured Mini App — fail loudly via a stable error code so
        # the frontend can surface "CRM unavailable, please retry" without
        # parsing free-form text. The Langfuse span carries the same code.
        if lf is not None:
            lf.update_current_span(
                level="ERROR",
                status_message="kommo_unconfigured",
                output={"crm_ok": False, "lead_created": False},
            )
        return {
            "success": False,
            "lead_id": None,
            "error": "kommo_unconfigured",
        }

    try:
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
            "error": "kommo_submission_failed",
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
