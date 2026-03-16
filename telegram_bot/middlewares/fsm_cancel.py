"""Global FSM cancel middleware."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any, cast

from aiogram import BaseMiddleware
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, TelegramObject

from telegram_bot.keyboards.client_keyboard import build_client_keyboard


_CANCEL_TRIGGERS = frozenset({"/cancel", "отмена", "cancel", "❌ отмена"})


class FSMCancelMiddleware(BaseMiddleware):
    """Intercept cancel commands in any FSM state and clear it."""

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        msg: Message | None
        if isinstance(event, Message):
            msg = event
        elif hasattr(event, "text") and hasattr(event, "answer"):
            msg = cast(Message, event)
        else:
            msg = None

        if msg is None:
            return await handler(event, data)

        state: FSMContext | None = data.get("state")
        if not state:
            return await handler(event, data)

        text = (msg.text or "").strip().lower()
        if text not in _CANCEL_TRIGGERS:
            return await handler(event, data)

        current = await state.get_state()
        if current is None:
            return await handler(event, data)

        await state.clear()
        await msg.answer(
            "😊 Заявка отменена. Когда будете готовы — мы на связи!",
            reply_markup=build_client_keyboard(),
        )
        return None
