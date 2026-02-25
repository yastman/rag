# telegram_bot/handlers/phone_collector.py
"""Phone collection FSM for lead capture (#628)."""

from __future__ import annotations

import logging
import re

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message


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
) -> None:
    """Start phone collection flow. Called from various handlers."""
    await state.set_state(PhoneCollectorStates.waiting_phone)
    await state.update_data(lead_source=source, lead_detail=source_detail)

    text = "Введите ваш номер телефона:"
    if isinstance(message_or_callback, CallbackQuery) and message_or_callback.message:
        await message_or_callback.message.answer(text)
        await message_or_callback.answer()
    else:
        await message_or_callback.answer(text)  # type: ignore[union-attr]


async def on_phone_received(message: Message, state: FSMContext) -> None:
    """Handle phone number input."""
    if not message.text or not validate_phone(message.text):
        await message.answer(
            "Пожалуйста, введите корректный номер телефона (например +380501234567):"
        )
        return

    data = await state.get_data()
    source = data.get("lead_source", "unknown")
    source_detail = data.get("lead_detail", "")

    await state.clear()

    # TODO: Create CRM lead/contact here (Task for CRM integration)
    logger.info(
        "Lead captured: phone=%s source=%s detail=%s user=%s",
        message.text,
        source,
        source_detail,
        message.from_user.id if message.from_user else "unknown",
    )

    await message.answer(
        "Спасибо за заявку! Менеджер свяжется с вами для уточнения деталей в ближайшее время."
    )


def create_phone_router() -> Router:
    """Create a fresh router instance for phone FSM handlers."""
    router = Router(name="phone_collector")
    router.message(PhoneCollectorStates.waiting_phone, F.text)(on_phone_received)
    return router
