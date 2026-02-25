# telegram_bot/handlers/phone_collector.py
"""Phone collection FSM for lead capture (#628)."""

from __future__ import annotations

import logging
import re
import time
from typing import Any

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

from telegram_bot.services.kommo_models import ContactCreate, LeadCreate, TaskCreate


logger = logging.getLogger(__name__)

_PHONE_PATTERN = re.compile(r"^\+?\d{7,15}$")


class PhoneCollectorStates(StatesGroup):
    """FSM states for phone collection."""

    waiting_phone = State()


def validate_phone(text: str) -> bool:
    """Validate phone number format."""
    cleaned = re.sub(r"[\s\-\(\)]", "", text)
    return bool(_PHONE_PATTERN.match(cleaned))


async def start_phone_collection(
    message_or_callback: Message | CallbackQuery,
    state: FSMContext,
    *,
    source: str,
    source_detail: str = "",
    i18n: Any | None = None,
) -> None:
    """Start phone collection flow. Called from various handlers."""
    await state.set_state(PhoneCollectorStates.waiting_phone)
    await state.update_data(lead_source=source, lead_detail=source_detail)

    text = i18n.get("phone-prompt") if i18n else "Введите ваш номер телефона:"
    if isinstance(message_or_callback, CallbackQuery) and message_or_callback.message:
        await message_or_callback.message.answer(text)
        await message_or_callback.answer()
    else:
        await message_or_callback.answer(text)  # type: ignore[union-attr]


async def on_phone_received(
    message: Message,
    state: FSMContext,
    kommo_client: Any | None = None,
    i18n: Any | None = None,
) -> None:
    """Handle phone number input."""
    if not message.text or not validate_phone(message.text):
        phone_invalid = (
            i18n.get("phone-invalid")
            if i18n
            else "Пожалуйста, введите корректный номер телефона (например +380501234567):"
        )
        await message.answer(phone_invalid)
        return

    phone = message.text
    data = await state.get_data()
    source = data.get("lead_source", "unknown")
    source_detail = data.get("lead_detail", "")
    user_id = message.from_user.id if message.from_user else "unknown"
    user_name = message.from_user.first_name if message.from_user else ""

    await state.clear()

    logger.info(
        "Lead captured: phone=%s source=%s detail=%s user=%s",
        phone,
        source,
        source_detail,
        user_id,
    )

    if kommo_client is not None:
        try:
            contact = await kommo_client.upsert_contact(phone, ContactCreate(first_name=user_name))
            lead = await kommo_client.create_lead(
                LeadCreate(name=f"Заявка: {source} — {user_name}")
            )
            await kommo_client.link_contact_to_lead(lead.id, contact.id)
            await kommo_client.add_note(
                "leads",
                lead.id,
                f"Источник: {source}\nДетали: {source_detail}\nTelegram ID: {user_id}",
            )
            await kommo_client.create_task(
                TaskCreate(
                    text=f"Перезвонить: {phone} ({user_name})",
                    entity_id=lead.id,
                    complete_till=int(time.time()) + 86400,
                )
            )
        except Exception:
            logger.exception("CRM lead creation failed for phone=%s", phone)

    phone_success = (
        i18n.get("phone-success")
        if i18n
        else "Спасибо за заявку! Менеджер свяжется с вами в ближайшее время."
    )
    await message.answer(phone_success)


def create_phone_router() -> Router:
    """Create a fresh router instance for phone FSM handlers."""
    router = Router(name="phone_collector")
    router.message(PhoneCollectorStates.waiting_phone, F.text)(on_phone_received)
    return router
