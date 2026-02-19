"""CRM tools for Kommo API — 8 tools with config-based context DI (#413).

All tools check ctx.kommo_client is not None before proceeding.
Dependencies injected via config["configurable"]["bot_context"].
"""

from __future__ import annotations

import logging

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool

from telegram_bot.agents.hitl import format_hitl_preview, hitl_guard
from telegram_bot.observability import observe
from telegram_bot.services.kommo_models import (
    ContactCreate,
    ContactUpdate,
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


def _get_ctx(config: RunnableConfig):
    """Get BotContext from config."""
    return config.get("configurable", {}).get("bot_context")


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
    """Create a new deal/lead in CRM. Requires confirmation.

    Args:
        name: Deal name.
        budget: Optional budget in local currency.
        pipeline_id: Optional pipeline ID.
    """
    kommo = _get_kommo(config)
    if not kommo:
        return _CRM_UNAVAILABLE

    args = {"name": name, "budget": budget, "pipeline_id": pipeline_id}
    preview = format_hitl_preview("crm_create_lead", args)
    response = hitl_guard("crm_create_lead", preview, args)

    if response.get("action") != "approve":
        return "Операция отменена пользователем."

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
    """Update an existing deal/lead in CRM. Requires confirmation.

    Args:
        deal_id: The deal ID to update.
        name: New name (optional).
        budget: New budget (optional).
        status_id: New status (optional).
    """
    kommo = _get_kommo(config)
    if not kommo:
        return _CRM_UNAVAILABLE

    args = {"deal_id": deal_id, "name": name, "budget": budget, "status_id": status_id}
    preview = format_hitl_preview("crm_update_lead", args)
    response = hitl_guard("crm_update_lead", preview, args)

    if response.get("action") != "approve":
        return "Операция отменена пользователем."

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
    """Find or create a contact by phone number. Requires confirmation.

    Args:
        phone: Phone number (used for dedup search).
        first_name: Contact first name.
        last_name: Optional last name.
        email: Optional email.
    """
    kommo = _get_kommo(config)
    if not kommo:
        return _CRM_UNAVAILABLE

    args = {"phone": phone, "first_name": first_name, "last_name": last_name, "email": email}
    preview = format_hitl_preview("crm_upsert_contact", args)
    response = hitl_guard("crm_upsert_contact", preview, args)

    if response.get("action") != "approve":
        return "Операция отменена пользователем."

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


@tool
@observe(name="crm-search-leads")
async def crm_search_leads(query: str, config: RunnableConfig) -> str:
    """Search deals/leads in CRM by name, keywords, or phone.

    Args:
        query: Search query (name, keywords, phone number).
    """
    kommo = _get_kommo(config)
    if not kommo:
        return _CRM_UNAVAILABLE

    try:
        leads = await kommo.search_leads(query=query, limit=10)
        if not leads:
            return f"Сделки по запросу «{query}» не найдены."
        lines = []
        for lead in leads:
            budget_str = f", бюджет: {lead.budget}" if lead.budget else ""
            lines.append(f"- {lead.name or 'Без названия'} (ID: {lead.id}{budget_str})")
        return "\n".join(lines)
    except Exception as e:
        logger.exception("crm_search_leads failed")
        return f"Ошибка при поиске сделок: {e}"


@tool
@observe(name="crm-get-my-leads")
async def crm_get_my_leads(config: RunnableConfig) -> str:
    """Get leads assigned to the current manager."""
    kommo = _get_kommo(config)
    if not kommo:
        return _CRM_UNAVAILABLE

    ctx = _get_ctx(config)
    manager_id = getattr(ctx, "manager_id", None) if ctx else None
    if manager_id is None:
        return "manager_id не настроен. Обратитесь к администратору."

    try:
        leads = await kommo.search_leads(responsible_user_id=manager_id, limit=20)
        if not leads:
            return "У вас нет активных сделок."
        lines = []
        for lead in leads:
            budget_str = f", бюджет: {lead.budget}" if lead.budget else ""
            lines.append(f"- {lead.name or 'Без названия'} (ID: {lead.id}{budget_str})")
        return "\n".join(lines)
    except Exception as e:
        logger.exception("crm_get_my_leads failed")
        return f"Ошибка при получении сделок: {e}"


@tool
@observe(name="crm-get-my-tasks")
async def crm_get_my_tasks(
    config: RunnableConfig,
    include_completed: bool = False,
) -> str:
    """Get tasks assigned to the current manager (overdue tasks highlighted).

    Args:
        include_completed: Include completed tasks (default: False).
    """
    import time

    kommo = _get_kommo(config)
    if not kommo:
        return _CRM_UNAVAILABLE

    ctx = _get_ctx(config)
    manager_id = getattr(ctx, "manager_id", None) if ctx else None
    if manager_id is None:
        return "manager_id не настроен. Обратитесь к администратору."

    try:
        is_completed = None if include_completed else False
        tasks = await kommo.get_tasks(responsible_user_id=manager_id, is_completed=is_completed)
        if not tasks:
            return "У вас нет активных задач."
        now = int(time.time())
        lines = []
        for task in tasks:
            overdue = ""
            if task.complete_till and task.complete_till < now and not task.is_completed:
                overdue = " ⚠️ ПРОСРОЧЕНО"
            lines.append(f"- {task.text or '(без текста)'} (ID: {task.id}){overdue}")
        return "\n".join(lines)
    except Exception as e:
        logger.exception("crm_get_my_tasks failed")
        return f"Ошибка при получении задач: {e}"


@tool
@observe(name="crm-update-contact")
async def crm_update_contact(
    contact_id: int,
    config: RunnableConfig,
    phone: str | None = None,
    email: str | None = None,
    first_name: str | None = None,
    last_name: str | None = None,
) -> str:
    """Update contact fields in CRM (phone, email, name). Requires confirmation.

    Args:
        contact_id: The Kommo contact ID.
        phone: New phone number (optional).
        email: New email address (optional).
        first_name: New first name (optional).
        last_name: New last name (optional).
    """
    kommo = _get_kommo(config)
    if not kommo:
        return _CRM_UNAVAILABLE

    args = {
        "contact_id": contact_id,
        "phone": phone,
        "email": email,
        "first_name": first_name,
        "last_name": last_name,
    }
    preview = format_hitl_preview("crm_update_contact", args)
    response = hitl_guard("crm_update_contact", preview, args)

    if response.get("action") != "approve":
        return "Операция отменена пользователем."

    try:
        custom_fields = ContactUpdate.build_contact_fields(phone=phone, email=email)
        update = ContactUpdate(
            first_name=first_name,
            last_name=last_name,
            custom_fields_values=custom_fields or None,
        )
        contact = await kommo.update_contact(contact_id, update)
        return f"Контакт обновлен: ID {contact.id}, {contact.first_name or ''}"
    except Exception as e:
        logger.exception("crm_update_contact failed")
        return f"Ошибка при обновлении контакта: {e}"


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
        crm_search_leads,
        crm_get_my_leads,
        crm_get_my_tasks,
        crm_update_contact,
    ]
