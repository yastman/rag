"""CRM / cache management callback handler Router (#2980).

Factory ``create_crm_router(bot)`` returns an aiogram Router that
registers ``cc:`` (clear-cache) and ``hitl:`` (human-in-the-loop) callback
handlers. The clear-cache logic lives in
``telegram_bot._bot_crm_callbacks``; the HITL handler is a no-op stub
because the HITL send path was removed in #2943.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery

from telegram_bot.observability import observe


if TYPE_CHECKING:
    from telegram_bot.bot import PropertyBot


def create_crm_router(bot: PropertyBot) -> Router:
    """Return a router with CRM/cache callback handlers bound to *bot*."""
    from telegram_bot import _bot_crm_callbacks

    router = Router(name="crm_callbacks")

    @observe(name="cb-clearcache", capture_input=False, capture_output=False)
    async def _handle_clearcache(callback_query: CallbackQuery) -> None:
        await _bot_crm_callbacks.handle_clearcache_callback(bot, callback_query)

    @observe(name="telegram-hitl-callback", as_type="agent")
    async def _handle_hitl(callback: CallbackQuery, state: FSMContext) -> None:
        await callback.answer("Устарело")

    router.callback_query.register(_handle_clearcache, F.data.startswith("cc:"))
    router.callback_query.register(_handle_hitl, F.data.startswith("hitl:"))
    return router
