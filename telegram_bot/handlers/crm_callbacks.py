"""CRM / cache management callback handler Router (#2980).

Factory ``create_crm_router(bot)`` returns an aiogram Router that
registers the ``cc:`` (clear-cache) callback handler. The clear-cache logic
lives in ``telegram_bot.handlers.bot_crm_callbacks``. The obsolete ``hitl:``
callback registration (and the HITL send path behind it) was removed in
#2943 / #3211.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from aiogram import F, Router
from aiogram.types import CallbackQuery


if TYPE_CHECKING:
    from telegram_bot.bot import PropertyBot


def create_crm_router(bot: PropertyBot) -> Router:
    """Return a router with CRM/cache callback handlers bound to *bot*."""
    from telegram_bot.handlers import bot_crm_callbacks as _bot_crm_callbacks

    router = Router(name="crm_callbacks")

    async def _handle_clearcache(callback_query: CallbackQuery) -> None:
        await _bot_crm_callbacks.handle_clearcache_callback(bot, callback_query)

    router.callback_query.register(_handle_clearcache, F.data.startswith("cc:"))
    return router
