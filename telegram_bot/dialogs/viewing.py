"""Viewing appointment wizard dialog (aiogram-dialog)."""

from __future__ import annotations

import logging
import operator
import time
from typing import Any

from aiogram.types import (
    CallbackQuery,
    ContentType,
    KeyboardButton,
    Message,
    ReplyKeyboardMarkup,
)
from aiogram_dialog import Dialog, DialogManager, Window
from aiogram_dialog.widgets.input import MessageInput
from aiogram_dialog.widgets.kbd import Back, Button, Cancel, Column, Select
from aiogram_dialog.widgets.text import Const, Format  # noqa: F401

from .states import ViewingSG


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


def build_phone_keyboard() -> ReplyKeyboardMarkup:
    """Build temporary ReplyKeyboard with request_contact button."""
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📱 Отправить мой номер", request_contact=True)],
        ],
        resize_keyboard=True,
        one_time_keyboard=True,
    )


# ── Getters ──────────────────────────────────────────────────────────


async def get_objects_options(
    event_from_user: Any = None,
    favorites_service: Any = None,
    middleware_data: dict[str, Any] | None = None,
    dialog_manager: DialogManager | None = None,
    **kwargs: Any,
) -> dict[str, Any]:
    """Load user favorites for object selection (Step 1)."""
    items: list[tuple[str, str]] = []
    has_favorites = False
    favorites_by_id: dict[str, dict[str, Any]] = {}

    resolved_favorites_service = favorites_service
    if resolved_favorites_service is None:
        resolved_favorites_service = (middleware_data or {}).get("favorites_service")
    if resolved_favorites_service is None:
        property_bot = (middleware_data or {}).get("property_bot")
        if property_bot is not None:
            resolved_favorites_service = getattr(property_bot, "_favorites_service", None)

    if resolved_favorites_service is not None and event_from_user is not None:
        try:
            favs = await resolved_favorites_service.list(event_from_user.id, limit=10)
            for fav in favs:
                data = fav.property_data
                property_id = str(fav.property_id)
                complex_name = data.get("complex_name", "?")
                property_type = data.get("property_type", "")
                area = data.get("area_m2", "")
                area_suffix = f"{area}м²" if area not in ("", None) else ""
                label = (f"{complex_name} {property_type} {area_suffix}").strip()
                items.append((label, property_id))
                favorites_by_id[property_id] = {
                    "id": property_id,
                    "complex_name": complex_name,
                    "property_type": property_type,
                    "area_m2": data.get("area_m2", 0),
                    "price_eur": data.get("price_eur", 0),
                }
            has_favorites = len(items) > 0
        except Exception:
            logger.exception("Failed to load favorites for viewing wizard")

    if dialog_manager is not None:
        dialog_manager.dialog_data["favorites_by_id"] = favorites_by_id

    return {
        "title": "🏠 Выберите объекты для осмотра:",
        "items": items,
        "has_favorites": has_favorites,
        "btn_manual": "📝 Ввести вручную",
        "btn_skip": "⏭ Пропустить",
        "btn_next": "▶ Далее",
        "btn_back": "◀ Назад",
    }


async def get_objects_text_prompt(**kwargs: Any) -> dict[str, str]:
    """Getter for free-text object input (Step 1b)."""
    return {
        "title": "📝 Опишите, какие объекты хотите посмотреть:",
        "btn_back": "◀ Назад",
    }


async def get_date_options(**kwargs: Any) -> dict[str, Any]:
    """Getter for date range selection (Step 2)."""
    items = list(DATE_LABELS.items())  # [(key, label), ...]
    # Flip to (label, key) for Select widget
    return {
        "title": "📅 Когда удобно осмотреть?",
        "items": [(label, key) for key, label in items],
        "btn_back": "◀ Назад",
    }


async def get_phone_prompt(**kwargs: Any) -> dict[str, str]:
    """Getter for phone input (Step 3)."""
    return {
        "title": (
            "📞 Введите номер телефона в формате +380990091392\n"
            "или нажмите кнопку «📱 Отправить мой номер» ниже."
        ),
        "btn_back": "◀ Назад",
    }


async def get_summary_data(
    dialog_manager: DialogManager | Any = None, **kwargs: Any
) -> dict[str, Any]:
    """Build summary text from collected data (Step 4)."""
    data = dialog_manager.dialog_data if dialog_manager else {}

    objects = data.get("selected_objects", [])
    manual_text = data.get("manual_text", "")
    date_range = data.get("date_range", "unknown")
    phone = data.get("phone", "—")

    # Format objects
    if objects:
        obj_lines = []
        for obj in objects:
            name = obj.get("complex_name", "?")
            ptype = obj.get("property_type", "")
            obj_lines.append(f"  • {name} {ptype}".strip())
        objects_text = "\n".join(obj_lines)
    elif manual_text:
        objects_text = f"  {manual_text}"
    else:
        objects_text = "  Не указаны (менеджер подберёт)"

    date_label = DATE_LABELS.get(date_range, date_range)

    summary = (
        f"📋 Ваша заявка на осмотр:\n\n"
        f"🏠 Объекты:\n{objects_text}\n\n"
        f"📅 Дата: {date_label}\n\n"
        f"📞 Телефон: {phone}"
    )

    return {
        "summary_text": summary,
        "btn_confirm": "✅ Подтвердить",
        "btn_edit": "✏ Изменить",
        "btn_cancel": "❌ Отмена",
    }


# ── Handlers ─────────────────────────────────────────────────────────


async def on_object_selected(
    callback: CallbackQuery,
    widget: Select,
    manager: DialogManager,
    item_id: str,
) -> None:
    """Toggle object selection (multi-select via dialog_data list)."""
    item_key = str(item_id)
    selected: list[dict[str, Any]] = manager.dialog_data.get("selected_objects", [])
    # Check if already selected → remove (toggle)
    existing_ids = [str(obj.get("id", obj.get("property_id", ""))) for obj in selected]
    if item_key in existing_ids:
        selected = [
            obj for obj in selected if str(obj.get("id", obj.get("property_id", ""))) != item_key
        ]
    else:
        favorites_by_id = manager.dialog_data.get("favorites_by_id", {})
        selected_obj = favorites_by_id.get(item_key, {"id": item_key})
        selected.append(dict(selected_obj))
    manager.dialog_data["selected_objects"] = selected


async def on_objects_next(callback: CallbackQuery, button: Button, manager: DialogManager) -> None:
    """Proceed to date selection with selected objects."""
    await manager.switch_to(ViewingSG.date)


async def on_objects_skip(callback: CallbackQuery, button: Button, manager: DialogManager) -> None:
    """Skip object selection, proceed to date."""
    manager.dialog_data["selected_objects"] = []
    await manager.switch_to(ViewingSG.date)


async def on_objects_manual(
    callback: CallbackQuery, button: Button, manager: DialogManager
) -> None:
    """Switch to free-text object input."""
    await manager.switch_to(ViewingSG.objects_text)


async def on_manual_text_received(message: Message, widget: Any, manager: DialogManager) -> None:
    """Save manual text and proceed to date."""
    manager.dialog_data["manual_text"] = message.text or ""
    await manager.switch_to(ViewingSG.date)


async def on_date_selected(
    callback: CallbackQuery,
    widget: Select,
    manager: DialogManager,
    item_id: str,
) -> None:
    """Save date range, send request_contact keyboard and proceed to phone."""
    manager.dialog_data["date_range"] = item_id
    # Send request_contact keyboard
    if callback.message:
        kb = build_phone_keyboard()
        await callback.message.answer(
            "📞 Введите номер в формате +380990091392\nили воспользуйтесь кнопкой:",
            reply_markup=kb,
        )
    await manager.switch_to(ViewingSG.phone)


async def on_phone_text_received(message: Message, widget: Any, manager: DialogManager) -> None:
    """Handle phone number text input."""
    from telegram_bot.handlers.phone_collector import normalize_phone, validate_phone

    text = message.text or ""
    if not validate_phone(text):
        await message.answer("❌ Некорректный номер. Введите в формате +380990091392:")
        return
    phone = normalize_phone(text)
    if phone is None:
        await message.answer("❌ Некорректный номер. Введите в формате +380990091392:")
        return
    manager.dialog_data["phone"] = phone
    await manager.switch_to(ViewingSG.summary)


async def on_phone_contact_received(message: Message, widget: Any, manager: DialogManager) -> None:
    """Handle shared contact (request_contact button)."""
    if message.contact and message.contact.phone_number:
        from telegram_bot.handlers.phone_collector import normalize_phone

        raw = message.contact.phone_number
        phone = normalize_phone(raw) or raw
        manager.dialog_data["phone"] = phone
        await manager.switch_to(ViewingSG.summary)
    else:
        await message.answer("❌ Не удалось получить номер. Введите вручную:")


async def on_confirm(callback: CallbackQuery, button: Button, manager: DialogManager) -> None:
    """Submit viewing request to Kommo CRM and close dialog."""
    from telegram_bot.handlers.phone_collector import (
        _build_custom_fields,
        _build_note_text,
        build_display_name,
    )
    from telegram_bot.services.kommo_models import ContactCreate, LeadCreate, TaskCreate

    data = manager.dialog_data
    phone = data.get("phone", "")
    date_range = data.get("date_range", "unknown")
    selected_objects = data.get("selected_objects", [])
    manual_text = data.get("manual_text", "")

    user = callback.from_user
    display_name = build_display_name(user, phone)
    username = getattr(user, "username", None)
    user_id = user.id if user else 0

    # Build viewing_objects for note (reuse phone_collector format)
    viewing_objects = selected_objects or []

    # Build note with date info
    date_label = DATE_LABELS.get(date_range, date_range)
    extra_note = f"\nЖелаемая дата осмотра: {date_label}"
    if manual_text:
        extra_note += f"\nОписание объектов: {manual_text}"

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

            lead = await kommo_client.create_lead(
                LeadCreate(
                    name=f"Осмотр — {display_name}",
                    pipeline_id=pipeline_id,
                    status_id=status_id,
                    responsible_user_id=responsible,
                    custom_fields_values=custom_fields or None,
                )
            )
            await kommo_client.link_contact_to_lead(lead.id, contact.id)

            note_text = _build_note_text(
                "Запись на осмотр",
                phone,
                username,
                user_id,
                display_name,
                viewing_objects,
            )
            note_text += extra_note
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

    if callback.message:
        await callback.message.answer(
            "✅ Заявка принята! Менеджер свяжется с вами в ближайшее время."
        )
    await callback.answer()
    await manager.done()


async def on_edit(callback: CallbackQuery, button: Button, manager: DialogManager) -> None:
    """Go back to objects selection to edit."""
    await manager.switch_to(ViewingSG.objects)


# ── Dialog Assembly ──────────────────────────────────────────────────

viewing_dialog = Dialog(
    # Step 1: Objects from favorites
    Window(
        Format("{title}"),
        Column(
            Select(
                Format("{item[0]}"),
                id="viewing_objects",
                item_id_getter=operator.itemgetter(1),
                items="items",
                on_click=on_object_selected,
            ),
            when="has_favorites",
        ),
        Button(Format("{btn_manual}"), id="manual", on_click=on_objects_manual),
        Button(Format("{btn_next}"), id="next", on_click=on_objects_next),
        Button(Format("{btn_skip}"), id="skip", on_click=on_objects_skip),
        Cancel(Format("{btn_back}")),
        getter=get_objects_options,
        state=ViewingSG.objects,
    ),
    # Step 1b: Free-text object input
    Window(
        Format("{title}"),
        MessageInput(on_manual_text_received, content_types=[ContentType.TEXT]),
        Back(Format("{btn_back}")),
        getter=get_objects_text_prompt,
        state=ViewingSG.objects_text,
    ),
    # Step 2: Date range
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
        Back(Format("{btn_back}")),
        getter=get_date_options,
        state=ViewingSG.date,
    ),
    # Step 3: Phone input
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
        Back(Format("{btn_back}")),
        getter=get_phone_prompt,
        state=ViewingSG.phone,
    ),
    # Step 4: Summary + confirm
    Window(
        Format("{summary_text}"),
        Button(Format("{btn_confirm}"), id="confirm", on_click=on_confirm),
        Button(Format("{btn_edit}"), id="edit", on_click=on_edit),
        Cancel(Format("{btn_cancel}")),
        getter=get_summary_data,
        state=ViewingSG.summary,
    ),
)
