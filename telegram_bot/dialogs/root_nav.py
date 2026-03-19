"""Shared client root navigation helpers."""

from __future__ import annotations

import contextlib
import inspect
from typing import Any

from aiogram.types import CallbackQuery, Message
from aiogram_dialog import DialogManager
from aiogram_dialog.widgets.kbd import Button
from aiogram_dialog.widgets.text import Const, Format

from telegram_bot.keyboards.client_keyboard import build_client_keyboard
from telegram_bot.services.content_loader import load_services_config


def get_main_menu_label(i18n: Any | None = None) -> str:
    """Return localized label for the shared client root button."""
    if i18n is None:
        return "🏠 Главное меню"
    return i18n.get("main-menu")


async def show_client_main_menu(
    message: Message,
    *,
    i18n: Any | None = None,
) -> None:
    """Send the client root message with the persistent lower keyboard."""
    name = getattr(message.from_user, "first_name", "") or ""
    if i18n is not None:
        text = i18n.get("welcome-text", name=name)
    else:
        text = load_services_config().get("welcome", {}).get("text", "Добро пожаловать!")
        if name:
            text = text.replace("Привет! 👋", f"Привет, {name}! 👋", 1)
    await message.answer(text, reply_markup=build_client_keyboard(i18n=i18n))


async def on_back_to_main_menu(
    callback: CallbackQuery,
    button: Button,
    manager: DialogManager,
) -> None:
    """Reset active scenario and return to the client lower-menu root."""
    middleware = getattr(manager, "middleware_data", None) or {}
    state = middleware.get("state") if isinstance(middleware, dict) else None
    i18n = middleware.get("i18n") if isinstance(middleware, dict) else None
    if state is not None:
        maybe_clear = state.clear()
        if inspect.isawaitable(maybe_clear):
            await maybe_clear
    with contextlib.suppress(Exception):
        await manager.reset_stack(remove_keyboard=True)
    message = callback.message
    if message is not None:
        await show_client_main_menu(message, i18n=i18n)


def root_menu_button(widget_id: str = "main_menu") -> Button:
    """Build a shared root-navigation button for client dialogs."""
    return Button(Format("{btn_main_menu}"), id=widget_id, on_click=on_back_to_main_menu)


def back_to_main_menu_button(
    *,
    widget_id: str = "back_to_main_menu",
    text: str | None = None,
) -> Button:
    """Build a back button that safely returns to the client root dialog."""
    button_text = Const(text) if text is not None else Format("{btn_back}")
    return Button(button_text, id=widget_id, on_click=on_back_to_main_menu)
