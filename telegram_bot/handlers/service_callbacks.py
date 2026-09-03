"""Service / CTA / FAQ callback handler Router (#2980).

Factory ``create_service_router(bot)`` returns an aiogram Router that
registers the ``svc:``, ``cta:``, and ``ask:`` callback handlers.
The actual handler logic lives in ``telegram_bot.handlers.catalog``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery


if TYPE_CHECKING:
    from telegram_bot.bot import PropertyBot


def create_service_router(bot: PropertyBot) -> Router:
    """Return a router with service/CTA/ask callback handlers bound to *bot*."""
    from telegram_bot.handlers import catalog as _bot_catalog

    router = Router(name="service_callbacks")

    async def _handle_service(callback: CallbackQuery, i18n: Any = None) -> None:
        await _bot_catalog.handle_service_callback(bot, callback, i18n)

    async def _handle_cta(
        callback: CallbackQuery,
        state: FSMContext,
        dialog_manager: Any = None,
    ) -> None:
        await _bot_catalog.handle_cta_callback(bot, callback, state, dialog_manager)

    async def _handle_ask(
        callback: CallbackQuery,
        state: FSMContext | None = None,
        dialog_manager: Any = None,
    ) -> None:
        await _bot_catalog.handle_ask_callback(
            bot,
            callback,
            state=state,
            dialog_manager=dialog_manager,
        )

    router.callback_query.register(_handle_service, F.data.startswith("svc:"))
    router.callback_query.register(_handle_cta, F.data.startswith("cta:"))
    router.callback_query.register(_handle_ask, F.data.startswith("ask:"))
    return router
