"""Additional crm_cards branch coverage."""

from __future__ import annotations

from telegram_bot.dialogs.crm_cards import format_contact_card, format_task_card
from telegram_bot.services.kommo_models import Contact, Task


def test_format_contact_card_uses_dash_for_missing_name() -> None:
    text, _ = format_contact_card(Contact(id=7))

    assert "Имя: —" in text


def test_format_task_card_completed_task_has_reopen_button() -> None:
    _, keyboard = format_task_card(Task(id=12, text="Done", is_completed=True))

    callbacks = [btn.callback_data for row in keyboard.inline_keyboard for btn in row]
    assert "crm:task:reopen:12" in callbacks
