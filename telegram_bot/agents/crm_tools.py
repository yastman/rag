"""Kommo CRM supervisor tools (#312).

7 tools for deal lifecycle: draft, upsert_contact, create_deal,
link_contact, add_note, create_task, finalize_deal.

Pattern: factory function with dependency injection (same as tools.py).
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool

from telegram_bot.observability import get_client, observe
from telegram_bot.services.kommo_models import (
    ContactCreate,
    DealDraft,
    LeadCreate,
    TaskCreate,
)


logger = logging.getLogger(__name__)

DEAL_DRAFT_SYSTEM_PROMPT = """\
Extract structured deal information from chat history.
Return ONLY a JSON object with these fields (null if not found):
- client_name: full name
- phone: phone number with country code
- email: email address
- budget: numeric budget in local currency
- property_type: type of property
- location: location/city
- notes: brief summary of requirements
- source: always "telegram_bot"
"""


def _get_user_context(config: RunnableConfig | None) -> tuple[int | None, str | None]:
    configurable = (config or {}).get("configurable", {})
    return configurable.get("user_id"), configurable.get("session_id")


def create_crm_tools(
    *,
    kommo: Any,
    llm: Any,
    history_service: Any,
    default_pipeline_id: int,
    responsible_user_id: int | None,
    session_field_id: int,
    idempotency_store: Any | None = None,
) -> list[Any]:
    """Create all CRM supervisor tools with injected dependencies."""

    @tool
    @observe(name="crm-generate-deal-draft")
    async def crm_generate_deal_draft(query: str, config: RunnableConfig) -> str:
        """Generate a structured deal draft by extracting data from chat history using LLM.

        Use this when you need to prepare deal data before creating it in CRM.
        Returns JSON with extracted client info (name, phone, budget, property type).
        """
        user_id, session_id = _get_user_context(config)
        if not user_id:
            return "Error: user context not available."

        messages = await history_service.get_session_turns(user_id, session_id, limit=40)
        chat_text = "\n".join(f"{m.get('role', 'user')}: {m.get('content', '')}" for m in messages)

        response = await llm.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": DEAL_DRAFT_SYSTEM_PROMPT},
                {"role": "user", "content": f"Chat history:\n{chat_text}"},
            ],
            name="crm-deal-draft-extraction",
        )
        draft_json = response.choices[0].message.content
        try:
            draft = DealDraft.model_validate_json(draft_json)
        except Exception:
            logger.warning("Failed to parse DealDraft, returning raw: %s", draft_json[:200])
            return draft_json or "Failed to generate deal draft."

        return draft.model_dump_json()

    @tool
    @observe(name="crm-upsert-contact")
    async def crm_upsert_contact(
        phone: str,
        first_name: str = "",
        last_name: str = "",
        email: str = "",
        config: RunnableConfig = None,  # type: ignore[assignment]
    ) -> str:
        """Find or create a contact in Kommo CRM by phone number.

        Use this to ensure the client exists in CRM before creating a deal.
        Returns the contact ID and name.
        """
        data = ContactCreate(
            first_name=first_name,
            last_name=last_name,
            phone=phone,
            email=email or None,
            responsible_user_id=responsible_user_id,
        )
        contact = await kommo.upsert_contact(phone=phone, data=data)
        return json.dumps({"contact_id": contact.id, "name": contact.name})

    @tool
    @observe(name="crm-create-deal")
    async def crm_create_deal(
        name: str,
        price: int = 0,
        config: RunnableConfig = None,  # type: ignore[assignment]
    ) -> str:
        """Create a new deal (lead) in Kommo CRM pipeline.

        Use this to register a new sales opportunity.
        Returns the deal ID.
        """
        _user_id, session_id = _get_user_context(config)
        lead_data = LeadCreate(
            name=name,
            price=price or None,
            pipeline_id=default_pipeline_id or None,
            responsible_user_id=responsible_user_id,
            session_id=session_id,
            session_field_id=session_field_id or None,
            tags=["telegram_bot"],
        )
        start = time.perf_counter()
        lead = await kommo.create_lead(lead_data)
        latency_ms = (time.perf_counter() - start) * 1000

        lf = get_client()
        lf.score_current_trace(name="crm_deal_created", value=1, data_type="NUMERIC")
        lf.score_current_trace(
            name="crm_deal_create_latency_ms", value=latency_ms, data_type="NUMERIC"
        )

        return json.dumps({"deal_id": lead.id, "name": lead.name})

    @tool
    @observe(name="crm-link-contact-to-deal")
    async def crm_link_contact_to_deal(
        deal_id: int,
        contact_id: int,
        config: RunnableConfig = None,  # type: ignore[assignment]
    ) -> str:
        """Link a contact to a deal in Kommo CRM.

        Use this after creating both contact and deal to bind them together.
        """
        await kommo.link_contact_to_lead(lead_id=deal_id, contact_id=contact_id)
        return json.dumps({"linked": True, "deal_id": deal_id, "contact_id": contact_id})

    @tool
    @observe(name="crm-add-note")
    async def crm_add_note(
        deal_id: int,
        text: str,
        config: RunnableConfig = None,  # type: ignore[assignment]
    ) -> str:
        """Add a text note to a deal in Kommo CRM.

        Use this to attach chat summaries or important information to deals.
        """
        note = await kommo.add_note(entity_type="leads", entity_id=deal_id, text=text)
        return json.dumps({"note_id": note.id, "deal_id": deal_id})

    @tool
    @observe(name="crm-create-followup-task")
    async def crm_create_followup_task(
        deal_id: int,
        text: str = "Follow up with client",
        due_hours: int = 24,
        config: RunnableConfig = None,  # type: ignore[assignment]
    ) -> str:
        """Create a follow-up task linked to a deal in Kommo CRM.

        Use this to schedule reminders for the responsible user.
        """
        complete_till = int(time.time()) + (due_hours * 3600)
        task_data = TaskCreate(
            text=text,
            entity_id=deal_id,
            entity_type="leads",
            complete_till=complete_till,
            responsible_user_id=responsible_user_id,
        )
        task = await kommo.create_task(task_data)

        lf = get_client()
        lf.score_current_trace(name="crm_task_created", value=1, data_type="NUMERIC")

        return json.dumps({"task_id": task.id, "deal_id": deal_id})

    @tool
    @observe(name="crm-finalize-deal")
    async def crm_finalize_deal(query: str, config: RunnableConfig) -> str:
        """End-to-end deal creation: extract data from chat, create contact, deal, link, note, task.

        Use this when the user asks to create a deal based on the conversation.
        Orchestrates all CRM steps in sequence with idempotency checks.
        """
        user_id, session_id = _get_user_context(config)
        if not user_id:
            return "Error: user context not available."

        start = time.perf_counter()
        lf = get_client()

        # Idempotency check
        if idempotency_store is not None:
            idempotency_key = f"kommo:deal:{user_id}:{session_id}"
            was_set = await idempotency_store.set(
                idempotency_key,
                "1",
                ex=24 * 3600,
                nx=True,
            )
            if not was_set:
                lf.score_current_trace(
                    name="crm_deal_idempotent_skip", value=1, data_type="BOOLEAN"
                )
                return "Idempotent skip: deal for this session is already processed."

        try:
            # Step 1: Extract deal data from chat history
            messages = await history_service.get_session_turns(user_id, session_id, limit=40)
            chat_text = "\n".join(
                f"{m.get('role', 'user')}: {m.get('content', '')}" for m in messages
            )
            response = await llm.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": DEAL_DRAFT_SYSTEM_PROMPT},
                    {"role": "user", "content": f"Chat history:\n{chat_text}"},
                ],
                name="crm-finalize-draft-extraction",
            )
            draft_json = response.choices[0].message.content
            try:
                draft = DealDraft.model_validate_json(draft_json)
            except Exception:
                return f"Failed to extract deal data from chat. Raw: {draft_json[:200]}"

            # Step 2: Upsert contact
            contact = None
            if draft.phone:
                contact_data = ContactCreate(
                    first_name=draft.client_name or "",
                    phone=draft.phone,
                    email=draft.email or None,
                    responsible_user_id=responsible_user_id,
                )
                contact = await kommo.upsert_contact(phone=draft.phone, data=contact_data)
                lf.score_current_trace(name="crm_contact_upserted", value=1, data_type="NUMERIC")

            # Step 3: Create deal
            deal_name = f"{draft.property_type or 'Сделка'}"
            if draft.location:
                deal_name += f" — {draft.location}"
            if draft.client_name:
                deal_name += f" ({draft.client_name})"

            lead_data = LeadCreate(
                name=deal_name,
                price=draft.budget,
                pipeline_id=default_pipeline_id or None,
                responsible_user_id=responsible_user_id,
                session_id=session_id,
                session_field_id=session_field_id or None,
                tags=["telegram_bot"],
            )
            lead = await kommo.create_lead(lead_data)

            # Step 4: Link contact to deal
            if contact:
                await kommo.link_contact_to_lead(lead_id=lead.id, contact_id=contact.id)

            # Step 5: Add note with chat summary
            note_text = "Источник: Telegram Bot\n"
            if draft.notes:
                note_text += f"Запрос: {draft.notes}\n"
            note_text += f"Session: {session_id}"
            await kommo.add_note(entity_type="leads", entity_id=lead.id, text=note_text)

            # Step 6: Create follow-up task
            complete_till = int(time.time()) + 24 * 3600
            task = TaskCreate(
                text=f"Связаться с {draft.client_name or 'клиентом'} по запросу из Telegram",
                entity_id=lead.id,
                entity_type="leads",
                complete_till=complete_till,
                responsible_user_id=responsible_user_id,
            )
            await kommo.create_task(task)

            latency_ms = (time.perf_counter() - start) * 1000
            lf.score_current_trace(name="crm_deal_created", value=1, data_type="NUMERIC")
            lf.score_current_trace(
                name="crm_deal_create_latency_ms", value=latency_ms, data_type="NUMERIC"
            )
            lf.score_current_trace(name="crm_write_success", value=1, data_type="NUMERIC")
            lf.score_current_trace(name="crm_task_created", value=1, data_type="NUMERIC")

            result_parts = [f"Сделка #{lead.id} создана: {deal_name}."]
            if contact:
                result_parts.append(f"Контакт: {contact.name} (#{contact.id}).")
            result_parts.append("Задача follow-up назначена.")

            return " ".join(result_parts)

        except Exception:
            logger.exception("CRM finalize_deal failed")
            lf.score_current_trace(name="crm_write_success", value=0, data_type="NUMERIC")
            return "Ошибка при создании сделки в CRM. Попробуйте позже."

    return [
        crm_generate_deal_draft,
        crm_upsert_contact,
        crm_create_deal,
        crm_link_contact_to_deal,
        crm_add_note,
        crm_create_followup_task,
        crm_finalize_deal,
    ]
