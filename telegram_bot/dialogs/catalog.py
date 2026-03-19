"""Dialog-owned catalog control shell."""

from __future__ import annotations

from typing import Any

from aiogram.enums import ContentType
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from aiogram_dialog import Dialog, DialogManager, LaunchMode, ShowMode, StartMode, Window
from aiogram_dialog.widgets.input import MessageInput
from aiogram_dialog.widgets.kbd import Button, Group
from aiogram_dialog.widgets.text import Const, Format

from telegram_bot.dialogs.root_nav import get_main_menu_label
from telegram_bot.dialogs.states import CatalogSG, ClientMenuSG, FilterSG
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


async def get_catalog_data(dialog_manager: DialogManager, **kwargs: Any) -> dict[str, Any]:
    runtime = await _get_catalog_runtime(dialog_manager)
    i18n = dialog_manager.middleware_data.get("i18n")
    return {
        "control_text": _control_text(runtime),
        "btn_main_menu": get_main_menu_label(i18n),
        "has_more": bool(runtime.get("next_offset"))
        and (int(runtime.get("shown_count", 0) or 0) < int(runtime.get("total", 0) or 0)),
    }


async def load_next_catalog_page(
    *,
    message: Message,
    dialog_manager: DialogManager,
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

    telegram_id = message.from_user.id if message.from_user else 0
    await send_catalog_results(
        message=message,
        property_bot=property_bot,
        results=results,
        total_count=total_count,
        view_mode=runtime.get("view_mode", "cards"),
        shown_start=shown_count + 1,
        telegram_id=telegram_id,
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


async def on_catalog_more(
    callback: CallbackQuery,
    button: Any,
    manager: DialogManager,
) -> None:
    if callback.message is None:
        return
    await load_next_catalog_page(message=callback.message, dialog_manager=manager)
    manager.show_mode = ShowMode.EDIT
    await manager.switch_to(CatalogSG.results)


async def on_catalog_filters(
    callback: CallbackQuery,
    button: Any,
    manager: DialogManager,
) -> None:
    runtime = await _get_catalog_runtime(manager)
    await manager.start(FilterSG.hub, data={"filters": runtime.get("filters", {})})


async def on_catalog_home(
    callback: CallbackQuery,
    button: Any,
    manager: DialogManager,
) -> None:
    await manager.start(ClientMenuSG.main, mode=StartMode.RESET_STACK)


async def on_catalog_manager(
    callback: CallbackQuery,
    button: Any,
    manager: DialogManager,
) -> None:
    if callback.message is None:
        return
    property_bot = manager.middleware_data.get("property_bot")
    state = await _get_state(manager)
    if property_bot is not None and state is not None:
        await property_bot._handle_manager(
            callback.message,
            state=state,
            dialog_manager=manager,
            i18n=manager.middleware_data.get("i18n"),
        )


async def on_catalog_viewing(
    callback: CallbackQuery,
    button: Any,
    manager: DialogManager,
) -> None:
    if callback.message is None:
        return
    property_bot = manager.middleware_data.get("property_bot")
    state = await _get_state(manager)
    if property_bot is not None and state is not None:
        await property_bot._handle_viewing(callback.message, state, manager)


async def on_catalog_bookmarks(
    callback: CallbackQuery,
    button: Any,
    manager: DialogManager,
) -> None:
    if callback.message is None:
        return
    property_bot = manager.middleware_data.get("property_bot")
    state = await _get_state(manager)
    if property_bot is not None and state is not None:
        await property_bot._handle_bookmarks(callback.message, state=state)


async def on_catalog_text_input(
    message: Message,
    widget: MessageInput,
    manager: DialogManager,
) -> None:
    if not message.text:
        return
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
        Format("{control_text}"),
        Group(
            Button(Const("📥 Показать ещё"), id="catalog_more", on_click=on_catalog_more),
            Button(Const("🔍 Фильтры"), id="catalog_filters", on_click=on_catalog_filters),
            Button(Const("📌 Избранное"), id="catalog_bookmarks", on_click=on_catalog_bookmarks),
            Button(Const("📅 Запись на осмотр"), id="catalog_viewing", on_click=on_catalog_viewing),
            Button(
                Const("👤 Написать менеджеру"), id="catalog_manager", on_click=on_catalog_manager
            ),
            Button(Format("{btn_main_menu}"), id="catalog_home", on_click=on_catalog_home),
            width=2,
        ),
        MessageInput(on_catalog_text_input, content_types=[ContentType.TEXT]),
        MessageInput(on_catalog_voice_input, content_types=[ContentType.VOICE]),
        getter=get_catalog_data,
        state=CatalogSG.results,
    ),
    Window(
        Const("Ничего не найдено. Измените фильтры или отправьте новый запрос."),
        Group(
            Button(Const("🔍 Фильтры"), id="catalog_filters_empty", on_click=on_catalog_filters),
            Button(Format("{btn_main_menu}"), id="catalog_home_empty", on_click=on_catalog_home),
            width=2,
        ),
        MessageInput(on_catalog_text_input, content_types=[ContentType.TEXT]),
        MessageInput(on_catalog_voice_input, content_types=[ContentType.VOICE]),
        getter=get_catalog_data,
        state=CatalogSG.empty,
    ),
    Window(
        Const("Детали объекта скоро будут доступны."),
        Button(Format("{btn_main_menu}"), id="catalog_home_details", on_click=on_catalog_home),
        getter=get_catalog_data,
        state=CatalogSG.details,
    ),
    launch_mode=LaunchMode.ROOT,
)
