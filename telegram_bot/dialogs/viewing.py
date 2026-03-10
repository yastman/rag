"""Viewing appointment wizard dialog (aiogram-dialog)."""

from __future__ import annotations

import logging
import operator
import time
from typing import Any

from aiogram.types import (
    CallbackQuery,
    ContentType,
    Message,
    ReplyKeyboardRemove,
)
from aiogram_dialog import Dialog, DialogManager, ShowMode, StartMode, Window
from aiogram_dialog.widgets.input import MessageInput
from aiogram_dialog.widgets.kbd import Button, Column, Select
from aiogram_dialog.widgets.text import Const, Format  # noqa: F401

from telegram_bot.observability import observe

from .states import HandoffSG, ViewingSG


logger = logging.getLogger(__name__)


# --- Date range → label mapping ---

DATE_LABELS: dict[str, str] = {
    "nearest": "📅 Ближайшие дни",
    "next_week": "📅 Через неделю",
    "next_month": "📅 Через месяц",
    "unknown": "🤷 Не знаю когда",
    "phone": "📞 Согласуем по телефону",
}

# --- Due date offsets (seconds) ---

_DUE_OFFSETS: dict[str, int] = {
    "nearest": 3 * 86400,
    "next_week": 7 * 86400,
    "next_month": 30 * 86400,
    "unknown": 7 * 86400,
    "phone": 1 * 86400,
}


def compute_due_date(date_range: str) -> int:
    """Compute unix timestamp for CRM task due date."""
    return int(time.time()) + _DUE_OFFSETS.get(date_range, 7 * 86400)


# ── Getters ──────────────────────────────────────────────────────────


async def get_date_options(
    dialog_manager: DialogManager | None = None, **kwargs: Any
) -> dict[str, Any]:
    """Getter for date range selection (Step 1)."""
    items = list(DATE_LABELS.items())  # [(key, label), ...]
    # Flip to (label, key) for Select widget
    return {
        "title": "📅 Когда удобно осмотреть?",
        "items": [(label, key) for key, label in items],
        "btn_cancel": "✉ Написать менеджеру",
    }


async def get_phone_prompt(**kwargs: Any) -> dict[str, str]:
    """Getter for phone input (Step 2)."""
    return {
        "title": "📞 Введите ваш номер телефона\n\nНапример: +359 88 123 4567 или +380 50 123 4567",
        "btn_cancel": "✉ Написать менеджеру",
    }


async def get_summary_data(
    dialog_manager: DialogManager | Any = None, **kwargs: Any
) -> dict[str, Any]:
    """Build summary text from collected data (Step 3)."""
    data = dialog_manager.dialog_data if dialog_manager else {}

    date_range = data.get("date_range", "unknown")
    phone = data.get("phone", "—")

    date_label = DATE_LABELS.get(date_range, date_range)

    summary = f"📋 Ваша заявка на осмотр:\n\n📅 Дата: {date_label}\n\n📞 Телефон: {phone}"

    return {
        "summary_text": summary,
        "btn_confirm": "✅ Подтвердить",
        "btn_cancel": "✉ Написать менеджеру",
    }


# ── Shared CRM logic ────────────────────────────────────────────────


async def _restore_menu_keyboard(bot: Any, chat_id: int) -> None:
    """Restore client menu ReplyKeyboard after dialog completes."""
    from telegram_bot.keyboards.client_keyboard import build_client_keyboard

    await bot.send_message(
        chat_id=chat_id,
        text="✅ Заявка оформлена! Менеджер перезвонит вам в ближайшее время.",
        reply_markup=build_client_keyboard(),
    )


@observe(name="dialog-viewing-submit", capture_input=False, capture_output=False)
async def _submit_viewing_request(
    manager: DialogManager,
    phone: str,
    user: Any,
    bot: Any,
) -> None:
    """Submit viewing request to Kommo CRM (shared by on_confirm and contact share)."""
    from telegram_bot.handlers.phone_collector import (
        _build_custom_fields,
        build_display_name,
    )
    from telegram_bot.services.kommo_models import ContactCreate, LeadCreate, TaskCreate

    data = manager.dialog_data
    date_range = data.get("date_range", "unknown")

    display_name = build_display_name(user, phone)
    username = getattr(user, "username", None)
    user_id = user.id if user else 0

    logger.info(
        "submit_viewing: phone=%s date=%s user=%s",
        phone,
        date_range,
        user_id,
    )

    date_label = DATE_LABELS.get(date_range, date_range)

    kommo_client = manager.middleware_data.get("kommo_client")
    bot_config = manager.middleware_data.get("bot_config")

    if kommo_client is not None:
        try:
            contact_data = ContactCreate(
                first_name=user.first_name if user else "",
                last_name=getattr(user, "last_name", None) if user else None,
                phone=phone,
            )
            contact = await kommo_client.upsert_contact(phone, contact_data)

            pipeline_id = (bot_config.kommo_default_pipeline_id if bot_config else 0) or None
            status_id = (bot_config.kommo_new_status_id if bot_config else 0) or None
            responsible = (bot_config.kommo_responsible_user_id if bot_config else None) or None

            custom_fields = _build_custom_fields(
                "Запись на осмотр",
                user_id,
                username,
                service_field_id=(bot_config.kommo_service_field_id if bot_config else 0),
                source_field_id=(bot_config.kommo_source_field_id if bot_config else 0),
                telegram_field_id=(bot_config.kommo_telegram_field_id if bot_config else 0),
                telegram_username_field_id=(
                    bot_config.kommo_telegram_username_field_id if bot_config else 0
                ),
            )

            lead_name = f"Осмотр — {display_name}"
            lead = await kommo_client.create_lead(
                LeadCreate(  # type: ignore[call-arg]
                    name=lead_name,
                    pipeline_id=pipeline_id,
                    status_id=status_id,
                    responsible_user_id=responsible,
                    custom_fields_values=custom_fields or None,
                )
            )
            await kommo_client.link_contact_to_lead(lead.id, contact.id)

            note_text = f"Запись на осмотр\nТелефон: {phone}\nЖелаемая дата осмотра: {date_label}"
            if username:
                note_text += f"\nTelegram: @{username}"
            note_text += f"\nTelegram ID: {user_id}"
            await kommo_client.add_note("leads", lead.id, note_text)

            due_date = compute_due_date(date_range)
            task_text = f"Осмотр: {display_name} ({date_label})"
            await kommo_client.create_task(
                TaskCreate(
                    text=task_text,
                    entity_id=lead.id,
                    complete_till=due_date,
                )
            )

            logger.info(
                "Viewing lead created: lead_id=%s phone=%s date=%s",
                lead.id,
                phone,
                date_range,
            )
        except Exception:
            logger.exception("CRM viewing lead creation failed for phone=%s", phone)

    # Send confirmation + restore client menu keyboard
    await _restore_menu_keyboard(bot, user_id)
    logger.info("Viewing confirmation sent to user=%s", user_id)


# ── Handlers ─────────────────────────────────────────────────────────


async def _send_phone_reply_keyboard(callback: CallbackQuery) -> None:
    """Send ReplyKeyboard with 'Share Contact' button for phone step."""
    from telegram_bot.keyboards.phone_keyboard import build_phone_keyboard

    kb = build_phone_keyboard()
    await callback.bot.send_message(  # type: ignore[union-attr]
        chat_id=callback.from_user.id,
        text="👇 Нажмите кнопку ниже или введите номер вручную:",
        reply_markup=kb,
    )


async def on_cancel_to_manager(
    callback: CallbackQuery, button: Button, manager: DialogManager
) -> None:
    """Cancel viewing and redirect to manager handoff."""
    await manager.start(HandoffSG.goal, mode=StartMode.RESET_STACK)


async def on_date_selected(
    callback: CallbackQuery,
    widget: Select,
    manager: DialogManager,
    item_id: str,
) -> None:
    """Save date range and proceed to phone."""
    manager.dialog_data["date_range"] = item_id
    await _send_phone_reply_keyboard(callback)
    await manager.switch_to(ViewingSG.phone)


async def on_phone_text_received(message: Message, widget: Any, manager: DialogManager) -> None:
    """Handle phone number text input."""
    from telegram_bot.keyboards.phone_keyboard import (
        is_phone_cancel,
        normalize_phone,
        validate_phone,
    )

    text = message.text or ""
    logger.info("on_phone_text_received: raw=%r", text)

    # Handle cancel from ReplyKeyboard
    if is_phone_cancel(text):
        await message.answer("Запись отменена.", reply_markup=ReplyKeyboardRemove())
        await manager.done()
        return

    if not validate_phone(text):
        await message.answer("❌ Некорректный номер. Например: +359 88 123 4567")
        return
    phone = normalize_phone(text)
    if phone is None:
        await message.answer("❌ Некорректный номер. Например: +359 88 123 4567")
        return
    manager.dialog_data["phone"] = phone
    await message.answer("📞 Номер принят!", reply_markup=ReplyKeyboardRemove())
    manager.show_mode = ShowMode.DELETE_AND_SEND
    logger.info("on_phone_text_received: phone=%s, switching to summary", phone)
    await manager.switch_to(ViewingSG.summary)


async def on_phone_contact_received(message: Message, widget: Any, manager: DialogManager) -> None:
    """Handle shared contact (request_contact button) — auto-confirm."""
    if message.contact and message.contact.phone_number:
        from telegram_bot.keyboards.phone_keyboard import normalize_phone

        raw = message.contact.phone_number
        phone = normalize_phone(raw) or raw
        manager.dialog_data["phone"] = phone
        await message.answer("📞 Номер принят!", reply_markup=ReplyKeyboardRemove())

        # Auto-confirm: submit CRM and close dialog without summary step
        try:
            await _submit_viewing_request(
                manager=manager,
                phone=phone,
                user=message.from_user,
                bot=message.bot,
            )
        except Exception:
            logger.exception("Auto-confirm CRM failed for phone=%s", phone)

        manager.show_mode = ShowMode.EDIT
        await manager.done()
    else:
        await message.answer("❌ Не удалось получить номер. Введите вручную:")


@observe(name="dialog-viewing-confirm", capture_input=False, capture_output=False)
async def on_confirm(callback: CallbackQuery, button: Button, manager: DialogManager) -> None:
    """Submit viewing request to Kommo CRM and close dialog."""
    try:
        phone = manager.dialog_data.get("phone", "")
        await _submit_viewing_request(
            manager=manager,
            phone=phone,
            user=callback.from_user,
            bot=callback.bot,
        )
    except Exception:
        logger.exception("on_confirm failed for user=%s", getattr(callback.from_user, "id", "?"))

    # aiogram-dialog auto-answers callback; don't call callback.answer() manually
    await manager.done()


# ── Dialog Assembly ──────────────────────────────────────────────────

viewing_dialog = Dialog(
    # Step 1: Date range
    Window(
        Format("{title}"),
        Column(
            Select(
                Format("{item[0]}"),
                id="viewing_date",
                item_id_getter=operator.itemgetter(1),
                items="items",
                on_click=on_date_selected,
            ),
        ),
        Button(Format("{btn_cancel}"), id="cancel", on_click=on_cancel_to_manager),
        getter=get_date_options,
        state=ViewingSG.date,
    ),
    # Step 2: Phone input
    Window(
        Format("{title}"),
        MessageInput(
            on_phone_text_received,
            content_types=[ContentType.TEXT],
        ),
        MessageInput(
            on_phone_contact_received,
            content_types=[ContentType.CONTACT],
        ),
        Button(Format("{btn_cancel}"), id="cancel", on_click=on_cancel_to_manager),
        getter=get_phone_prompt,
        state=ViewingSG.phone,
    ),
    # Step 3: Summary + confirm
    Window(
        Format("{summary_text}"),
        Button(Format("{btn_confirm}"), id="confirm", on_click=on_confirm),
        Button(Format("{btn_cancel}"), id="cancel", on_click=on_cancel_to_manager),
        getter=get_summary_data,
        state=ViewingSG.summary,
    ),
)
