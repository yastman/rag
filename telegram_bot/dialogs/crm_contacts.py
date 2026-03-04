"""CRM Contact dialogs: submenu, create wizard, search (#697).

Dialogs:
  contacts_menu_dialog    — ContactsMenuSG.main  — navigation hub for contacts
  create_contact_dialog   — CreateContactSG.*    — multi-step wizard
  search_contacts_dialog  — SearchContactsSG.*   — search by query
"""

from __future__ import annotations

import logging
from typing import Any

from aiogram.types import CallbackQuery, Message
from aiogram_dialog import Dialog, DialogManager, Window
from aiogram_dialog.widgets.input import MessageInput, TextInput
from aiogram_dialog.widgets.kbd import Back, Button, Cancel, Column, Start
from aiogram_dialog.widgets.text import Format

from .crm_cards import format_contact_card
from .states import (
    ContactsMenuSG,
    CreateContactSG,
    SearchContactsSG,
)


logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Contacts Menu — getters & dialog
# ─────────────────────────────────────────────────────────────────────────────


async def get_contacts_menu_data(**kwargs: Any) -> dict[str, str]:
    """Getter: contacts submenu navigation labels."""
    return {
        "title": "👤 Контакты",
        "btn_create": "➕ Создать контакт",
        "btn_search": "🔍 Поиск",
        "btn_back": "← Назад",
    }


contacts_menu_dialog = Dialog(
    Window(
        Format("{title}"),
        Column(
            Start(
                Format("{btn_create}"),
                id="contacts_nav_create",
                state=CreateContactSG.first_name,
            ),
            Start(
                Format("{btn_search}"),
                id="contacts_nav_search",
                state=SearchContactsSG.query,
            ),
        ),
        Cancel(Format("{btn_back}")),
        getter=get_contacts_menu_data,
        state=ContactsMenuSG.main,
    ),
)


# ─────────────────────────────────────────────────────────────────────────────
# Create Contact Wizard — getters, handlers & dialog
# ─────────────────────────────────────────────────────────────────────────────


async def get_contact_first_name_prompt(**kwargs: Any) -> dict[str, str]:
    """Getter: first name input prompt."""
    return {
        "prompt": "Введите имя контакта:",
        "btn_cancel": "Отмена",
    }


async def get_contact_last_name_prompt(**kwargs: Any) -> dict[str, str]:
    """Getter: last name input prompt."""
    return {
        "prompt": "Введите фамилию контакта:",
        "btn_back": "← Назад",
    }


async def get_contact_phone_prompt(**kwargs: Any) -> dict[str, str]:
    """Getter: phone input prompt."""
    return {
        "prompt": "Введите телефон контакта (например: +79001234567):",
        "btn_back": "← Назад",
    }


async def get_contact_email_prompt(**kwargs: Any) -> dict[str, str]:
    """Getter: email input prompt (optional)."""
    return {
        "prompt": "Введите email контакта (или нажмите «Пропустить»):",
        "btn_skip": "Пропустить",
        "btn_back": "← Назад",
    }


async def get_contact_summary_data(dialog_manager: DialogManager, **kwargs: Any) -> dict[str, Any]:
    """Getter: contact preview for confirmation window."""
    data = dialog_manager.dialog_data
    first_name = data.get("first_name", "—")
    last_name = data.get("last_name", "")
    phone = data.get("phone", "—")
    email = data.get("email", "")

    full_name = f"{first_name} {last_name}".strip() if last_name else first_name
    lines = [
        "👤 Предпросмотр контакта:\n",
        f"Имя: {full_name}",
        f"Телефон: {phone}",
    ]
    if email:
        lines.append(f"Email: {email}")

    return {
        "summary_text": "\n".join(lines),
        "btn_confirm": "✅ Создать",
        "btn_edit": "✏️ Изменить имя",
        "btn_cancel": "Отмена",
    }


# Handlers


async def on_first_name_entered(
    message: Message,
    widget: TextInput,
    manager: DialogManager,
    text: str,
) -> None:
    """Save first name and advance to last name step."""
    manager.dialog_data["first_name"] = text.strip()
    await manager.switch_to(CreateContactSG.last_name)


async def on_last_name_entered(
    message: Message,
    widget: TextInput,
    manager: DialogManager,
    text: str,
) -> None:
    """Save last name and advance to phone step."""
    manager.dialog_data["last_name"] = text.strip()
    await manager.switch_to(CreateContactSG.phone)


async def on_phone_entered(
    message: Message,
    widget: TextInput,
    manager: DialogManager,
    text: str,
) -> None:
    """Save phone number and advance to email step."""
    manager.dialog_data["phone"] = text.strip()
    await manager.switch_to(CreateContactSG.email)


async def on_email_entered(
    message: Message,
    widget: TextInput,
    manager: DialogManager,
    text: str,
) -> None:
    """Save email and advance to summary."""
    manager.dialog_data["email"] = text.strip()
    await manager.switch_to(CreateContactSG.summary)


async def on_email_skip(
    callback: CallbackQuery,
    button: Button,
    manager: DialogManager,
) -> None:
    """Skip email entry and go to summary."""
    manager.dialog_data.pop("email", None)
    await manager.switch_to(CreateContactSG.summary)


async def on_contact_edit(
    callback: CallbackQuery,
    button: Button,
    manager: DialogManager,
) -> None:
    """Go back to first name step for editing."""
    await manager.switch_to(CreateContactSG.first_name)


async def on_contact_confirm(
    callback: CallbackQuery,
    button: Button,
    manager: DialogManager,
) -> None:
    """Confirm: call kommo.upsert_contact() and close wizard."""
    kommo = manager.middleware_data.get("kommo_client")
    if kommo is None:
        if callback.message is not None:
            await callback.message.answer("❌ CRM-интеграция недоступна.")
        return

    from telegram_bot.services.kommo_models import ContactCreate

    data = manager.dialog_data
    phone = data.get("phone", "")
    payload = ContactCreate(
        first_name=data.get("first_name", ""),
        last_name=data.get("last_name") or None,
        phone=phone or None,
        email=data.get("email") or None,
    )

    try:
        contact = await kommo.upsert_contact(phone, payload)
        text, keyboard = format_contact_card(contact)
        if callback.message is not None:
            await callback.message.answer(
                f"✅ Контакт создан!\n\n{text}",
                reply_markup=keyboard,
            )
    except Exception:
        logger.exception("Failed to create contact in Kommo")
        if callback.message is not None:
            await callback.message.answer("❌ Не удалось создать контакт. Попробуйте позже.")
        return

    await manager.done()


create_contact_dialog = Dialog(
    # Step 1: First name
    Window(
        Format("{prompt}"),
        TextInput(id="contact_first_name", on_success=on_first_name_entered),  # type: ignore[arg-type]
        Cancel(Format("{btn_cancel}")),
        getter=get_contact_first_name_prompt,
        state=CreateContactSG.first_name,
    ),
    # Step 2: Last name
    Window(
        Format("{prompt}"),
        TextInput(id="contact_last_name", on_success=on_last_name_entered),  # type: ignore[arg-type]
        Back(Format("{btn_back}")),
        getter=get_contact_last_name_prompt,
        state=CreateContactSG.last_name,
    ),
    # Step 3: Phone
    Window(
        Format("{prompt}"),
        TextInput(id="contact_phone", on_success=on_phone_entered),  # type: ignore[arg-type]
        Back(Format("{btn_back}")),
        getter=get_contact_phone_prompt,
        state=CreateContactSG.phone,
    ),
    # Step 4: Email (optional)
    Window(
        Format("{prompt}"),
        TextInput(id="contact_email", on_success=on_email_entered),  # type: ignore[arg-type]
        Button(Format("{btn_skip}"), id="email_skip", on_click=on_email_skip),
        Back(Format("{btn_back}")),
        getter=get_contact_email_prompt,
        state=CreateContactSG.email,
    ),
    # Step 5: Summary + Confirm
    Window(
        Format("{summary_text}"),
        Button(Format("{btn_confirm}"), id="contact_confirm", on_click=on_contact_confirm),
        Button(Format("{btn_edit}"), id="contact_edit", on_click=on_contact_edit),
        Cancel(Format("{btn_cancel}")),
        getter=get_contact_summary_data,
        state=CreateContactSG.summary,
    ),
)


# ─────────────────────────────────────────────────────────────────────────────
# Search Contacts — getters, handlers & dialog
# ─────────────────────────────────────────────────────────────────────────────


async def get_search_contacts_prompt(**kwargs: Any) -> dict[str, str]:
    """Getter: contact search prompt."""
    return {
        "prompt": "Введите имя или телефон для поиска контактов:",
        "btn_cancel": "Отмена",
    }


async def get_search_contacts_results(
    dialog_manager: DialogManager, **kwargs: Any
) -> dict[str, Any]:
    """Getter: execute contact search and format results."""
    kommo = dialog_manager.middleware_data.get("kommo_client")
    query = dialog_manager.dialog_data.get("search_query", "")

    results_text = "Ничего не найдено."

    if kommo is not None and query:
        try:
            contacts = await kommo.get_contacts(query=query)
            if contacts:
                cards = []
                for contact in contacts:
                    text, _ = format_contact_card(contact)
                    cards.append(text)
                results_text = "\n\n".join(cards)
        except Exception:
            logger.exception("Failed to search contacts in Kommo")
            results_text = "Ошибка поиска. Попробуйте позже."
    elif not kommo:
        results_text = "CRM-интеграция недоступна."

    return {
        "title": f'🔍 Контакты: "{query}"',
        "results_text": results_text,
        "btn_back": "← Назад",
        "btn_cancel": "Закрыть",
    }


async def on_search_contacts_query(
    message: Message,
    widget: MessageInput,
    manager: DialogManager,
) -> None:
    """Save search query and switch to results."""
    manager.dialog_data["search_query"] = message.text or ""
    await manager.switch_to(SearchContactsSG.results)


search_contacts_dialog = Dialog(
    # Step 1: Query input
    Window(
        Format("{prompt}"),
        MessageInput(func=on_search_contacts_query),
        Cancel(Format("{btn_cancel}")),
        getter=get_search_contacts_prompt,
        state=SearchContactsSG.query,
    ),
    # Step 2: Results
    Window(
        Format("{title}\n\n{results_text}"),
        Back(Format("{btn_back}")),
        Cancel(Format("{btn_cancel}")),
        getter=get_search_contacts_results,
        state=SearchContactsSG.results,
    ),
)
