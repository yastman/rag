"""Favorites / bookmarks callback handler Router (#2980).

Factory ``create_favorites_router(bot)`` returns an aiogram Router that
registers all ``fav:`` callback handlers.
The actual handler logic lives in ``telegram_bot._bot_favorites``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery

from telegram_bot.callback_data import FavoriteCB


if TYPE_CHECKING:
    from telegram_bot.bot import PropertyBot


def create_favorites_router(bot: PropertyBot) -> Router:
    """Return a router with favorites callback handlers bound to *bot*."""
    from telegram_bot import _bot_favorites

    router = Router(name="favorites_callbacks")

    async def _fav_add(
        callback: CallbackQuery,
        state: FSMContext,
        callback_data: FavoriteCB | None = None,
        dialog_manager: Any = None,
    ) -> None:
        await _bot_favorites.handle_fav_add(bot, callback, state, callback_data, dialog_manager)

    async def _fav_remove(
        callback: CallbackQuery,
        state: FSMContext,
        callback_data: FavoriteCB | None = None,
        dialog_manager: Any = None,
    ) -> None:
        await _bot_favorites.handle_fav_remove(bot, callback, state, callback_data, dialog_manager)

    async def _fav_viewing(
        callback: CallbackQuery,
        state: FSMContext,
        callback_data: FavoriteCB | None = None,
        dialog_manager: Any = None,
    ) -> None:
        await _bot_favorites.handle_fav_viewing(bot, callback, state, callback_data, dialog_manager)

    async def _fav_viewing_all(
        callback: CallbackQuery,
        state: FSMContext,
        callback_data: FavoriteCB | None = None,
        dialog_manager: Any = None,
    ) -> None:
        await _bot_favorites.handle_fav_viewing_all(
            bot, callback, state, callback_data, dialog_manager
        )

    async def _fav_legacy(
        callback: CallbackQuery,
        state: FSMContext,
        callback_data: FavoriteCB | None = None,
        dialog_manager: Any = None,
    ) -> None:
        await _bot_favorites.handle_favorite_callback(
            bot, callback, state, callback_data, dialog_manager
        )

    router.callback_query.register(_fav_add, FavoriteCB.filter(F.action == "add"))
    router.callback_query.register(_fav_remove, FavoriteCB.filter(F.action == "remove"))
    router.callback_query.register(_fav_viewing, FavoriteCB.filter(F.action == "viewing"))
    router.callback_query.register(_fav_viewing_all, FavoriteCB.filter(F.action == "viewing_all"))
    # Legacy buttons in old chat history may contain "fav:viewing_all" (without id part).
    router.callback_query.register(_fav_legacy, F.data == "fav:viewing_all")
    return router
