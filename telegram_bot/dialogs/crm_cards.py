"""CRM card formatting utilities for Telegram messages (#697).

Formats Lead, Contact, Task objects from Kommo API into Telegram-ready
text cards with inline keyboards. Supports pagination for list views.
"""

from __future__ import annotations

import datetime

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from telegram_bot.services.kommo_models import Contact, Lead, Task


# Callback prefix constants
_LEAD_PREFIX = "crm:lead"
_CONTACT_PREFIX = "crm:contact"
_TASK_PREFIX = "crm:task"

# Pagination defaults
PAGE_SIZE = 5


def format_lead_card(lead: Lead, task_count: int = 0) -> tuple[str, InlineKeyboardMarkup]:
    """Format a Lead as a Telegram text card with inline buttons.

    Args:
        lead: Lead object from Kommo API.
        task_count: number of open tasks linked to this lead (#731).

    Returns:
        (text, keyboard) — ready to use in bot.send_message() / edit_message_text().
    """
    budget_str = f"{lead.budget:,} €".replace(",", " ") if lead.budget else "не указан"

    contact_name = "—"
    if lead.contacts:
        first = lead.contacts[0]
        contact_name = first.get("name") or first.get("first_name") or "—"

    lines = [
        f"📋 *Сделка #{lead.id}*",
        f"Название: {lead.name or '—'}",
        f"Бюджет: {budget_str}",
        f"Контакт: {contact_name}",
        f"Задач: {task_count}",
    ]
    if lead.created_at:
        dt = datetime.datetime.fromtimestamp(lead.created_at, tz=datetime.UTC)
        lines.append(f"Создана: {dt.strftime('%d.%m.%Y')}")

    text = "\n".join(lines)

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✏️ Изменить",
                    callback_data=f"{_LEAD_PREFIX}:edit:{lead.id}",
                ),
                InlineKeyboardButton(
                    text="📝 Заметка",
                    callback_data=f"{_LEAD_PREFIX}:note:{lead.id}",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="✅ Задача",
                    callback_data=f"{_LEAD_PREFIX}:task:{lead.id}",
                ),
                InlineKeyboardButton(
                    text="🔗 Контакт",
                    callback_data=f"{_LEAD_PREFIX}:contact:{lead.id}",
                ),
            ],
        ]
    )
    return text, keyboard


def format_contact_card(contact: Contact) -> tuple[str, InlineKeyboardMarkup]:
    """Format a Contact as a Telegram text card with inline buttons.

    Returns:
        (text, keyboard) — ready to use in bot.send_message() / edit_message_text().
    """
    full_name = " ".join(part for part in [contact.first_name, contact.last_name] if part) or "—"

    lines = [
        f"👤 *Контакт #{contact.id}*",
        f"Имя: {full_name}",
    ]
    if contact.created_at:
        dt = datetime.datetime.fromtimestamp(contact.created_at, tz=datetime.UTC)
        lines.append(f"Создан: {dt.strftime('%d.%m.%Y')}")

    text = "\n".join(lines)

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✏️ Изменить",
                    callback_data=f"{_CONTACT_PREFIX}:edit:{contact.id}",
                ),
                InlineKeyboardButton(
                    text="📝 Заметка",
                    callback_data=f"{_CONTACT_PREFIX}:note:{contact.id}",
                ),
            ],
        ]
    )
    return text, keyboard


def format_task_card(task: Task) -> tuple[str, InlineKeyboardMarkup]:
    """Format a Task as a Telegram text card with inline buttons.

    Returns:
        (text, keyboard) — ready to use in bot.send_message() / edit_message_text().
    """
    status_icon = "✅" if task.is_completed else "🔲"
    due_str = "—"
    if task.complete_till:
        dt = datetime.datetime.fromtimestamp(task.complete_till, tz=datetime.UTC)
        due_str = dt.strftime("%d.%m.%Y %H:%M")

    lines = [
        f"{status_icon} *Задача #{task.id}*",
        f"Текст: {task.text or '—'}",
        f"Срок: {due_str}",
    ]
    if task.entity_id and task.entity_type:
        lines.append(f"Сущность: {task.entity_type} #{task.entity_id}")

    text = "\n".join(lines)

    buttons: list[list[InlineKeyboardButton]] = []
    if not task.is_completed:
        buttons.append(
            [
                InlineKeyboardButton(
                    text="✅ Завершить",
                    callback_data=f"{_TASK_PREFIX}:complete:{task.id}",
                ),
                InlineKeyboardButton(
                    text="⏰ Отложить",
                    callback_data=f"{_TASK_PREFIX}:postpone:{task.id}",
                ),
            ]
        )
        buttons.append(
            [
                InlineKeyboardButton(
                    text="✏️ Изменить",
                    callback_data=f"{_TASK_PREFIX}:edit:{task.id}",
                ),
            ]
        )
    else:
        buttons.append(
            [
                InlineKeyboardButton(
                    text="🔁 Переоткрыть",
                    callback_data=f"{_TASK_PREFIX}:reopen:{task.id}",
                ),
            ]
        )

    keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
    return text, keyboard


def build_pagination_buttons(
    *,
    prefix: str,
    page: int,
    total: int,
    page_size: int = PAGE_SIZE,
) -> list[InlineKeyboardButton]:
    """Build prev/next pagination buttons for CRM list views.

    Args:
        prefix: Callback data prefix (e.g. "crm:lead:page").
        page: Current 0-based page index.
        total: Total number of items.
        page_size: Items per page.

    Returns:
        List of InlineKeyboardButton for prev/next navigation.
    """
    buttons: list[InlineKeyboardButton] = []
    if page > 0:
        buttons.append(
            InlineKeyboardButton(
                text="◀ Назад",
                callback_data=f"{prefix}:{page - 1}",
            )
        )
    if (page + 1) * page_size < total:
        buttons.append(
            InlineKeyboardButton(
                text="Вперёд ▶",
                callback_data=f"{prefix}:{page + 1}",
            )
        )
    return buttons
