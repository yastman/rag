"""Catalog state owner with reply-keyboard navigation."""

from __future__ import annotations

import contextlib
import inspect
from typing import Any

from aiogram.enums import ContentType
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message, ReplyKeyboardRemove
from aiogram_dialog import Dialog, DialogManager, LaunchMode, ShowMode, StartMode, Window
from aiogram_dialog.widgets.input import MessageInput
from aiogram_dialog.widgets.text import Const

from telegram_bot.dialogs.root_nav import show_client_main_menu
from telegram_bot.dialogs.states import CatalogSG
from telegram_bot.keyboards.catalog_keyboard import build_catalog_keyboard, parse_catalog_button
from telegram_bot.services.catalog_rendering import send_catalog_results
from telegram_bot.services.catalog_session import (
    CATALOG_RUNTIME_DATA_KEY,
    CatalogRuntime,
    update_catalog_runtime_page,
)


_PAGE_SIZE = 10


async def _get_state(dialog_manager: DialogManager) -> FSMContext | None:
    state = dialog_manager.middleware_data.get("state")
    if isinstance(state, FSMContext):
        return state
    return state


async def _get_catalog_runtime(dialog_manager: DialogManager) -> CatalogRuntime:
    state = await _get_state(dialog_manager)
    if state is None:
        return {}
    data = await state.get_data()
    runtime = data.get(CATALOG_RUNTIME_DATA_KEY)
    if isinstance(runtime, dict):
        return runtime
    return {}


async def _update_catalog_runtime(dialog_manager: DialogManager, runtime: CatalogRuntime) -> None:
    state = await _get_state(dialog_manager)
    if state is None:
        return
    await state.update_data(**{CATALOG_RUNTIME_DATA_KEY: runtime})


def is_catalog_state(state_name: str | None) -> bool:
    return isinstance(state_name, str) and state_name.startswith("CatalogSG:")


def _control_text(runtime: CatalogRuntime) -> str:
    total = int(runtime.get("total", 0) or 0)
    shown = int(runtime.get("shown_count", 0) or 0)
    query = runtime.get("query") or ""
    source = runtime.get("source") or "catalog"
    view_mode = runtime.get("view_mode") or "cards"

    if total <= 0:
        return "Каталог пуст. Измените фильтры или отправьте новый запрос."

    lines = [f"Показано {shown} из {total}"]
    if query:
        lines.append(f"Запрос: {query}")
    lines.append(f"Источник: {source}")
    lines.append(f"Режим: {view_mode}")
    return "\n".join(lines)


async def clear_catalog_controls(
    *,
    message: Message,
    dialog_manager: DialogManager,
) -> CatalogRuntime:
    runtime = dict(await _get_catalog_runtime(dialog_manager))
    control_message_id = runtime.pop("control_message_id", None)
    if control_message_id and message.bot is not None:
        with contextlib.suppress(Exception):
            await message.bot.delete_message(
                chat_id=message.chat.id,
                message_id=int(control_message_id),
            )
    await _update_catalog_runtime(dialog_manager, runtime)
    return runtime


async def show_catalog_controls(
    *,
    message: Message,
    dialog_manager: DialogManager,
    runtime: CatalogRuntime | None = None,
    text: str | None = None,
) -> CatalogRuntime:
    current_runtime = dict(runtime or await _get_catalog_runtime(dialog_manager))
    control_message_id = current_runtime.pop("control_message_id", None)
    if control_message_id and message.bot is not None:
        with contextlib.suppress(Exception):
            await message.bot.delete_message(
                chat_id=message.chat.id,
                message_id=int(control_message_id),
            )
    i18n = dialog_manager.middleware_data.get("i18n")
    sent = await message.answer(
        text or _control_text(current_runtime),
        reply_markup=build_catalog_keyboard(
            shown=int(current_runtime.get("shown_count", 0) or 0),
            total=int(current_runtime.get("total", 0) or 0),
            i18n=i18n,
        ),
    )
    message_id = getattr(sent, "message_id", None)
    if isinstance(message_id, int):
        current_runtime["control_message_id"] = message_id
    await _update_catalog_runtime(dialog_manager, current_runtime)
    return current_runtime


async def activate_catalog_state(
    *,
    dialog_manager: DialogManager,
    state: Any,
) -> None:
    maybe_start = dialog_manager.start(
        state,
        mode=StartMode.RESET_STACK,
        show_mode=ShowMode.NO_UPDATE,
    )
    if inspect.isawaitable(maybe_start):
        await maybe_start


async def _remove_reply_keyboard(message: Message) -> None:
    sent = await message.answer(".", reply_markup=ReplyKeyboardRemove())
    if hasattr(sent, "delete"):
        with contextlib.suppress(Exception):
            await sent.delete()


async def load_next_catalog_page(
    *,
    message: Message,
    dialog_manager: DialogManager,
    telegram_id: int | None = None,
) -> CatalogRuntime:
    runtime = await _get_catalog_runtime(dialog_manager)
    shown_count = int(runtime.get("shown_count", 0) or 0)
    total = int(runtime.get("total", 0) or 0)
    next_offset = runtime.get("next_offset")

    if shown_count >= total or next_offset is None:
        return runtime

    property_bot = dialog_manager.middleware_data.get("property_bot")
    apartments_service = dialog_manager.middleware_data.get("apartments_service")
    if apartments_service is None and property_bot is not None:
        apartments_service = getattr(property_bot, "_apartments_service", None)
    if apartments_service is None:
        return runtime

    (
        results,
        total_count,
        new_next_offset,
        shown_item_ids,
    ) = await apartments_service.scroll_with_filters(
        filters=runtime.get("filters"),
        limit=_PAGE_SIZE,
        start_from=next_offset,
        exclude_ids=runtime.get("shown_item_ids") or None,
    )

    effective_telegram_id = telegram_id if telegram_id is not None else 0
    if not effective_telegram_id and message.from_user:
        effective_telegram_id = message.from_user.id
    await send_catalog_results(
        message=message,
        property_bot=property_bot,
        results=results,
        total_count=total_count,
        view_mode=runtime.get("view_mode", "cards"),
        shown_start=shown_count + 1,
        telegram_id=effective_telegram_id,
    )

    updated = update_catalog_runtime_page(
        runtime,
        results=results,
        total=total_count,
        next_offset=new_next_offset,
        shown_item_ids=shown_item_ids,
    )
    await _update_catalog_runtime(dialog_manager, updated)
    return updated


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
    await activate_catalog_state(dialog_manager=manager, state=CatalogSG.results)


async def _handle_catalog_filters_message(
    *,
    message: Message,
    manager: DialogManager,
) -> None:
    runtime = await clear_catalog_controls(message=message, dialog_manager=manager)
    await _remove_reply_keyboard(message)
    from telegram_bot.dialogs.states import FilterSG

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
    manager.show_mode = ShowMode.NO_UPDATE
    with contextlib.suppress(Exception):
        await manager.done()
    await show_client_main_menu(message, i18n=manager.middleware_data.get("i18n"))


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
    if callback.message is None:
        return
    await _handle_catalog_more_message(
        message=callback.message,
        manager=manager,
        telegram_id=callback.from_user.id if callback.from_user else None,
    )


async def on_catalog_filters(
    callback: CallbackQuery,
    button: Any,
    manager: DialogManager,
) -> None:
    if callback.message is None:
        return
    await _handle_catalog_filters_message(message=callback.message, manager=manager)


async def on_catalog_home(
    callback: CallbackQuery,
    button: Any,
    manager: DialogManager,
) -> None:
    if callback.message is None:
        return
    await _handle_catalog_home_message(message=callback.message, manager=manager)


async def on_catalog_manager(
    callback: CallbackQuery,
    button: Any,
    manager: DialogManager,
) -> None:
    if callback.message is None:
        return
    await _handle_catalog_manager_message(message=callback.message, manager=manager)


async def on_catalog_viewing(
    callback: CallbackQuery,
    button: Any,
    manager: DialogManager,
) -> None:
    if callback.message is None:
        return
    await _handle_catalog_viewing_message(message=callback.message, manager=manager)


async def on_catalog_bookmarks(
    callback: CallbackQuery,
    button: Any,
    manager: DialogManager,
) -> None:
    if callback.message is None:
        return
    await _handle_catalog_bookmarks_message(message=callback.message, manager=manager)


async def on_catalog_text_input(
    message: Message,
    widget: MessageInput,
    manager: DialogManager,
) -> None:
    if not message.text:
        return
    if await dispatch_catalog_text_action(message=message, manager=manager):
        return

    manager.show_mode = ShowMode.NO_UPDATE
    from telegram_bot.handlers.demo_handler import _run_demo_search

    state = await _get_state(manager)
    if state is None:
        return
    await _run_demo_search(
        message.text,
        message,
        state,
        pipeline=manager.middleware_data.get("pipeline"),
        apartments_service=manager.middleware_data.get("apartments_service"),
        dialog_manager=manager,
    )


async def on_catalog_voice_input(
    message: Message,
    widget: MessageInput,
    manager: DialogManager,
) -> None:
    manager.show_mode = ShowMode.NO_UPDATE
    from telegram_bot.handlers.demo_handler import handle_demo_search_voice

    state = await _get_state(manager)
    if state is None:
        return
    await handle_demo_search_voice(
        message,
        state,
        pipeline=manager.middleware_data.get("pipeline"),
        apartments_service=manager.middleware_data.get("apartments_service"),
        llm=manager.middleware_data.get("llm"),
        dialog_manager=manager,
    )


catalog_dialog = Dialog(
    Window(
        Const("Каталог активен."),
        MessageInput(on_catalog_text_input, content_types=[ContentType.TEXT]),
        MessageInput(on_catalog_voice_input, content_types=[ContentType.VOICE]),
        state=CatalogSG.results,
    ),
    Window(
        Const("Каталог активен."),
        MessageInput(on_catalog_text_input, content_types=[ContentType.TEXT]),
        MessageInput(on_catalog_voice_input, content_types=[ContentType.VOICE]),
        state=CatalogSG.empty,
    ),
    Window(
        Const("Детали объекта скоро будут доступны."),
        state=CatalogSG.details,
    ),
    launch_mode=LaunchMode.ROOT,
)
