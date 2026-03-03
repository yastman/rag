# telegram_bot/handlers/phone_collector.py
"""Phone collection FSM for lead capture (#628)."""

from __future__ import annotations

import datetime
import logging
import re
import time
from typing import Any

import phonenumbers
from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

from telegram_bot.services.content_loader import get_phone_config
from telegram_bot.services.kommo_models import ContactCreate, LeadCreate, TaskCreate


logger = logging.getLogger(__name__)

_PHONE_PATTERN = re.compile(r"^\+?\d{7,15}$")


class PhoneCollectorStates(StatesGroup):
    """FSM states for phone collection."""

    waiting_phone = State()


def normalize_phone(raw: str, default_region: str = "BG") -> str | None:
    """Parse and validate phone via phonenumbers; return E164 or None if invalid.

    Tries with default_region first (for local numbers like 088...),
    then without region (for international +380, +7, etc.).
    """
    cleaned = re.sub(r"[\s\-\(\)]", "", raw)
    for region in (default_region, None):
        try:
            parsed = phonenumbers.parse(cleaned, region)
            if phonenumbers.is_valid_number(parsed):
                return phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)
        except phonenumbers.NumberParseException:
            continue
    return None


def validate_phone(text: str) -> bool:
    """Validate phone number format."""
    cleaned = re.sub(r"[\s\-\(\)]", "", text)
    return bool(_PHONE_PATTERN.match(cleaned))


def build_display_name(user: Any | None, phone: str) -> str:
    """Build human-readable display name with fallback chain."""
    if user and getattr(user, "first_name", None):
        last_initial = f" {user.last_name[0]}." if getattr(user, "last_name", None) else ""
        return f"{user.first_name}{last_initial}"
    if user and getattr(user, "username", None):
        return f"@{user.username}"
    return phone


def _build_custom_fields(
    crm_title: str,
    telegram_id: int | str,
    username: str | None,
    *,
    service_field_id: int = 0,
    source_field_id: int = 0,
    telegram_field_id: int = 0,
    telegram_username_field_id: int = 0,
) -> list[dict]:
    """Build Kommo custom_fields_values for lead."""
    fields: list[dict] = []

    if service_field_id:
        fields.append({"field_id": service_field_id, "values": [{"value": crm_title}]})
    if source_field_id:
        fields.append({"field_id": source_field_id, "values": [{"value": "Telegram-бот"}]})
    if telegram_field_id and telegram_id:
        fields.append({"field_id": telegram_field_id, "values": [{"value": str(telegram_id)}]})
    if telegram_username_field_id and username:
        fields.append(
            {"field_id": telegram_username_field_id, "values": [{"value": f"@{username}"}]}
        )
    return fields


def _build_note_text(
    crm_title: str,
    phone: str,
    username: str | None,
    telegram_id: int | str,
    display_name: str,
    viewing_objects: list[dict[str, Any]],
) -> str:
    """Build rich note text for CRM."""
    tg_link = (
        f"@{username} (tg://user?id={telegram_id})" if username else f"tg://user?id={telegram_id}"
    )
    now = datetime.datetime.now(tz=datetime.UTC).strftime("%Y-%m-%d %H:%M")

    lines = [
        "📋 Заявка из Telegram-бота",
        "",
        f"Услуга: {crm_title}",
        f"Телефон: {phone}",
        f"Telegram: {tg_link}",
        f"Имя в Telegram: {display_name}",
    ]

    if viewing_objects:
        lines.append("")
        lines.append("Интересующие объекты:")
        for obj in viewing_objects:
            name = obj.get("complex_name", "")
            prop_type = obj.get("property_type", "")
            area = obj.get("area_m2", "")
            price = obj.get("price_eur", "")
            prop_id = obj.get("id", "")
            if isinstance(price, (int, float)) and price:
                lines.append(f"- {name}, {prop_type} {area}м², €{price:,} (ID: {prop_id})")
            else:
                lines.append(f"- {name}, {prop_type} {area}м² (ID: {prop_id})")

    lines.append("")
    lines.append(f"Дата заявки: {now}")
    return "\n".join(lines)


async def start_phone_collection(
    message_or_callback: Message | CallbackQuery,
    state: FSMContext,
    *,
    service_key: str,
    viewing_objects: list[dict[str, Any]] | None = None,
) -> None:
    """Start phone collection flow. Called from various handlers."""
    config = get_phone_config(service_key)
    phone_prompt = (
        config["phone_prompt"]
        if config and "phone_prompt" in config
        else "Введите ваш номер телефона:"
    )

    await state.set_state(PhoneCollectorStates.waiting_phone)
    await state.update_data(service_key=service_key, viewing_objects=viewing_objects or [])

    if isinstance(message_or_callback, CallbackQuery) and message_or_callback.message:
        await message_or_callback.message.answer(phone_prompt)
        await message_or_callback.answer()
    else:
        await message_or_callback.answer(phone_prompt)  # type: ignore[union-attr]


async def on_phone_received(
    message: Message,
    state: FSMContext,
    kommo_client: Any | None = None,
    i18n: Any | None = None,
    bot_config: Any | None = None,
) -> None:
    """Handle phone number input."""
    if not message.text or not validate_phone(message.text):
        phone_invalid = (
            i18n.get("phone-invalid")
            if i18n
            else "Пожалуйста, введите корректный номер телефона.\nНапример: +359 88 123 4567"
        )
        await message.answer(phone_invalid)
        return

    phone = normalize_phone(message.text)
    if phone is None:
        phone_invalid = (
            i18n.get("phone-invalid")
            if i18n
            else "Пожалуйста, введите корректный номер телефона.\nНапример: +359 88 123 4567"
        )
        await message.answer(phone_invalid)
        return
    data = await state.get_data()
    service_key = data.get("service_key", "unknown")
    viewing_objects: list[dict[str, Any]] = data.get("viewing_objects", [])
    user = message.from_user
    user_id: int | str = user.id if user else "unknown"

    await state.clear()

    config = get_phone_config(service_key)
    crm_title = config.get("crm_title", service_key) if config else service_key
    phone_success = (
        config.get("phone_success", "Спасибо! Менеджер свяжется с вами в ближайшее время.")
        if config
        else "Спасибо! Менеджер свяжется с вами в ближайшее время."
    )

    display_name = build_display_name(user, phone)
    username = getattr(user, "username", None) if user else None

    logger.info(
        "Lead captured: phone=%s service_key=%s crm_title=%s user=%s",
        phone,
        service_key,
        crm_title,
        user_id,
    )

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
                crm_title,
                user_id,
                username,
                service_field_id=bot_config.kommo_service_field_id if bot_config else 0,
                source_field_id=bot_config.kommo_source_field_id if bot_config else 0,
                telegram_field_id=bot_config.kommo_telegram_field_id if bot_config else 0,
                telegram_username_field_id=bot_config.kommo_telegram_username_field_id
                if bot_config
                else 0,
            )

            lead = await kommo_client.create_lead(
                LeadCreate(
                    name=f"{crm_title} — {display_name}",
                    pipeline_id=pipeline_id,
                    status_id=status_id,
                    responsible_user_id=responsible,
                    custom_fields_values=custom_fields or None,
                )
            )
            await kommo_client.link_contact_to_lead(lead.id, contact.id)

            note_text = _build_note_text(
                crm_title, phone, username, user_id, display_name, viewing_objects
            )
            await kommo_client.add_note("leads", lead.id, note_text)

            await kommo_client.create_task(
                TaskCreate(
                    text=f"Перезвонить: {phone} ({display_name}) — {crm_title}",
                    entity_id=lead.id,
                    complete_till=int(time.time()) + 86400,
                )
            )
        except Exception:
            logger.exception("CRM lead creation failed for phone=%s", phone)

    await message.answer(phone_success)


def create_phone_router() -> Router:
    """Create a fresh router instance for phone FSM handlers."""
    router = Router(name="phone_collector")
    router.message(PhoneCollectorStates.waiting_phone, F.text)(on_phone_received)
    return router
