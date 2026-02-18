"""CRM supervisor tools for Kommo integration (#389, #312/#324).

Manager-only tools that wrap KommoClient for deal lifecycle operations.
All tools are fail-soft — CRM errors return a user-friendly message
instead of propagating exceptions to the supervisor.
"""

from __future__ import annotations

import logging
from typing import Any

from langchain_core.tools import tool


logger = logging.getLogger(__name__)


def create_crm_tools(*, kommo: Any, history_service: Any, llm: Any) -> list[Any]:
    """Create CRM tools bound to the given Kommo client.

    Args:
        kommo: KommoClient instance for API calls.
        history_service: HistoryService for session context.
        llm: LLM client for draft generation.

    Returns:
        List of LangChain tools for supervisor binding.
    """

    @tool
    async def crm_generate_deal_draft(session_id: str) -> str:
        """Generate a CRM deal draft from the current conversation session.

        Use this when the manager wants to create a lead/deal based on
        the client's conversation. Summarizes needs, budget, preferences.
        """
        try:
            from telegram_bot.services.session_summary import (
                format_summary_as_note,
                generate_summary,
            )

            if history_service is None:
                return "History service unavailable — cannot generate deal draft."

            turns = await history_service.get_session_turns(session_id=session_id, limit=30)
            if not turns:
                return f"No conversation turns found for session {session_id}."

            summary = await generate_summary(turns=turns, llm=llm)
            if summary is None:
                return "Could not generate summary from conversation."

            return format_summary_as_note(summary)
        except Exception:
            logger.exception("crm_generate_deal_draft failed")
            return "CRM is temporarily unavailable, please retry in a minute."

    @tool
    async def crm_upsert_contact(phone: str, name: str = "") -> str:
        """Create or update a contact in Kommo CRM by phone number.

        Use this when you need to register a new client or update existing
        contact details before creating a deal.
        """
        try:
            result = await kommo._request_json(
                "GET",
                "/contacts",
                json={"query": phone},
            )
            contacts = result.get("_embedded", {}).get("contacts", [])
            if contacts:
                contact_id = contacts[0]["id"]
                return f"Contact already exists: ID {contact_id}"

            create_result = await kommo._request_json(
                "POST",
                "/contacts",
                json=[{"name": name or phone, "custom_fields_values": []}],
            )
            new_contacts = create_result.get("_embedded", {}).get("contacts", [])
            if new_contacts:
                return f"Contact created: ID {new_contacts[0]['id']}"
            return "Contact creation returned no data."
        except Exception:
            logger.exception("crm_upsert_contact failed")
            return "CRM is temporarily unavailable, please retry in a minute."

    @tool
    async def crm_create_deal(name: str, pipeline_id: int) -> str:
        """Create a new deal (lead) in Kommo CRM pipeline.

        Use this after confirming client interest and generating a deal draft.
        Requires deal name and target pipeline ID.
        """
        try:
            result = await kommo._request_json(
                "POST",
                "/leads",
                json=[{"name": name, "pipeline_id": pipeline_id}],
            )
            leads = result.get("_embedded", {}).get("leads", [])
            if leads:
                return f"Deal created: ID {leads[0]['id']}"
            return "Deal creation returned no data."
        except Exception:
            logger.exception("crm_create_deal failed")
            return "CRM is temporarily unavailable, please retry in a minute."

    return [crm_generate_deal_draft, crm_upsert_contact, crm_create_deal]
