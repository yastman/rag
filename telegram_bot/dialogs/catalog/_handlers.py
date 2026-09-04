"""Catalog message and callback handlers — routes reply-keyboard button presses."""

from __future__ import annotations

import contextlib
import inspect
from typing import Any

from aiogram.types import CallbackQuery, Message
from aiogram_dialog import DialogManager, ShowMode

from telegram_bot.dialogs.catalog._controls import (
    clear_catalog_controls,
    show_catalog_controls,
)
from telegram_bot.dialogs.catalog._runtime import (
    _callback_message,
    _get_state,
)
from telegram_bot.dialogs.catalog._search import (
    activate_catalog_state,
    load_next_catalog_page,
)
from telegram_bot.dialogs.root_nav import show_client_main_menu
from telegram_bot.keyboards.catalog_keyboard import parse_catalog_button


async def _handle_catalog_more_message(
    *,
    message: Message,
    manager: DialogManager,
    telegram_id: int | None = None,
) -> None:
    updated = await load_next_catalog_page(
        message=message,
        dialog_manager=manager,
        telegram_id=telegram_id
        if telegram_id is not None
        else (message.from_user.id if message.from_user else None),
    )
    await show_catalog_controls(message=message, dialog_manager=manager, runtime=updated)
    from telegram_bot.dialogs.states import CatalogSG

    await activate_catalog_state(dialog_manager=manager, state=CatalogSG.results)


async def _handle_catalog_filters_message(
    *,
    message: Message,
    manager: DialogManager,
) -> None:
    from aiogram_dialog import StartMode

    from telegram_bot.dialogs.states import FilterSG

    runtime = await clear_catalog_controls(message=message, dialog_manager=manager)
    await manager.start(
        FilterSG.hub,
        data={"filters": runtime.get("filters", {})},
        mode=StartMode.RESET_STACK,
        show_mode=ShowMode.SEND,
    )


async def _handle_catalog_home_message(
    *,
    message: Message,
    manager: DialogManager,
) -> None:
    await clear_catalog_controls(message=message, dialog_manager=manager)
    state = await _get_state(manager)
    if state is not None:
        maybe_clear = state.clear()
        if inspect.isawaitable(maybe_clear):
            await maybe_clear
    manager.show_mode = ShowMode.NO_UPDATE
    with contextlib.suppress(Exception):
        await manager.reset_stack(remove_keyboard=True)
    await show_client_main_menu(
        message,
        i18n=manager.middleware_data.get("i18n"),
        property_bot=manager.middleware_data.get("property_bot"),
    )


async def _handle_catalog_manager_message(
    *,
    message: Message,
    manager: DialogManager,
) -> None:
    property_bot = manager.middleware_data.get("property_bot")
    state = await _get_state(manager)
    if property_bot is not None and state is not None:
        await property_bot._handle_manager(
            message,
            state=state,
            dialog_manager=manager,
            i18n=manager.middleware_data.get("i18n"),
        )


async def _handle_catalog_viewing_message(
    *,
    message: Message,
    manager: DialogManager,
) -> None:
    property_bot = manager.middleware_data.get("property_bot")
    state = await _get_state(manager)
    if property_bot is not None and state is not None:
        await property_bot._handle_viewing(message, state, manager)


async def _handle_catalog_bookmarks_message(
    *,
    message: Message,
    manager: DialogManager,
) -> None:
    property_bot = manager.middleware_data.get("property_bot")
    state = await _get_state(manager)
    if property_bot is not None and state is not None:
        await property_bot._handle_bookmarks(message, state=state)


async def dispatch_catalog_text_action(
    *,
    message: Message,
    manager: DialogManager,
    i18n_hub: Any = None,
) -> bool:
    action_id = parse_catalog_button(
        message.text or "",
        i18n_hub=i18n_hub,
        i18n=manager.middleware_data.get("i18n"),
    )
    if action_id is None:
        return False

    manager.show_mode = ShowMode.NO_UPDATE
    if action_id == "catalog_more":
        await _handle_catalog_more_message(message=message, manager=manager)
    elif action_id == "catalog_filters":
        await _handle_catalog_filters_message(message=message, manager=manager)
    elif action_id == "catalog_bookmarks":
        await _handle_catalog_bookmarks_message(message=message, manager=manager)
    elif action_id == "catalog_viewing":
        await _handle_catalog_viewing_message(message=message, manager=manager)
    elif action_id == "catalog_manager":
        await _handle_catalog_manager_message(message=message, manager=manager)
    elif action_id == "catalog_home":
        await _handle_catalog_home_message(message=message, manager=manager)
    else:
        return False
    return True


async def on_catalog_more(
    callback: CallbackQuery,
    button: Any,
    manager: DialogManager,
) -> None:
    message = _callback_message(callback)
    if message is None:
        return
    await _handle_catalog_more_message(
        message=message,
        manager=manager,
        telegram_id=callback.from_user.id if callback.from_user else None,
    )


async def on_catalog_filters(
    callback: CallbackQuery,
    button: Any,
    manager: DialogManager,
) -> None:
    message = _callback_message(callback)
    if message is None:
        return
    await _handle_catalog_filters_message(message=message, manager=manager)


async def on_catalog_home(
    callback: CallbackQuery,
    button: Any,
    manager: DialogManager,
) -> None:
    message = _callback_message(callback)
    if message is None:
        return
    await _handle_catalog_home_message(message=message, manager=manager)


async def on_catalog_manager(
    callback: CallbackQuery,
    button: Any,
    manager: DialogManager,
) -> None:
    message = _callback_message(callback)
    if message is None:
        return
    await _handle_catalog_manager_message(message=message, manager=manager)


async def on_catalog_viewing(
    callback: CallbackQuery,
    button: Any,
    manager: DialogManager,
) -> None:
    message = _callback_message(callback)
    if message is None:
        return
    await _handle_catalog_viewing_message(message=message, manager=manager)


async def on_catalog_bookmarks(
    callback: CallbackQuery,
    button: Any,
    manager: DialogManager,
) -> None:
    message = _callback_message(callback)
    if message is None:
        return
    await _handle_catalog_bookmarks_message(message=message, manager=manager)


__all__ = [
    "dispatch_catalog_text_action",
    "on_catalog_bookmarks",
    "on_catalog_filters",
    "on_catalog_home",
    "on_catalog_manager",
    "on_catalog_more",
    "on_catalog_viewing",
]
