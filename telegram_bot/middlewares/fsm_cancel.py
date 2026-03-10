"""Global FSM cancel middleware."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from telegram_bot.keyboards.client_keyboard import build_client_keyboard


_CANCEL_TRIGGERS = frozenset({"/cancel", "отмена", "cancel", "❌ отмена"})


class FSMCancelMiddleware(BaseMiddleware):
    """Intercept cancel commands in any FSM state and clear it."""

    async def __call__(
        self,
        handler: Callable[[Message, dict[str, Any]], Awaitable[Any]],
        event: Message,
        data: dict[str, Any],
    ) -> Any:
        state: FSMContext | None = data.get("state")
        if not state:
            return await handler(event, data)

        text = (event.text or "").strip().lower()
        if text not in _CANCEL_TRIGGERS:
            return await handler(event, data)

        current = await state.get_state()
        if current is None:
            return await handler(event, data)

        await state.clear()
        await event.answer(
            "😊 Заявка отменена. Когда будете готовы — мы на связи!",
            reply_markup=build_client_keyboard(),
        )
        return None
