# telegram_bot/handlers/phone_collector.py
"""Phone collection FSM for lead capture (#628).

## Design exception: justified non-aiogram-dialog FSM (#1232 / #2055)

Telegram lead capture relies on a one-tap *contact share* button
(`KeyboardButton(request_contact=True)` rendered via
`ReplyKeyboardMarkup`). The native UX is:

  * the user sees a single big "Поделиться номером" button at the bottom
    of the chat,
  * one tap sends a `Contact` payload (verified phone, no manual typing),
  * fallback path accepts free-text phone input from users on clients
    that hide the keyboard or refuse contact share.

aiogram-dialog renders inline-keyboard `Select`/`Button` widgets above
the message and does **not** provide a `request_contact` widget.
Replacing the reply-keyboard contact share with an inline button would
force users to type their phone manually, which measurably reduces
opt-in rate for lead capture.

This module therefore stays as a raw aiogram `Router` + `StatesGroup`
implementation. The SDK registry calls this out at the bottom of the
aiogram-dialog gotchas section: it is the **single** intentional
exception to the "no custom FSM" rule.

If a future product decision accepts a weaker UX (no contact share),
or aiogram-dialog gains a native contact-share widget, drop this
exception and migrate. Until then, do not "consistency-refactor" this
file into aiogram-dialog. See #1232 (parent) and #2055 (this design
note).
"""

from __future__ import annotations

import logging
from typing import Any

from aiogram import F, Router
from aiogram.enums import ContentType
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

from telegram_bot.keyboards.phone_keyboard import (
    build_phone_keyboard,
    is_phone_attempt,
    normalize_phone,
    validate_phone,
)
from telegram_bot.observability import observe
from telegram_bot.services.content_loader import get_phone_config


logger = logging.getLogger(__name__)


class PhoneCollectorStates(StatesGroup):
    """FSM states for phone collection."""

    waiting_phone = State()


def _phone_log_state(phone: str | None) -> str:
    """Return a non-PII phone presence marker for application logs."""
    return "provided" if phone else "missing"


def build_display_name(user: Any | None, phone: str) -> str:
    """Build human-readable display name with fallback chain."""
    if user and getattr(user, "first_name", None):
        last_initial = f" {user.last_name[0]}." if getattr(user, "last_name", None) else ""
        return f"{user.first_name}{last_initial}"
    if user and getattr(user, "username", None):
        return f"@{user.username}"
    return phone


async def start_phone_collection(
    message_or_callback: Message | CallbackQuery,
    state: FSMContext,
    *,
    service_key: str,
    viewing_objects: list[dict[str, Any]] | None = None,
    prompt_text: str | None = None,
) -> None:
    """Start phone collection flow with reply keyboard."""
    await state.set_state(PhoneCollectorStates.waiting_phone)
    await state.update_data(service_key=service_key, viewing_objects=viewing_objects or [])

    kb = build_phone_keyboard()
    text = prompt_text or (
        "📞 Оставьте номер телефона, и мы свяжемся с вами:\n\n"
        "👇 Нажмите «Поделиться контактом» — это самый быстрый способ\n"
        "✍️ Или введите номер вручную (например, +380 99 009 13 92)"
    )

    if isinstance(message_or_callback, CallbackQuery) and message_or_callback.message:
        await message_or_callback.message.answer(text, reply_markup=kb)
        await message_or_callback.answer()
    else:
        await message_or_callback.answer(text, reply_markup=kb)  # type: ignore[union-attr]


@observe(name="phone-lead-capture", capture_input=False, capture_output=False)
async def _process_valid_phone(
    phone: str,
    message: Message,
    state: FSMContext,
    bot_config: Any | None = None,
    search_event_store: Any | None = None,
) -> None:
    """Process validated phone: log and send success message."""
    from telegram_bot.keyboards.client_keyboard import build_client_keyboard

    data = await state.get_data()
    service_key = data.get("service_key", "unknown")
    user = message.from_user
    user_id: int | str = user.id if user else "unknown"

    await state.clear()

    config = get_phone_config(service_key)
    phone_success = (
        config.get(
            "phone_success", "✅ Заявка оформлена! Менеджер перезвонит вам в ближайшее время."
        )
        if config
        else "✅ Заявка оформлена! Менеджер перезвонит вам в ближайшее время."
    )

    logger.info(
        "Phone collected: phone_state=%s service_key=%s user=%s",
        _phone_log_state(phone),
        service_key,
        user_id,
    )

    await message.answer(phone_success, reply_markup=build_client_keyboard())


async def on_phone_received(
    message: Message,
    state: FSMContext,
    i18n: Any | None = None,
    bot_config: Any | None = None,
    search_event_store: Any | None = None,
) -> None:
    """Handle phone number text input."""
    from telegram_bot.keyboards.client_keyboard import build_client_keyboard
    from telegram_bot.keyboards.phone_keyboard import is_phone_cancel

    text = message.text or ""

    if is_phone_cancel(text):
        await state.clear()
        await message.answer(
            "Обращение отменено.",
            reply_markup=build_client_keyboard(),
        )
        return

    if not is_phone_attempt(text):
        await state.clear()
        await message.answer(
            "Обращение отменено.",
            reply_markup=build_client_keyboard(),
        )
        return

    if not validate_phone(text):
        phone_invalid = (
            i18n.get("phone-invalid")
            if i18n
            else "Пожалуйста, введите корректный номер телефона.\nНапример: +359 88 123 4567"
        )
        await message.answer(phone_invalid)
        return

    phone = normalize_phone(text)
    if phone is None:
        phone_invalid = (
            i18n.get("phone-invalid")
            if i18n
            else "Пожалуйста, введите корректный номер телефона.\nНапример: +359 88 123 4567"
        )
        await message.answer(phone_invalid)
        return

    await _process_valid_phone(phone, message, state, bot_config, search_event_store)


async def on_phone_contact(
    message: Message,
    state: FSMContext,
    bot_config: Any | None = None,
    search_event_store: Any | None = None,
) -> None:
    """Handle shared contact via request_contact button."""
    if message.contact and message.contact.phone_number:
        phone = normalize_phone(message.contact.phone_number) or message.contact.phone_number
        await _process_valid_phone(phone, message, state, bot_config, search_event_store)
    else:
        await message.answer("Не удалось получить номер. Введите вручную:")


def create_phone_router() -> Router:
    """Create a fresh router instance for phone FSM handlers."""
    router = Router(name="phone_collector")
    router.message(PhoneCollectorStates.waiting_phone, F.text)(on_phone_received)
    router.message(PhoneCollectorStates.waiting_phone, F.content_type == ContentType.CONTACT)(
        on_phone_contact
    )
    return router
