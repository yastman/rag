"""Tests for CRM foundation: states, card formatters (#697)."""

from __future__ import annotations

from telegram_bot.dialogs.states import (
    AIAdvisorSG,
    CreateContactSG,
    CreateLeadSG,
    CreateNoteSG,
    CreateTaskSG,
    CRMMenuSG,
    SearchSG,
)


# --- FSM States ---


def test_crm_menu_sg_has_main():
    """CRMMenuSG has 'main' state."""
    assert hasattr(CRMMenuSG, "main")


def test_create_lead_sg_states():
    """CreateLeadSG has wizard states: name, budget, pipeline, summary."""
    for state_name in ("name", "budget", "pipeline", "summary"):
        assert hasattr(CreateLeadSG, state_name), f"Missing state: {state_name}"


def test_create_contact_sg_states():
    """CreateContactSG has wizard states: first_name, last_name, phone, email, summary."""
    for state_name in ("first_name", "last_name", "phone", "email", "summary"):
        assert hasattr(CreateContactSG, state_name), f"Missing state: {state_name}"


def test_create_task_sg_states():
    """CreateTaskSG has wizard states: text, due_date, lead_id, summary."""
    for state_name in ("text", "due_date", "lead_id", "summary"):
        assert hasattr(CreateTaskSG, state_name), f"Missing state: {state_name}"


def test_create_note_sg_states():
    """CreateNoteSG has wizard states: entity_type, entity_id, text, summary."""
    for state_name in ("entity_type", "entity_id", "text", "summary"):
        assert hasattr(CreateNoteSG, state_name), f"Missing state: {state_name}"


def test_search_sg_states():
    """SearchSG has states: query, results."""
    for state_name in ("query", "results"):
        assert hasattr(SearchSG, state_name), f"Missing state: {state_name}"


def test_ai_advisor_sg_has_main():
    """AIAdvisorSG has 'main' state."""
    assert hasattr(AIAdvisorSG, "main")


# --- Card Formatters ---


def test_format_lead_card_returns_text_and_keyboard():
    """format_lead_card returns (str, InlineKeyboardMarkup)."""
    from aiogram.types import InlineKeyboardMarkup

    from telegram_bot.dialogs.crm_cards import format_lead_card
    from telegram_bot.services.kommo_models import Lead

    lead = Lead(id=1, name="Test Deal", budget=75000, pipeline_id=10, status_id=5)
    text, keyboard = format_lead_card(lead)

    assert isinstance(text, str)
    assert "1" in text
    assert "Test Deal" in text
    assert isinstance(keyboard, InlineKeyboardMarkup)


def test_format_lead_card_callback_prefixes():
    """Lead card inline buttons use crm:lead: prefix."""
    from telegram_bot.dialogs.crm_cards import format_lead_card
    from telegram_bot.services.kommo_models import Lead

    lead = Lead(id=42, name="Deal")
    _, keyboard = format_lead_card(lead)

    all_callbacks = [
        btn.callback_data for row in keyboard.inline_keyboard for btn in row if btn.callback_data
    ]
    assert any(cb.startswith("crm:lead:") for cb in all_callbacks)
    assert any("42" in cb for cb in all_callbacks)


def test_format_contact_card_returns_text_and_keyboard():
    """format_contact_card returns (str, InlineKeyboardMarkup)."""
    from aiogram.types import InlineKeyboardMarkup

    from telegram_bot.dialogs.crm_cards import format_contact_card
    from telegram_bot.services.kommo_models import Contact

    contact = Contact(id=5, first_name="Ivan", last_name="Petrov")
    text, keyboard = format_contact_card(contact)

    assert isinstance(text, str)
    assert "5" in text
    assert "Ivan" in text
    assert isinstance(keyboard, InlineKeyboardMarkup)


def test_format_contact_card_callback_prefixes():
    """Contact card inline buttons use crm:contact: prefix."""
    from telegram_bot.dialogs.crm_cards import format_contact_card
    from telegram_bot.services.kommo_models import Contact

    contact = Contact(id=7, first_name="Anna")
    _, keyboard = format_contact_card(contact)

    all_callbacks = [
        btn.callback_data for row in keyboard.inline_keyboard for btn in row if btn.callback_data
    ]
    assert any(cb.startswith("crm:contact:") for cb in all_callbacks)


def test_format_task_card_active_task():
    """format_task_card for active task shows complete button."""
    from telegram_bot.dialogs.crm_cards import format_task_card
    from telegram_bot.services.kommo_models import Task

    task = Task(
        id=3,
        text="Call client",
        complete_till=1740000000,
        entity_id=10,
        entity_type="leads",
        is_completed=False,
    )
    text, keyboard = format_task_card(task)

    assert "3" in text
    assert "Call client" in text
    all_callbacks = [
        btn.callback_data for row in keyboard.inline_keyboard for btn in row if btn.callback_data
    ]
    assert any("complete" in cb for cb in all_callbacks)


def test_format_task_card_completed_task():
    """format_task_card for completed task shows reopen button."""
    from telegram_bot.dialogs.crm_cards import format_task_card
    from telegram_bot.services.kommo_models import Task

    task = Task(id=4, text="Done task", is_completed=True)
    text, keyboard = format_task_card(task)

    assert "✅" in text
    all_callbacks = [
        btn.callback_data for row in keyboard.inline_keyboard for btn in row if btn.callback_data
    ]
    assert any("reopen" in cb for cb in all_callbacks)


def test_build_pagination_buttons_first_page():
    """Pagination on first page shows only next button."""
    from telegram_bot.dialogs.crm_cards import build_pagination_buttons

    buttons = build_pagination_buttons(prefix="crm:lead:page", page=0, total=20, page_size=5)
    assert len(buttons) == 1
    assert "1" in buttons[0].callback_data  # next page = 1


def test_build_pagination_buttons_middle_page():
    """Pagination on middle page shows both prev and next buttons."""
    from telegram_bot.dialogs.crm_cards import build_pagination_buttons

    buttons = build_pagination_buttons(prefix="crm:lead:page", page=1, total=20, page_size=5)
    assert len(buttons) == 2


def test_build_pagination_buttons_last_page():
    """Pagination on last page shows only prev button."""
    from telegram_bot.dialogs.crm_cards import build_pagination_buttons

    buttons = build_pagination_buttons(prefix="crm:lead:page", page=3, total=20, page_size=5)
    assert len(buttons) == 1
    assert "2" in buttons[0].callback_data  # prev page = 2


def test_build_pagination_buttons_single_page():
    """Pagination with total <= page_size returns no buttons."""
    from telegram_bot.dialogs.crm_cards import build_pagination_buttons

    buttons = build_pagination_buttons(prefix="crm:lead:page", page=0, total=3, page_size=5)
    assert len(buttons) == 0


# --- KommoClient new methods ---


async def test_kommo_client_has_update_task():
    """KommoClient exposes update_task method."""
    from telegram_bot.services.kommo_client import KommoClient

    assert hasattr(KommoClient, "update_task")
    assert callable(KommoClient.update_task)


async def test_kommo_client_has_complete_task():
    """KommoClient exposes complete_task method."""
    from telegram_bot.services.kommo_client import KommoClient

    assert hasattr(KommoClient, "complete_task")
    assert callable(KommoClient.complete_task)


def test_task_update_model():
    """TaskUpdate model accepts partial fields."""
    from telegram_bot.services.kommo_models import TaskUpdate

    update = TaskUpdate(text="Updated text")
    assert update.text == "Updated text"
    assert update.complete_till is None
    assert update.responsible_user_id is None


def test_task_update_model_dump_excludes_none():
    """TaskUpdate.model_dump excludes None values for PATCH payload."""
    from telegram_bot.services.kommo_models import TaskUpdate

    update = TaskUpdate(text="New text")
    dumped = update.model_dump(exclude_none=True)
    assert dumped == {"text": "New text"}
    assert "complete_till" not in dumped
