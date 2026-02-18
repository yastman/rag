"""CRM tools for Kommo API — 8 tools with config-based context DI (#413).

All tools check ctx.kommo_client is not None before proceeding.
Dependencies injected via config["configurable"]["bot_context"].
"""

from __future__ import annotations

import logging

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool

from telegram_bot.observability import observe
from telegram_bot.services.kommo_models import (
    ContactCreate,
    LeadCreate,
    LeadUpdate,
    TaskCreate,
)


logger = logging.getLogger(__name__)

_CRM_UNAVAILABLE = "CRM недоступен. Обратитесь к администратору."


def _get_kommo(config: RunnableConfig):
    """Get KommoClient from config context."""
    ctx = config.get("configurable", {}).get("bot_context")
    if ctx and ctx.kommo_client:
        return ctx.kommo_client
    return None


# --- READ tools ---


@tool
@observe(name="crm-get-deal")
async def crm_get_deal(deal_id: int, config: RunnableConfig) -> str:
    """Get deal details from CRM by deal ID.

    Args:
        deal_id: The Kommo lead/deal ID.
    """
    kommo = _get_kommo(config)
    if not kommo:
        return _CRM_UNAVAILABLE

    try:
        lead = await kommo.get_lead(deal_id)
        return str(lead.model_dump_json())
    except Exception as e:
        logger.exception("crm_get_deal failed")
        return f"Ошибка при получении сделки: {e}"


@tool
@observe(name="crm-get-contacts")
async def crm_get_contacts(query: str, config: RunnableConfig) -> str:
    """Search contacts in CRM by name or phone.

    Args:
        query: Search query (name, phone, email).
    """
    kommo = _get_kommo(config)
    if not kommo:
        return _CRM_UNAVAILABLE

    try:
        contacts = await kommo.get_contacts(query)
        if not contacts:
            return f"Контакты по запросу «{query}» не найдены."
        lines = [f"- {c.first_name or ''} {c.last_name or ''} (ID: {c.id})" for c in contacts[:10]]
        return "\n".join(lines)
    except Exception as e:
        logger.exception("crm_get_contacts failed")
        return f"Ошибка при поиске контактов: {e}"


# --- WRITE tools ---


@tool
@observe(name="crm-create-lead")
async def crm_create_lead(
    name: str,
    config: RunnableConfig,
    budget: int | None = None,
    pipeline_id: int | None = None,
) -> str:
    """Create a new deal/lead in CRM.

    Args:
        name: Deal name.
        budget: Optional budget in local currency.
        pipeline_id: Optional pipeline ID.
    """
    kommo = _get_kommo(config)
    if not kommo:
        return _CRM_UNAVAILABLE

    try:
        lead = await kommo.create_lead(
            LeadCreate(name=name, budget=budget, pipeline_id=pipeline_id)
        )
        return f"Сделка создана: ID {lead.id}, {lead.name}"
    except Exception as e:
        logger.exception("crm_create_lead failed")
        return f"Ошибка при создании сделки: {e}"


@tool
@observe(name="crm-update-lead")
async def crm_update_lead(
    deal_id: int,
    config: RunnableConfig,
    name: str | None = None,
    budget: int | None = None,
    status_id: int | None = None,
) -> str:
    """Update an existing deal/lead in CRM.

    Args:
        deal_id: The deal ID to update.
        name: New name (optional).
        budget: New budget (optional).
        status_id: New status (optional).
    """
    kommo = _get_kommo(config)
    if not kommo:
        return _CRM_UNAVAILABLE

    try:
        lead = await kommo.update_lead(
            deal_id, LeadUpdate(name=name, budget=budget, status_id=status_id)
        )
        return f"Сделка обновлена: ID {lead.id}"
    except Exception as e:
        logger.exception("crm_update_lead failed")
        return f"Ошибка при обновлении сделки: {e}"


@tool
@observe(name="crm-upsert-contact")
async def crm_upsert_contact(
    phone: str,
    first_name: str,
    config: RunnableConfig,
    last_name: str | None = None,
    email: str | None = None,
) -> str:
    """Find or create a contact by phone number.

    Args:
        phone: Phone number (used for dedup search).
        first_name: Contact first name.
        last_name: Optional last name.
        email: Optional email.
    """
    kommo = _get_kommo(config)
    if not kommo:
        return _CRM_UNAVAILABLE

    try:
        contact = await kommo.upsert_contact(
            phone,
            ContactCreate(first_name=first_name, last_name=last_name, phone=phone, email=email),
        )
        return f"Контакт: ID {contact.id}, {contact.first_name}"
    except Exception as e:
        logger.exception("crm_upsert_contact failed")
        return f"Ошибка при работе с контактом: {e}"


@tool
@observe(name="crm-add-note")
async def crm_add_note(
    entity_type: str,
    entity_id: int,
    text: str,
    config: RunnableConfig,
) -> str:
    """Add a note to a deal or contact in CRM.

    Args:
        entity_type: 'leads' or 'contacts'.
        entity_id: Entity ID.
        text: Note text.
    """
    kommo = _get_kommo(config)
    if not kommo:
        return _CRM_UNAVAILABLE

    try:
        note = await kommo.add_note(entity_type, entity_id, text)
        return f"Заметка добавлена: ID {note.id}"
    except Exception as e:
        logger.exception("crm_add_note failed")
        return f"Ошибка при добавлении заметки: {e}"


@tool
@observe(name="crm-create-task")
async def crm_create_task(
    text: str,
    entity_id: int,
    complete_till: int,
    config: RunnableConfig,
    entity_type: str = "leads",
) -> str:
    """Create a follow-up task in CRM.

    Args:
        text: Task description.
        entity_id: Linked entity ID.
        complete_till: Due date as Unix timestamp.
        entity_type: 'leads' or 'contacts'.
    """
    kommo = _get_kommo(config)
    if not kommo:
        return _CRM_UNAVAILABLE

    try:
        task = await kommo.create_task(
            TaskCreate(
                text=text,
                entity_id=entity_id,
                entity_type=entity_type,
                complete_till=complete_till,
            )
        )
        return f"Задача создана: ID {task.id}"
    except Exception as e:
        logger.exception("crm_create_task failed")
        return f"Ошибка при создании задачи: {e}"


@tool
@observe(name="crm-link-contact-to-deal")
async def crm_link_contact_to_deal(
    lead_id: int,
    contact_id: int,
    config: RunnableConfig,
) -> str:
    """Link a contact to a deal in CRM.

    Args:
        lead_id: Deal ID.
        contact_id: Contact ID.
    """
    kommo = _get_kommo(config)
    if not kommo:
        return _CRM_UNAVAILABLE

    try:
        await kommo.link_contact_to_lead(lead_id, contact_id)
        return f"Контакт {contact_id} привязан к сделке {lead_id}"
    except Exception as e:
        logger.exception("crm_link_contact_to_deal failed")
        return f"Ошибка при привязке контакта: {e}"


def get_crm_tools() -> list:
    """Return all CRM tools for agent registration."""
    return [
        crm_get_deal,
        crm_create_lead,
        crm_update_lead,
        crm_upsert_contact,
        crm_add_note,
        crm_create_task,
        crm_link_contact_to_deal,
        crm_get_contacts,
    ]
