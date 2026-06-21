"""Results / property-card callback handler Router (#2980).

Factory ``create_results_router(bot)`` returns an aiogram Router that
registers ``results:`` and ``card:`` callback handlers.
The actual handler logic lives in ``telegram_bot._bot_catalog``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery

from telegram_bot.callback_data import ResultsCB


if TYPE_CHECKING:
    from telegram_bot.bot import PropertyBot


def create_results_router(bot: PropertyBot) -> Router:
    """Return a router with results/card callback handlers bound to *bot*."""
    from telegram_bot import _bot_catalog

    router = Router(name="results_callbacks")

    async def _handle_results(
        callback: CallbackQuery,
        state: FSMContext,
        callback_data: ResultsCB | None = None,
        dialog_manager: Any = None,
    ) -> None:
        await _bot_catalog.handle_results_callback(
            bot, callback, state, callback_data, dialog_manager
        )

    async def _handle_card(
        callback: CallbackQuery,
        state: FSMContext,
        dialog_manager: Any = None,
    ) -> None:
        await _bot_catalog.handle_card_callback(bot, callback, state, dialog_manager)

    router.callback_query.register(_handle_results, ResultsCB.filter())
    router.callback_query.register(_handle_card, F.data.startswith("card:"))
    return router
