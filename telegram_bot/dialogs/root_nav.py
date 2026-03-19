"""Shared client root navigation helpers."""

from __future__ import annotations

import inspect
from typing import Any

from aiogram.types import CallbackQuery
from aiogram_dialog import DialogManager, StartMode
from aiogram_dialog.widgets.kbd import Button
from aiogram_dialog.widgets.text import Format

from telegram_bot.dialogs.states import ClientMenuSG


def get_main_menu_label(i18n: Any | None = None) -> str:
    """Return localized label for the shared client root button."""
    if i18n is None:
        return "🏠 Главное меню"
    return i18n.get("main-menu")


async def on_back_to_main_menu(
    callback: CallbackQuery,
    button: Button,
    manager: DialogManager,
) -> None:
    """Reset active scenario and return to the client root dialog."""
    middleware = getattr(manager, "middleware_data", None) or {}
    state = middleware.get("state") if isinstance(middleware, dict) else None
    if state is not None:
        maybe_clear = state.clear()
        if inspect.isawaitable(maybe_clear):
            await maybe_clear
    await manager.start(ClientMenuSG.main, mode=StartMode.RESET_STACK)


def root_menu_button(widget_id: str = "main_menu") -> Button:
    """Build a shared root-navigation button for client dialogs."""
    return Button(Format("{btn_main_menu}"), id=widget_id, on_click=on_back_to_main_menu)
